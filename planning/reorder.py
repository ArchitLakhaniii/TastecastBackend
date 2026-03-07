from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd

from inventory.policy import compute_reorder_point, compute_safety_stock, round_up_lot


def _get_ing_param(ingredient_dim: Optional[pd.DataFrame], ing_id: str, col: str, default):
    if ingredient_dim is None or col not in ingredient_dim.columns:
        return default
    row = ingredient_dim[ingredient_dim["ingredient_id"] == ing_id]
    if len(row) == 0:
        return default
    v = row.iloc[0].get(col, default)
    try:
        if pd.isna(v):
            return default
    except Exception:
        pass
    return v


def compute_reorder_plan(
    inventory_sim: pd.DataFrame,
    ingredient_dim: Optional[pd.DataFrame],
    *,
    default_service_level: float = 0.95,
    default_lead_time_days: int = 2,
    review_period_days: int = 7,
) -> pd.DataFrame:
    """Compute reorder quantities for each store×ingredient×date.\n+\n+    Minimal v1:\n+    - mean_daily_demand: rolling mean over last 28 days of ingredient_demand_p50\n+    - std_daily_demand: rolling std over last 28 days (fallback to 25% mean)\n+    - safety stock: z * std * sqrt(lead_time)\n+    - ROP: mean*lead_time + safety\n+    - target_stock: demand over (lead+review) + safety\n+    - suggested_order_qty_final: rounded to constraints\n+    """
    df = inventory_sim.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["store_id", "ingredient_id", "date"]).reset_index(drop=True)

    out_rows = []
    for (store_id, ing_id), g in df.groupby(["store_id", "ingredient_id"], sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        demand = pd.to_numeric(g["ingredient_demand_p50"], errors="coerce").fillna(0.0).astype(float)
        mean28 = demand.shift(1).rolling(28, min_periods=3).mean().fillna(demand.mean() if len(demand) else 0.0)
        std28 = demand.shift(1).rolling(28, min_periods=3).std(ddof=1)
        std28 = std28.fillna((mean28 * 0.25).fillna(1.0))

        lead = int(_get_ing_param(ingredient_dim, ing_id, "lead_time_days_avg", default_lead_time_days) or default_lead_time_days)
        service_level = float(_get_ing_param(ingredient_dim, ing_id, "service_level_target", default_service_level) or default_service_level)
        lot = int(_get_ing_param(ingredient_dim, ing_id, "lot_size", 0) or 0)
        case_mult = int(_get_ing_param(ingredient_dim, ing_id, "case_multiple", 0) or 0)
        min_order = float(_get_ing_param(ingredient_dim, ing_id, "min_order_qty", 0) or 0)
        shelf_life = _get_ing_param(ingredient_dim, ing_id, "shelf_life_days", None)
        uom = _get_ing_param(ingredient_dim, ing_id, "uom", None)

        for i, r in g.iterrows():
            m = float(mean28.iloc[i])
            s = float(std28.iloc[i])
            safety = compute_safety_stock(s, lead, service_level)
            rop = compute_reorder_point(m, lead, safety)

            inv_pos = float(pd.to_numeric(r.get("inventory_position", 0.0), errors="coerce") or 0.0)

            # lead+review demand forecast using p90 as conservative for procurement (simple)
            horizon = lead + review_period_days
            future = g["ingredient_demand_p90"].iloc[i : i + horizon]
            lead_review_demand = float(pd.to_numeric(future, errors="coerce").fillna(0.0).sum())
            target_stock = lead_review_demand + safety

            order_raw = max(0.0, target_stock - inv_pos) if inv_pos < rop else 0.0

            # perishability cap (if shelf life known)
            if shelf_life is not None and pd.notna(shelf_life):
                sl = int(float(shelf_life))
                future_sl = g["ingredient_demand_p90"].iloc[i : i + max(1, sl)]
                max_safe = float(pd.to_numeric(future_sl, errors="coerce").fillna(0.0).sum()) + safety
                order_raw = min(order_raw, max_safe)

            # apply rounding constraints
            order_qty = float(order_raw)
            # lot size rounding first
            if lot and lot > 0:
                order_qty = float(round_up_lot(order_qty, lot))
            # case multiple rounding
            if case_mult and case_mult > 0:
                import math

                order_qty = float(math.ceil(order_qty / case_mult) * case_mult)
            # MOQ
            if order_qty > 0 and min_order and order_qty < min_order:
                order_qty = float(min_order)

            reason = "below_ROP" if inv_pos < rop and order_qty > 0 else "no_order"
            out_rows.append(
                {
                    "store_id": store_id,
                    "date": r["date"],
                    "ingredient_id": ing_id,
                    "uom": uom,
                    "mean_daily_usage": m,
                    "std_daily_usage": s,
                    "lead_time_days": lead,
                    "service_level": service_level,
                    "safety_stock": float(safety),
                    "reorder_point": float(rop),
                    "target_stock": float(target_stock),
                    "suggested_order_qty_raw": float(order_raw),
                    "suggested_order_qty_final": float(order_qty),
                    "order_reason": reason,
                    "supporting_metrics_json": json.dumps(
                        {
                            "inventory_position": float(inv_pos),
                            "lead_review_demand_p90": float(lead_review_demand),
                            "constraints": {
                                "lot_size": int(lot) if lot is not None else None,
                                "case_multiple": int(case_mult) if case_mult is not None else None,
                                "min_order_qty": float(min_order) if min_order is not None else None,
                                "shelf_life_days": int(shelf_life) if shelf_life is not None and pd.notna(shelf_life) else None,
                            },
                        },
                        default=str,
                    ),
                }
            )

    return pd.DataFrame(out_rows)

