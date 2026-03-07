from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class SchemaMapResult:
    df: pd.DataFrame
    applied_mapping: Dict[str, str]  # canonical -> source column


def _lower_cols(cols: Iterable[str]) -> Dict[str, str]:
    return {str(c).strip().lower(): str(c) for c in cols}


DEFAULT_ALIASES: Dict[str, List[str]] = {
    "date": ["date", "day", "business_date", "sale_date", "sold_at", "order_date"],
    "qty_sold": ["qty_sold", "qty", "quantity", "units", "sold", "unit_sold", "count"],
    "menu_item_name": ["menu_item_name", "menu_item", "item", "item_name", "sku", "product", "product_name"],
    "menu_item_id": ["menu_item_id", "item_id", "sku_id", "product_id"],
    "store_id": ["store_id", "store", "location", "branch", "restaurant", "site", "store_code"],
}


def infer_mapping(df: pd.DataFrame, aliases: Optional[Dict[str, List[str]]] = None) -> Dict[str, str]:
    """Infer canonical->source mapping using alias lists.\n+\n+    Only maps columns that are present. Caller decides which canonical fields are required.\n+    """
    aliases = aliases or DEFAULT_ALIASES
    by_lower = _lower_cols(df.columns)
    mapping: Dict[str, str] = {}
    for canonical, names in aliases.items():
        for n in names:
            key = n.strip().lower()
            if key in by_lower:
                mapping[canonical] = by_lower[key]
                break
    return mapping


def apply_mapping(df: pd.DataFrame, mapping: Dict[str, str]) -> SchemaMapResult:
    out = df.copy()
    applied: Dict[str, str] = {}
    for canonical, source in mapping.items():
        if source in out.columns:
            out[canonical] = out[source]
            applied[canonical] = source
    return SchemaMapResult(df=out, applied_mapping=applied)


def ensure_menu_item_id(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Ensure `menu_item_id` exists.\n+\n+    If missing, derive from `menu_item_name` by stable factorization.\n+    """
    out = df.copy()
    applied: Dict[str, str] = {}
    if "menu_item_id" in out.columns and out["menu_item_id"].notna().any():
        return out, applied
    if "menu_item_name" in out.columns:
        # stable factorization based on sorted unique names
        names = out["menu_item_name"].astype(str).fillna("")
        uniq = sorted(set(names.tolist()))
        idx = {name: f"item_{i:04d}" for i, name in enumerate(uniq)}
        out["menu_item_id"] = names.map(idx)
        applied["menu_item_id"] = "derived_from_menu_item_name"
    else:
        # ultra-minimal fallback: treat as a single aggregate item
        out["menu_item_id"] = "aggregate"
        applied["menu_item_id"] = "default_aggregate"
    return out, applied


def ensure_store_id(df: pd.DataFrame, default_store_id: str = "default") -> Tuple[pd.DataFrame, Dict[str, str]]:
    out = df.copy()
    applied: Dict[str, str] = {}
    if "store_id" not in out.columns:
        out["store_id"] = default_store_id
        applied["store_id"] = "default"
    else:
        out["store_id"] = out["store_id"].fillna(default_store_id)
    return out, applied

