from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from ingestion.quality_checks import basic_quality_checks_sales_fact
from ingestion.schema_map import apply_mapping, ensure_menu_item_id, ensure_store_id, infer_mapping
from schemas.canonical import (
    ValidationIssue,
    validate_ingredient_dim,
    validate_inventory_snapshot,
    validate_recipe_fact,
    validate_sales_fact,
)


@dataclass(frozen=True)
class IngestionResult:
    sales_fact: pd.DataFrame
    recipe_fact: Optional[pd.DataFrame]
    ingredient_dim: Optional[pd.DataFrame]
    inventory_snapshot: Optional[pd.DataFrame]
    report: Dict[str, Any]


def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def ingest_sales_csv(
    df_raw: pd.DataFrame,
    mapping_override: Optional[Dict[str, str]] = None,
    default_store_id: str = "default",
) -> Tuple[pd.DataFrame, Dict[str, Any], list[ValidationIssue]]:
    """Map a raw sales CSV into canonical `sales_fact` and validate."""
    inferred = infer_mapping(df_raw)
    mapping = dict(inferred)
    if mapping_override:
        # override uses canonical->source keys
        mapping.update(mapping_override)
    mapped = apply_mapping(df_raw, mapping)
    df = mapped.df

    # ensure required canonical columns exist / derived
    df, store_applied = ensure_store_id(df, default_store_id=default_store_id)
    df, item_applied = ensure_menu_item_id(df)

    # if menu_item_name exists but wasn't mapped (or is empty), keep it if present
    applied = {}
    applied.update(mapped.applied_mapping)
    applied.update(store_applied)
    applied.update(item_applied)

    # Validate canonical
    df_valid, issues = validate_sales_fact(df[["store_id", "date", "menu_item_id", "qty_sold"] + [c for c in df.columns if c not in ("store_id", "date", "menu_item_id", "qty_sold")]])
    issues += basic_quality_checks_sales_fact(df_valid)

    report = {
        "sales_fact": {
            "rows": int(len(df_valid)),
            "columns": list(df_valid.columns),
            "applied_mapping": applied,
        }
    }
    return df_valid, report, issues


def ingest_optional_table(
    df_raw: Optional[pd.DataFrame],
    table_name: str,
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any], list[ValidationIssue]]:
    if df_raw is None:
        return None, {table_name: {"present": False}}, []

    df = df_raw.copy()
    issues: list[ValidationIssue] = []
    if table_name == "recipe_fact":
        df, issues = validate_recipe_fact(df)
    elif table_name == "ingredient_dim":
        df, issues = validate_ingredient_dim(df)
    elif table_name == "inventory_snapshot":
        df, issues = validate_inventory_snapshot(df)
    else:
        issues.append(ValidationIssue(level="warning", code="unknown_table", message=f"Unknown table: {table_name}"))

    report = {
        table_name: {
            "present": True,
            "rows": int(len(df)),
            "columns": list(df.columns),
        }
    }
    return df, report, issues


def ingest_mode_c(
    sales_df_raw: pd.DataFrame,
    recipe_df_raw: Optional[pd.DataFrame] = None,
    ingredient_df_raw: Optional[pd.DataFrame] = None,
    inventory_df_raw: Optional[pd.DataFrame] = None,
    mapping_override: Optional[Dict[str, str]] = None,
    default_store_id: str = "default",
) -> IngestionResult:
    issues: list[ValidationIssue] = []
    sales_fact, sales_report, sales_issues = ingest_sales_csv(
        sales_df_raw, mapping_override=mapping_override, default_store_id=default_store_id
    )
    issues += sales_issues

    recipe_fact, recipe_report, recipe_issues = ingest_optional_table(recipe_df_raw, "recipe_fact")
    ingredient_dim, ingredient_report, ingredient_issues = ingest_optional_table(ingredient_df_raw, "ingredient_dim")
    inventory_snapshot, inv_report, inv_issues = ingest_optional_table(inventory_df_raw, "inventory_snapshot")
    issues += recipe_issues + ingredient_issues + inv_issues

    # Mode C requires recipe + ingredient + inventory for full planning; we degrade gracefully later.
    report: Dict[str, Any] = {}
    report.update(sales_report)
    report.update(recipe_report)
    report.update(ingredient_report)
    report.update(inv_report)
    report["issues"] = [i.__dict__ for i in issues]
    report["ok"] = not any(i.level == "error" for i in issues)

    return IngestionResult(
        sales_fact=sales_fact,
        recipe_fact=recipe_fact,
        ingredient_dim=ingredient_dim,
        inventory_snapshot=inventory_snapshot,
        report=report,
    )

