from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from forecasting.forecaster import forecast_menu_demand
from planning.recipe_expansion import expand_menu_to_ingredients
from planning.inventory_sim import simulate_inventory
from planning.reorder import compute_reorder_plan
from planning.specials import recommend_specials, SpecialsPolicy


@dataclass(frozen=True)
class PipelineOutputs:
    run_id: str
    forecast_df: pd.DataFrame
    daily_plan_df: pd.DataFrame
    ingredient_plan_df: Optional[pd.DataFrame]
    inventory_sim_df: Optional[pd.DataFrame]
    reorder_df: Optional[pd.DataFrame]
    advisories_df: pd.DataFrame
    explanations: Dict[str, Any]
    summary: Dict[str, Any]
    status: Dict[str, Any]


def _new_run_id() -> str:
    return uuid.uuid4().hex


def build_daily_menu_plan(forecast_df: pd.DataFrame) -> pd.DataFrame:
    """Convert forecast rows into a menu-level daily plan."""
    df = forecast_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["baseline_qty"] = pd.to_numeric(df["pred_p50"], errors="coerce").fillna(0.0)
    df["special_added"] = 0
    df["qty_total"] = df["baseline_qty"]
    return df[["store_id", "date", "menu_item_id", "baseline_qty", "special_added", "qty_total", "pred_p10", "pred_p50", "pred_p90", "forecast_status"]].copy()


