"""Run end-to-end pipeline: fit model, forecast, schedule specials, export artifacts.

Set `FORECAST_AHEAD_DAYS` below to control how far ahead the pipeline forecasts.
You can also override via the --days CLI argument when running this script.
"""
import os
import argparse
import pandas as pd

from cli import load_config
from data.utils import upgrade_to_per_ingredient_restock_flags, forecast_next_days_window
from features.builders import add_base_features
from models.ridge_pi import ProbabilisticRegressor
from optimizers.weekly_specials import schedule_specials
from reports.export import export_plan, export_advisories

# DEFAULT: change this variable to adjust the forecast horizon for runs
FORECAST_AHEAD_DAYS = 365  # if None, use config.yaml forecast.forecast_horizon_days


def main(data_csv: str = "tastecast_one_item_2023_2025.csv", days_ahead: int | None = None):
    cfg = load_config("config.yaml")
    df = pd.read_csv(data_csv, parse_dates=["date"]) if data_csv else pd.read_csv(cfg.get("data_csv"))
    df = upgrade_to_per_ingredient_restock_flags(df)

    feats = add_base_features(df).dropna()
    X = feats[["dow","month","is_weekend","is_xmas","is_july4","is_piday","is_thanksgiving","lag_1","lag_7","roll7","roll28"]]
    y = feats["qty_sold"]
    model = ProbabilisticRegressor()
    model.fit(X,y)

    # determine horizon: CLI arg -> module var -> config
    horizon = days_ahead if days_ahead is not None else (FORECAST_AHEAD_DAYS if FORECAST_AHEAD_DAYS is not None else cfg["forecast"]["forecast_horizon_days"])
    future = forecast_next_days_window(df, model, days_ahead=horizon, start_year=cfg["forecast"]["forecast_year"])
    # base plan
    future["qty_total"] = future["qty_sold"]
    recipe = cfg["production"]["recipe"]
    for ing, per in recipe.items():
        future[f"{ing}_need"] = future["qty_total"] * per

    # schedule specials and advisories
    restock_lots = cfg["store"].get("restock_lot_size", {})
    vendor_weekday = cfg["store"].get("vendor_weekday", None)
    plan_df, adv_df = schedule_specials(future, recipe, cfg["production"]["special_days"], cfg["production"]["special_boost_max_per_day"], start_stocks=None, restock_lot_sizes=restock_lots, vendor_weekday=vendor_weekday)

    # export artifacts
    os.makedirs("artifacts", exist_ok=True)
    plan_path = export_plan(plan_df, "artifacts/daily_plan.csv")
    adv_path = export_advisories(adv_df, "artifacts/advisories.csv")
    print({"plan": plan_path, "advisories": adv_path})


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=None, help="Override forecast horizon in days")
    p.add_argument("--data", type=str, default=None, help="Path to historical CSV")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(data_csv=args.data or "tastecast_one_item_2023_2025.csv", days_ahead=args.days)
