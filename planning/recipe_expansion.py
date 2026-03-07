from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd


def expand_menu_to_ingredients(
    menu_plan: pd.DataFrame,
    recipe_fact: pd.DataFrame,
    ingredient_dim: Optional[pd.DataFrame] = None,
    *,
    qty_col: str = "qty_total",
) -> pd.DataFrame:
    """Compute ingredient demand by store/date from menu plan and recipe mappings.

    Ingredient demand uses planned menu qty (qty_total), not baseline.
    Applies yield/waste adjustments if columns exist.
    """
    plan = menu_plan.copy()
    rec = recipe_fact.copy()

    plan["date"] = pd.to_datetime(plan["date"])
    rec = rec.copy()

    # defaults for adjustments
    if "yield_loss_pct" not in rec.columns:
        rec["yield_loss_pct"] = 0.0
    if "waste_pct" not in rec.columns:
        rec["waste_pct"] = 0.0

    rec["yield_loss_pct"] = pd.to_numeric(rec["yield_loss_pct"], errors="coerce").fillna(0.0)
    rec["waste_pct"] = pd.to_numeric(rec["waste_pct"], errors="coerce").fillna(0.0)
    rec["ingredient_qty_per_unit"] = pd.to_numeric(rec["ingredient_qty_per_unit"], errors="coerce").fillna(0.0)

    # merge plan with recipe lines
    merged = plan.merge(rec, on="menu_item_id", how="left", suffixes=("", "_recipe"))
    merged["planned_menu_qty"] = pd.to_numeric(merged[qty_col], errors="coerce").fillna(0.0)

    # yield_adjustment = (1 + waste_pct) / (1 - yield_loss_pct)
    denom = (1.0 - merged["yield_loss_pct"]).clip(lower=0.01)
    merged["yield_adjustment"] = (1.0 + merged["waste_pct"]) / denom
    merged["ingredient_demand"] = merged["planned_menu_qty"] * merged["ingredient_qty_per_unit"] * merged["yield_adjustment"]

    ingredient_plan = (
        merged.groupby(["store_id", "date", "ingredient_id"], as_index=False)["ingredient_demand"].sum()
        if "ingredient_id" in merged.columns
        else pd.DataFrame(columns=["store_id", "date", "ingredient_id", "ingredient_demand"])
    )

    ingredient_plan["ingredient_demand_p50"] = ingredient_plan["ingredient_demand"].round(6)
    ingredient_plan["ingredient_demand_p90"] = (ingredient_plan["ingredient_demand"] * 1.2).round(6)  # heuristic until full uncertainty propagation
    ingredient_plan = ingredient_plan.drop(columns=["ingredient_demand"])

    if ingredient_dim is not None and "ingredient_id" in ingredient_dim.columns:
        ingredient_plan = ingredient_plan.merge(
            ingredient_dim[["ingredient_id"] + [c for c in ("ingredient_name", "uom", "category") if c in ingredient_dim.columns]],
            on="ingredient_id",
            how="left",
        )

    return ingredient_plan