def generate_buy_advisories(reorder_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if reorder_df is None or len(reorder_df) == 0:
        return pd.DataFrame(columns=["store_id", "date", "advisory_type", "severity", "entity_type", "entity_id", "message", "recommended_action", "qty", "uom", "reason_code", "supporting_metrics_json"])

    buys = reorder_df[reorder_df["suggested_order_qty_final"] > 0].copy()
    rows = []
    for _, r in buys.iterrows():
        qty = float(r.get("suggested_order_qty_final", 0.0))
        rows.append(
            {
                "store_id": r["store_id"],
                "date": pd.to_datetime(r["date"]).date().isoformat(),
                "advisory_type": "BUY",
                "severity": "warning" if qty > 0 else "info",
                "entity_type": "ingredient",
                "entity_id": str(r["ingredient_id"]),
                "message": f"{pd.to_datetime(r['date']).date()}: BUY {int(round(qty))} {r['ingredient_id']} (reason: {r.get('order_reason','')}).",
                "recommended_action": "place_order",
                "qty": int(round(qty)),
                "uom": r.get("uom", None),
                "reason_code": r.get("order_reason", "below_ROP"),
                "supporting_metrics_json": r.get("supporting_metrics_json", "{}"),
            }
        )
    return pd.DataFrame(rows)


def build_forecast_summary(forecast_df: pd.DataFrame) -> Dict[str, Any]:
    # dashboard-friendly aggregate across all items for the first 14 days
    df = forecast_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    # aggregate by date
    agg = df.groupby("date", as_index=False).agg(
        pred_p50=("pred_p50", "sum"),
        pred_p10=("pred_p10", "sum"),
        pred_p90=("pred_p90", "sum"),
    )
    agg = agg.sort_values("date").head(14)
    points = [float(x) for x in agg["pred_p50"].tolist()]
    total = float(df["pred_p50"].sum()) if len(df) else 0.0
    lower_total = float(df["pred_p10"].sum()) if len(df) else 0.0
    upper_total = float(df["pred_p90"].sum()) if len(df) else 0.0
    avg = float(df["pred_p50"].mean()) if len(df) else 0.0
    return {
        "points": points,
        "total_forecast": int(round(total)),
        "avg_daily": round(avg, 2),
        "forecast_lower_total": int(round(lower_total)),
        "forecast_upper_total": int(round(upper_total)),
    }


def run_pipeline_mode_c(
    sales_fact: pd.DataFrame,
    *,
    recipe_fact: Optional[pd.DataFrame] = None,
    ingredient_dim: Optional[pd.DataFrame] = None,
    inventory_snapshot: Optional[pd.DataFrame] = None,
    horizon_days: int = 30,
    specials_policy: SpecialsPolicy = SpecialsPolicy(),
) -> PipelineOutputs:
    run_id = _new_run_id()

    # 1) Forecast demand (menu level)
    fc = forecast_menu_demand(sales_fact, horizon_days=horizon_days, use_quantiles=True)
    forecast_df = fc.forecast_df.copy()

    # 2) Build baseline menu plan
    daily_plan = build_daily_menu_plan(forecast_df)

    advisories_frames = []
    explanations: Dict[str, Any] = {"note": "v1 explanations: minimal", "drivers": []}

    ingredient_plan = None
    inventory_sim_df = None
    reorder_df = None

    status = {
        "forecast_status": "ok",
        "ingredient_plan_status": "skipped",
        "inventory_sim_status": "skipped",
        "reorder_status": "skipped",
        "specials_status": "skipped",
    }

    # Degrade gracefully if recipe map missing
    if recipe_fact is None or len(recipe_fact) == 0:
        advisories_frames.append(
            pd.DataFrame(
                [
                    {
                        "store_id": "all",
                        "date": pd.Timestamp.now().date().isoformat(),
                        "advisory_type": "DATA_QUALITY_WARNING",
                        "severity": "warning",
                        "entity_type": "store",
                        "entity_id": "all",
                        "message": "Recipe mapping missing; serving forecast-only outputs (no ingredient plan / reorders / specials).",
                        "recommended_action": "upload_recipe_fact",
                        "qty": None,
                        "uom": None,
                        "reason_code": "missing_recipe_fact",
                        "supporting_metrics_json": json.dumps({}),
                    }
                ]
            )
        )
        status["ingredient_plan_status"] = "missing_recipe_fact"
        summary = build_forecast_summary(forecast_df)
        advisories_df = pd.concat(advisories_frames, ignore_index=True) if advisories_frames else pd.DataFrame()
        return PipelineOutputs(
            run_id=run_id,
            forecast_df=forecast_df,
            daily_plan_df=daily_plan,
            ingredient_plan_df=None,
            inventory_sim_df=None,
            reorder_df=None,
            advisories_df=advisories_df,
            explanations=explanations,
            summary=summary,
            status=status,
        )

    # 3) Ingredient expansion
    ingredient_plan = expand_menu_to_ingredients(daily_plan, recipe_fact, ingredient_dim, qty_col="qty_total")
    status["ingredient_plan_status"] = "ok"

    # Degrade if inventory snapshot missing (skip reorder/specials)
    if inventory_snapshot is None or len(inventory_snapshot) == 0:
        advisories_frames.append(
            pd.DataFrame(
                [
                    {
                        "store_id": "all",
                        "date": pd.Timestamp.now().date().isoformat(),
                        "advisory_type": "DATA_QUALITY_WARNING",
                        "severity": "warning",
                        "entity_type": "store",
                        "entity_id": "all",
                        "message": "Inventory snapshot missing; serving ingredient demand but skipping inventory simulation and reorder/specials.",
                        "recommended_action": "upload_inventory_snapshot",
                        "qty": None,
                        "uom": None,
                        "reason_code": "missing_inventory_snapshot",
                        "supporting_metrics_json": json.dumps({}),
                    }
                ]
            )
        )
        status["inventory_sim_status"] = "missing_inventory_snapshot"
        summary = build_forecast_summary(forecast_df)
        advisories_df = pd.concat(advisories_frames, ignore_index=True) if advisories_frames else pd.DataFrame()
        return PipelineOutputs(
            run_id=run_id,
            forecast_df=forecast_df,
            daily_plan_df=daily_plan,
            ingredient_plan_df=ingredient_plan,
            inventory_sim_df=None,
            reorder_df=None,
            advisories_df=advisories_df,
            explanations=explanations,
            summary=summary,
            status=status,
        )

    # 4) Inventory simulation
    inventory_sim_df = simulate_inventory(ingredient_plan, inventory_snapshot, ingredient_dim)
    status["inventory_sim_status"] = "ok"

    # 5) Reorder calculations
    reorder_df = compute_reorder_plan(inventory_sim_df, ingredient_dim)
    status["reorder_status"] = "ok"
    advisories_frames.append(generate_buy_advisories(reorder_df))

    # 6) Specials recommendations + consistency recompute
    daily_plan2, specials_adv = recommend_specials(
        daily_plan, inventory_sim_df, recipe_fact, ingredient_dim, policy=specials_policy
    )
    if specials_adv is not None and len(specials_adv) > 0:
        status["specials_status"] = "ok"
        advisories_frames.append(specials_adv)
        # Recompute downstream from updated plan for internal consistency
        ingredient_plan2 = expand_menu_to_ingredients(daily_plan2, recipe_fact, ingredient_dim, qty_col="qty_total")
        inventory_sim2 = simulate_inventory(ingredient_plan2, inventory_snapshot, ingredient_dim)
        reorder2 = compute_reorder_plan(inventory_sim2, ingredient_dim)
        # Merge buy advisories from recomputed reorder (replace prior buys)
        advisories_frames = [df for df in advisories_frames if not (len(df) and "advisory_type" in df.columns and (df["advisory_type"] == "BUY").any())]
        advisories_frames.append(generate_buy_advisories(reorder2))
        # Replace outputs
        daily_plan = daily_plan2
        ingredient_plan = ingredient_plan2
        inventory_sim_df = inventory_sim2
        reorder_df = reorder2
    else:
        status["specials_status"] = "none"

    summary = build_forecast_summary(forecast_df)
    advisories_df = pd.concat([df for df in advisories_frames if df is not None and len(df) > 0], ignore_index=True) if advisories_frames else pd.DataFrame()

    return PipelineOutputs(
        run_id=run_id,
        forecast_df=forecast_df,
        daily_plan_df=daily_plan,
        ingredient_plan_df=ingredient_plan,
        inventory_sim_df=inventory_sim_df,
        reorder_df=reorder_df,
        advisories_df=advisories_df,
        explanations=explanations,
        summary=summary,
        status=status,
    )

