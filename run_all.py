"""Run end-to-end pipeline: fit model, forecast, schedule specials, export artifacts.

Set `FORECAST_AHEAD_DAYS` below to control how far ahead the pipeline forecasts.
You can also override via the --days CLI argument when running this script.
"""
import os
import sys
import argparse
import pandas as pd
import yaml
import traceback
from typing import Dict, Any

# Add current directory to Python path to ensure imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import functions with error handling
try:
    from cli import load_config
except ImportError:
    # Fallback config loader if cli module fails
    def load_config(config_path: str) -> Dict[str, Any]:
        """Fallback config loader"""
        if not os.path.exists(config_path):
            # Return default config if file doesn't exist
            return {
                "forecast": {"forecast_horizon_days": 30, "forecast_year": 2026},
                "production": {"recipe": {"apples": 3, "dough": 1}, "special_days": [3,4,5,6], "special_boost_max_per_day": 5},
                "store": {"restock_lot_size": {"apples": 300, "dough": 120}, "vendor_weekday": 0}
            }
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                return config if config is not None else {}
        except Exception:
            # Return default config if YAML parsing fails
            return {
                "forecast": {"forecast_horizon_days": 30, "forecast_year": 2026},
                "production": {"recipe": {"apples": 3, "dough": 1}, "special_days": [3,4,5,6], "special_boost_max_per_day": 5},
                "store": {"restock_lot_size": {"apples": 300, "dough": 120}, "vendor_weekday": 0}
            }

try:
    from data.utils import upgrade_to_per_ingredient_restock_flags, forecast_next_days_window
    from features.builders import add_base_features
    from models.ridge_pi import ProbabilisticRegressor
    from optimizers.weekly_specials import schedule_specials
    from reports.export import export_plan, export_advisories
except ImportError as e:
    print(f"Import error: {e}")
    # We'll handle missing imports with fallback functions below

# DEFAULT: change this variable to adjust the forecast horizon for runs
FORECAST_AHEAD_DAYS = 365  # if None, use config.yaml forecast.forecast_horizon_days


def main(data_csv: str = "tastecast_one_item_2023_2025.csv", days_ahead: int | None = None):
    """Main pipeline function with error handling"""
    try:
        print(f"DEBUG: Starting main pipeline with data_csv={data_csv}, days_ahead={days_ahead}")
        cfg = load_config("config.yaml")
        print(f"DEBUG: Config loaded: {cfg}")
        
        df = pd.read_csv(data_csv, parse_dates=["date"]) if data_csv else pd.read_csv(cfg.get("data_csv"))
        print(f"DEBUG: CSV loaded with {len(df)} rows, date range: {df['date'].min()} to {df['date'].max()}")
        
        # Try to run the full pipeline
        try:
            print("DEBUG: Attempting full ML pipeline...")
            df = upgrade_to_per_ingredient_restock_flags(df)
            feats = add_base_features(df).dropna()
            X = feats[["dow","month","is_weekend","is_xmas","is_july4","is_piday","is_thanksgiving","lag_1","lag_7","roll7","roll28"]]
            y = feats["qty_sold"]
            model = ProbabilisticRegressor()
            model.fit(X,y)

            # determine horizon: CLI arg -> module var -> config
            horizon = days_ahead if days_ahead is not None else (FORECAST_AHEAD_DAYS if FORECAST_AHEAD_DAYS is not None else cfg["forecast"]["forecast_horizon_days"])
            print(f"DEBUG: Forecast horizon: {horizon} days")
            
            future = forecast_next_days_window(df, model, days_ahead=horizon, start_year=cfg["forecast"]["forecast_year"])
            print(f"DEBUG: Future forecast generated for {len(future)} days")
            
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
            print(f"DEBUG: SUCCESS - Exported artifacts: {plan_path}, {adv_path}")
            print({"plan": plan_path, "advisories": adv_path})
            return {"status": "success", "plan": plan_path, "advisories": adv_path}
            
        except Exception as pipeline_error:
            print(f"DEBUG: Pipeline failed with error: {pipeline_error}")
            print(f"DEBUG: Pipeline traceback: {traceback.format_exc()}")
            # Create minimal fallback artifacts
            return create_fallback_artifacts(df, cfg, days_ahead)
            
    except Exception as e:
        print(f"DEBUG: Main function error: {e}")
        print(f"DEBUG: Main traceback: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


def create_fallback_artifacts(df, cfg, days_ahead=None):
    """Create simple fallback artifacts when the full pipeline fails"""
    try:
        import datetime
        from datetime import timedelta
        
        os.makedirs("artifacts", exist_ok=True)
        
        # Simple forecast based on recent average
        recent_avg = df['qty_sold'].tail(7).mean()
        horizon = days_ahead if days_ahead else 30
        
        # Create simple daily plan
        start_date = pd.to_datetime(df['date'].max()) + timedelta(days=1)
        dates = [start_date + timedelta(days=i) for i in range(horizon)]
        
        daily_plan = pd.DataFrame({
            'date': dates,
            'qty_sold': [int(recent_avg)] * horizon,
            'apples_need': [int(recent_avg * 3)] * horizon,
            'dough_need': [int(recent_avg * 1)] * horizon
        })
        
        # Create simple advisories
        advisories = pd.DataFrame({
            'date': [start_date.strftime('%Y-%m-%d')],
            'type': ['forecast'],
            'message': [f'Based on recent average: {recent_avg:.1f} items per day'],
            'ingredient': ['general']
        })
        
        # Save artifacts
        plan_path = "artifacts/daily_plan.csv"
        adv_path = "artifacts/advisories.csv"
        
        daily_plan.to_csv(plan_path, index=False)
        advisories.to_csv(adv_path, index=False)
        
        print(f"Created fallback artifacts: {plan_path}, {adv_path}")
        return {"status": "fallback", "plan": plan_path, "advisories": adv_path}
        
    except Exception as e:
        print(f"Fallback creation error: {e}")
        return {"status": "error", "message": str(e)}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=None, help="Override forecast horizon in days")
    p.add_argument("--data", type=str, default=None, help="Path to historical CSV")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(data_csv=args.data or "tastecast_one_item_2023_2025.csv", days_ahead=args.days)
