from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from suggestions import get_suggestions


@dataclass(frozen=True)
class SpecialsPolicy:
    allowed_weekdays: Tuple[int, ...] = (3, 4, 5, 6)  # Thu-Sun
    max_specials_per_day: int = 1
    max_special_units_per_day: int = 10
    surplus_threshold_units: float = 0.0


def recommend_specials(
    menu_plan: pd.DataFrame,
    inventory_sim: pd.DataFrame,
    recipe_fact: pd.DataFrame,
    ingredient_dim: Optional[pd.DataFrame],
    *,
    policy: SpecialsPolicy = SpecialsPolicy(),
    suggestion_seed: int = 0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Recommend specials when projected surplus exists.\n+\n+    Minimal v1:\n+    - Identify surplus ingredient as end_on_hand - demand_next_shelf_life (heuristic)\n+    - Choose the menu item that consumes that ingredient the most per unit\n+    - Add special units (special_added) capped by policy\n+    - Emit advisory rows\n+    """
    plan = menu_plan.copy()
    plan["date"] = pd.to_datetime(plan["date"])
    plan["special_added"] = pd.to_numeric(plan.get("special_added", 0), errors="coerce").fillna(0).astype(int)
    plan["qty_total"] = pd.to_numeric(plan.get("qty_total", plan.get("baseline_qty", 0)), errors="coerce").fillna(0.0)

    inv = inventory_sim.copy()
    inv["date"] = pd.to_datetime(inv["date"])

    # Precompute recipe usage per item×ingredient
    rec = recipe_fact.copy()
    rec["ingredient_qty_per_unit"] = pd.to_numeric(rec["ingredient_qty_per_unit"], errors="coerce").fillna(0.0)

    advisories = []
    # For each store-day on allowed weekdays, find ingredient with max surplus
    for (store_id, d), gday in inv.groupby(["store_id", "date"], sort=False):
        if int(pd.to_datetime(d).weekday()) not in policy.allowed_weekdays:
            continue

        # compute simple surplus = end_on_hand - next_3day_demand_p90 (fallback)
        gday = gday.sort_values("ingredient_id")
        surplus_rows = []
        for _, r in gday.iterrows():
            ing_id = r["ingredient_id"]
            shelf_life = None
            if ingredient_dim is not None and "shelf_life_days" in ingredient_dim.columns:
                row = ingredient_dim[ingredient_dim["ingredient_id"] == ing_id]
                if len(row) > 0:
                    shelf_life = row.iloc[0].get("shelf_life_days", None)
            sl = int(float(shelf_life)) if shelf_life is not None and pd.notna(shelf_life) else 3

            # demand window starting tomorrow
            future = inv[(inv["store_id"] == store_id) & (inv["ingredient_id"] == ing_id) & (inv["date"] > d)].sort_values("date").head(sl)
            future_need = float(pd.to_numeric(future.get("ingredient_demand_p90", 0.0), errors="coerce").fillna(0.0).sum()) if len(future) else 0.0
            end_on_hand = float(pd.to_numeric(r.get("end_on_hand", 0.0), errors="coerce") or 0.0)
            surplus = end_on_hand - future_need
            surplus_rows.append((ing_id, surplus, end_on_hand, future_need))

        if not surplus_rows:
            continue
        ing_id, surplus, end_on_hand, future_need = sorted(surplus_rows, key=lambda x: x[1], reverse=True)[0]
        if surplus <= policy.surplus_threshold_units:
            continue

        # choose candidate item using this ingredient
        cand = rec[rec["ingredient_id"] == ing_id].sort_values("ingredient_qty_per_unit", ascending=False)
        if len(cand) == 0:
            continue
        best_item = cand.iloc[0]["menu_item_id"]
        per_unit = float(cand.iloc[0]["ingredient_qty_per_unit"]) if pd.notna(cand.iloc[0]["ingredient_qty_per_unit"]) else 0.0
        if per_unit <= 0:
            continue

        max_units = int(surplus // per_unit)
        add_units = int(max(0, min(policy.max_special_units_per_day, max_units)))
        if add_units <= 0:
            continue

        # apply to menu_plan for this store-day-item row(s)
        mask = (plan["store_id"] == store_id) & (plan["date"] == d) & (plan["menu_item_id"] == best_item)
        if not mask.any():
            # if item not present on that day, create a row (rare) with baseline 0
            plan = pd.concat(
                [
                    plan,
                    pd.DataFrame(
                        [
                            {
                                "store_id": store_id,
                                "date": d,
                                "menu_item_id": best_item,
                                "baseline_qty": 0.0,
                                "special_added": 0,
                                "qty_total": 0.0,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
            mask = (plan["store_id"] == store_id) & (plan["date"] == d) & (plan["menu_item_id"] == best_item)

        plan.loc[mask, "special_added"] = plan.loc[mask, "special_added"].astype(int) + add_units
        plan.loc[mask, "qty_total"] = pd.to_numeric(plan.loc[mask, "qty_total"], errors="coerce").fillna(0.0) + float(add_units)

        suggestions = get_suggestions(str(ing_id), k=5, seed=suggestion_seed)
        advisories.append(
            {
                "store_id": store_id,
                "date": pd.to_datetime(d).date().isoformat(),
                "advisory_type": "SPECIAL",
                "severity": "info",
                "entity_type": "ingredient",
                "entity_id": str(ing_id),
                "message": f"{pd.to_datetime(d).date()}: Surplus projected for {ing_id}. Schedule {add_units} specials of item {best_item}.",
                "recommended_action": "run_special",
                "qty": int(add_units),
                "uom": None,
                "reason_code": "surplus_burn",
                "supporting_metrics_json": json.dumps(
                    {
                        "ingredient_end_on_hand": end_on_hand,
                        "future_need_p90": future_need,
                        "surplus_units": surplus,
                        "chosen_menu_item_id": best_item,
                        "ingredient_per_unit": per_unit,
                        "suggestions": suggestions,
                    }
                ),
            }
        )

    adv_df = pd.DataFrame(advisories)
    return plan.sort_values(["store_id", "date", "menu_item_id"]).reset_index(drop=True), adv_df

