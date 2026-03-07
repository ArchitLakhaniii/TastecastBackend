from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd


def simulate_inventory(
    ingredient_plan: pd.DataFrame,
    inventory_snapshot: Optional[pd.DataFrame],
    ingredient_dim: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Simulate inventory day-by-day at store×ingredient granularity.

    Minimal v1:
    - begin_on_hand from latest snapshot <= first plan date (or 0)
    - receipts ignored unless inventory_snapshot has on_order_qty (treated as available at day0)
    - consumption = ingredient_demand_p50
    - waste is 0 (expiry buckets are placeholders unless provided by snapshot)
    """
    plan = ingredient_plan.copy()
    plan["date"] = pd.to_datetime(plan["date"])
    plan = plan.sort_values(["store_id", "ingredient_id", "date"]).reset_index(drop=True)

    snap = None
    if inventory_snapshot is not None and len(inventory_snapshot) > 0:
        snap = inventory_snapshot.copy()
        snap["snapshot_date"] = pd.to_datetime(snap["snapshot_date"])

    rows = []
    for (store_id, ing_id), g in plan.groupby(["store_id", "ingredient_id"], sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        start_date = g["date"].min()

        begin_qty = 0.0
        on_order = 0.0
        reserved = 0.0
        backorder = 0.0
        if snap is not None:
            ss = snap[(snap["store_id"] == store_id) & (snap["ingredient_id"] == ing_id)]
            if len(ss) > 0:
                ss = ss[ss["snapshot_date"] <= start_date].sort_values("snapshot_date")
                if len(ss) > 0:
                    last = ss.iloc[-1]
                    begin_qty = float(pd.to_numeric(last.get("on_hand_qty", 0), errors="coerce") or 0.0)
                    on_order = float(pd.to_numeric(last.get("on_order_qty", 0), errors="coerce") or 0.0)
                    reserved = float(pd.to_numeric(last.get("reserved_qty", 0), errors="coerce") or 0.0)
                    backorder = float(pd.to_numeric(last.get("backorder_qty", 0), errors="coerce") or 0.0)

        end_prev = begin_qty
        for _, r in g.iterrows():
            d = r["date"]
            receipts = 0.0
            available = float(end_prev) + float(receipts)
            consumption = float(pd.to_numeric(r.get("ingredient_demand_p50", 0.0), errors="coerce") or 0.0)
            waste = 0.0
            end_on_hand = max(0.0, available - consumption - waste)
            inventory_position = max(0.0, available - reserved) + max(0.0, on_order) - max(0.0, backorder)

            rows.append(
                {
                    "store_id": store_id,
                    "date": d,
                    "ingredient_id": ing_id,
                    "ingredient_demand_p50": float(consumption),
                    "ingredient_demand_p90": float(pd.to_numeric(r.get("ingredient_demand_p90", consumption * 1.2), errors="coerce") or consumption * 1.2),
                    "begin_on_hand": float(end_prev),
                    "receipts": float(receipts),
                    "consumption": float(consumption),
                    "waste": float(waste),
                    "end_on_hand": float(end_on_hand),
                    "inventory_position": float(inventory_position),
                    # placeholders for expiry buckets
                    "expiry_bucket_0_1d": None,
                    "expiry_bucket_2_3d": None,
                    "expiry_bucket_4_7d": None,
                    "expiry_bucket_gt_7d": None,
                }
            )
            end_prev = end_on_hand

    out = pd.DataFrame(rows)
    if ingredient_dim is not None and "ingredient_id" in ingredient_dim.columns:
        cols = ["ingredient_id"] + [c for c in ("ingredient_name", "uom", "category") if c in ingredient_dim.columns]
        out = out.merge(ingredient_dim[cols], on="ingredient_id", how="left")
    return out

