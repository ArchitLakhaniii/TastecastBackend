from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationIssue:
    level: str  # "error" | "warning"
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


def _require_columns(df: pd.DataFrame, required: Iterable[str], table: str) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    missing = [c for c in required if c not in df.columns]
    if missing:
        issues.append(
            ValidationIssue(
                level="error",
                code="missing_columns",
                message=f"{table} missing required columns: {missing}",
                details={"missing": missing},
            )
        )
    return issues


def _coerce_date(df: pd.DataFrame, col: str, table: str) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if col not in df.columns:
        return issues
    try:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    except Exception as e:
        issues.append(
            ValidationIssue(
                level="error",
                code="date_parse_failed",
                message=f"{table}.{col} failed to parse as datetime: {e}",
            )
        )
        return issues
    bad = df[col].isna().sum()
    if bad:
        issues.append(
            ValidationIssue(
                level="error",
                code="invalid_dates",
                message=f"{table}.{col} contains {int(bad)} invalid dates",
                details={"invalid_rows": int(bad)},
            )
        )
    return issues


def _coerce_numeric_nonneg(df: pd.DataFrame, col: str, table: str) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if col not in df.columns:
        return issues
    df[col] = pd.to_numeric(df[col], errors="coerce")
    nan = df[col].isna().sum()
    if nan:
        issues.append(
            ValidationIssue(
                level="error",
                code="non_numeric",
                message=f"{table}.{col} contains {int(nan)} non-numeric values",
                details={"non_numeric_rows": int(nan)},
            )
        )
    neg = (df[col] < 0).sum(skipna=True)
    if neg:
        issues.append(
            ValidationIssue(
                level="warning",
                code="negative_values",
                message=f"{table}.{col} contains {int(neg)} negative values",
                details={"negative_rows": int(neg)},
            )
        )
    return issues


def _dedupe_primary_key(df: pd.DataFrame, key_cols: List[str], table: str) -> Tuple[pd.DataFrame, List[ValidationIssue]]:
    issues: List[ValidationIssue] = []
    if not all(c in df.columns for c in key_cols):
        return df, issues
    dups = df.duplicated(subset=key_cols, keep=False)
    if dups.any():
        n = int(dups.sum())
        issues.append(
            ValidationIssue(
                level="warning",
                code="duplicate_grain_rows",
                message=f"{table} has {n} duplicate primary-grain rows; they will be aggregated (sum qty_sold)",
                details={"duplicates": n, "key": key_cols},
            )
        )
        # Aggregate numeric columns where it makes sense; for now: qty_sold, net_sales, gross_sales, discount_amount
        agg_map: Dict[str, str] = {}
        for c in df.columns:
            if c in key_cols:
                continue
            if c in ("qty_sold", "net_sales", "gross_sales", "discount_amount", "returns_or_voids"):
                agg_map[c] = "sum"
        if "qty_sold" in df.columns and "qty_sold" not in agg_map:
            agg_map["qty_sold"] = "sum"
        df = df.groupby(key_cols, as_index=False).agg(agg_map) if agg_map else df.drop_duplicates(subset=key_cols)
    return df, issues


def validate_sales_fact(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[ValidationIssue]]:
    """Validate canonical sales_fact.\n+\n+    Required columns (Mode B/C): store_id, date, menu_item_id, qty_sold.\n+    """
    table = "sales_fact"
    issues: List[ValidationIssue] = []
    df = df.copy()
    issues += _require_columns(df, ["store_id", "date", "menu_item_id", "qty_sold"], table)
    if any(i.level == "error" for i in issues):
        return df, issues

    issues += _coerce_date(df, "date", table)
    issues += _coerce_numeric_nonneg(df, "qty_sold", table)
    df, dedupe_issues = _dedupe_primary_key(df, ["store_id", "date", "menu_item_id"], table)
    issues += dedupe_issues

    # too-little-history warning (per series)
    if all(c in df.columns for c in ("store_id", "menu_item_id", "date")):
        counts = df.groupby(["store_id", "menu_item_id"])["date"].nunique()
        small = counts[counts < 60]
        if len(small) > 0:
            issues.append(
                ValidationIssue(
                    level="warning",
                    code="short_history",
                    message=f"{len(small)} series have <60 unique dates; intermittent/cold-start fallbacks may apply",
                    details={"series_under_60_days": int(len(small))},
                )
            )

    return df, issues


def validate_recipe_fact(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[ValidationIssue]]:
    table = "recipe_fact"
    issues: List[ValidationIssue] = []
    df = df.copy()
    issues += _require_columns(df, ["menu_item_id", "ingredient_id", "ingredient_qty_per_unit"], table)
    if any(i.level == "error" for i in issues):
        return df, issues
    issues += _coerce_numeric_nonneg(df, "ingredient_qty_per_unit", table)
    for col in ("yield_loss_pct", "waste_pct"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df, issues


def validate_ingredient_dim(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[ValidationIssue]]:
    table = "ingredient_dim"
    issues: List[ValidationIssue] = []
    df = df.copy()
    issues += _require_columns(df, ["ingredient_id", "ingredient_name"], table)
    if any(i.level == "error" for i in issues):
        return df, issues
    for col in ("lead_time_days_avg", "lead_time_days_std", "shelf_life_days", "pack_size", "min_order_qty", "lot_size", "case_multiple", "service_level_target"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df, issues


def validate_inventory_snapshot(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[ValidationIssue]]:
    table = "inventory_snapshot"
    issues: List[ValidationIssue] = []
    df = df.copy()
    issues += _require_columns(df, ["store_id", "ingredient_id", "snapshot_date", "on_hand_qty"], table)
    if any(i.level == "error" for i in issues):
        return df, issues
    issues += _coerce_date(df, "snapshot_date", table)
    issues += _coerce_numeric_nonneg(df, "on_hand_qty", table)
    for col in ("reserved_qty", "on_order_qty", "backorder_qty", "usable_qty"):
        if col in df.columns:
            issues += _coerce_numeric_nonneg(df, col, table)
    return df, issues

