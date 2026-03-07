from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from features.builders import add_grouped_time_features
from models.croston import CrostonModel
from models.pooled_poisson_gbm import PooledPoissonGBM
from models.quantile_gbm import QuantileGBM
from models.routing import classify_sales_fact
from models.seasonal_naive import seasonal_naive_forecast


DEFAULT_FEATURE_COLS = [
    "dow",
    "month",
    "weekofyear",
    "quarter",
    "is_weekend",
    "is_xmas",
    "is_july4",
    "is_piday",
    "is_thanksgiving",
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "roll_mean_7",
    "roll_mean_28",
    "roll_std_7",
    "roll_std_28",
    "zero_ratio_28",
]


@dataclass(frozen=True)
class ForecastResult:
    forecast_df: pd.DataFrame
    routing_df: pd.DataFrame
    feature_columns: List[str]


def _build_future_grid(sales_fact: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    """Build a future date grid per (store_id, menu_item_id) starting after last observed date."""
    df = sales_fact.copy()
    df["date"] = pd.to_datetime(df["date"])
    last_dates = df.groupby(["store_id", "menu_item_id"])["date"].max().reset_index()
    rows = []
    for _, r in last_dates.iterrows():
        for h in range(horizon_days):
            rows.append(
                {
                    "store_id": r["store_id"],
                    "menu_item_id": r["menu_item_id"],
                    "date": pd.to_datetime(r["date"]) + pd.Timedelta(days=h + 1),
                    "qty_sold": np.nan,  # placeholder
                }
            )
    return pd.DataFrame(rows)


def forecast_menu_demand(
    sales_fact: pd.DataFrame,
    *,
    horizon_days: int = 30,
    use_quantiles: bool = True,
) -> ForecastResult:
    """Produce store×date×menu_item forecasts with p10/p50/p90 and graceful fallbacks."""
    sales = sales_fact.copy()
    sales["date"] = pd.to_datetime(sales["date"])
    sales = sales.sort_values(["store_id", "menu_item_id", "date"]).reset_index(drop=True)

    routing = classify_sales_fact(sales)

    # Always compute baseline; we may blend or fallback to it per series.
    baseline = seasonal_naive_forecast(sales, horizon_days=horizon_days)

    # Build pooled features on historical rows for training.
    feats = add_grouped_time_features(sales, date_col="date", target_col="qty_sold")
    train = feats.dropna(subset=["lag_28"]).copy()  # ensure enough history for lag features
    if len(train) < 50:
        # Too little data globally → baseline only
        out = baseline.copy()
        out["forecast_status"] = "fallback_baseline_insufficient_training_data"
        return ForecastResult(forecast_df=out, routing_df=routing, feature_columns=DEFAULT_FEATURE_COLS)

    X_train = train
    y_train = train["qty_sold"]

    # Fit pooled models; if failure, return baseline.
    try:
        mean_model = PooledPoissonGBM()
        mean_model.fit(X_train, y_train, feature_columns=DEFAULT_FEATURE_COLS)

        q10 = QuantileGBM(quantile=0.10)
        q50 = QuantileGBM(quantile=0.50)
        q90 = QuantileGBM(quantile=0.90)
        if use_quantiles:
            q10.fit(X_train, y_train, feature_columns=DEFAULT_FEATURE_COLS)
            q50.fit(X_train, y_train, feature_columns=DEFAULT_FEATURE_COLS)
            q90.fit(X_train, y_train, feature_columns=DEFAULT_FEATURE_COLS)
        else:
            q10 = q50 = q90 = None
    except Exception:
        out = baseline.copy()
        out["forecast_status"] = "fallback_baseline_training_failed"
        return ForecastResult(forecast_df=out, routing_df=routing, feature_columns=DEFAULT_FEATURE_COLS)

    # Autoregressive multi-step forecast per series (simple recursion).
    future_grid = _build_future_grid(sales, horizon_days=horizon_days)
    combined = pd.concat([sales[["store_id", "menu_item_id", "date", "qty_sold"]], future_grid], ignore_index=True)
    combined = combined.sort_values(["store_id", "menu_item_id", "date"]).reset_index(drop=True)

    preds_rows = []
    for (store_id, item_id), g in combined.groupby(["store_id", "menu_item_id"], sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        hist_len = int(g["qty_sold"].notna().sum())
        series_kind = routing[(routing["store_id"] == store_id) & (routing["menu_item_id"] == item_id)]["series_kind"]
        series_kind = series_kind.iloc[0] if len(series_kind) else "regular"

        # Intermittent / cold-start handling: Croston/SBA (intermittent) or baseline (cold_start/inactive)
        if series_kind == "intermittent":
            cm = CrostonModel(alpha=0.1, method="sba")
            hist_y = pd.to_numeric(g.loc[: hist_len - 1, "qty_sold"], errors="coerce").fillna(0.0).values if hist_len > 0 else np.array([])
            p50 = cm.fit_predict(hist_y, horizon=horizon_days)
            last_date = pd.to_datetime(g.loc[hist_len - 1, "date"]) if hist_len > 0 else pd.Timestamp.now().normalize()
            rows = []
            for i in range(horizon_days):
                rows.append(
                    {
                        "store_id": store_id,
                        "date": last_date + pd.Timedelta(days=i + 1),
                        "menu_item_id": item_id,
                        "pred_p50": float(p50[i]),
                        "pred_p10": float(max(0.0, p50[i] * 0.7)),
                        "pred_p90": float(p50[i] * 1.4),
                        "forecast_status": "fallback_croston_sba",
                    }
                )
            preds_rows.append(pd.DataFrame(rows)[["store_id", "date", "menu_item_id", "pred_p10", "pred_p50", "pred_p90", "forecast_status"]])
            continue

        # Start with known history
        work = g.copy()
        # Predict one step at a time so lag features can use prior preds.
        for step in range(horizon_days):
            idx = hist_len + step
            if idx >= len(work):
                break
            tmp = add_grouped_time_features(work.iloc[: idx + 1], date_col="date", target_col="qty_sold")
            row = tmp.iloc[-1:].copy()

            # If series is intermittent/cold_start, prefer baseline / croston
            if series_kind in ("intermittent", "cold_start", "inactive"):
                # baseline already computed; just skip modeling here
                yhat = np.nan
            else:
                yhat = float(mean_model.predict(row)[0])

            # Fill missing/NaN with baseline later
            if not np.isfinite(yhat):
                yhat = np.nan
            work.at[idx, "qty_sold"] = yhat

        # Build forecast output for this series from the future window
        future_part = work.iloc[hist_len : hist_len + horizon_days].copy()
        future_part["store_id"] = store_id
        future_part["menu_item_id"] = item_id
        future_part["pred_p50"] = pd.to_numeric(future_part["qty_sold"], errors="coerce")
        future_part["forecast_status"] = "ml_pooled_poisson"

        # Quantiles: if enabled, compute using quantile models on the final feature rows (non-recursive approximation).
        if use_quantiles and q10 and q50 and q90:
            # rebuild features using filled recursion values for lag computation
            tmp_all = add_grouped_time_features(work, date_col="date", target_col="qty_sold")
            future_feats = tmp_all.iloc[hist_len : hist_len + horizon_days].copy()
            future_part["pred_p10"] = q10.predict(future_feats)
            future_part["pred_p50"] = q50.predict(future_feats)
            future_part["pred_p90"] = q90.predict(future_feats)
        else:
            future_part["pred_p10"] = future_part["pred_p50"] * 0.8
            future_part["pred_p90"] = future_part["pred_p50"] * 1.2

        preds_rows.append(future_part[["store_id", "date", "menu_item_id", "pred_p10", "pred_p50", "pred_p90", "forecast_status"]])

    ml_forecast = pd.concat(preds_rows, ignore_index=True) if preds_rows else pd.DataFrame()

    # Merge ML with baseline for intermittent/cold_start series and any missing predictions.
    out = baseline.merge(ml_forecast, on=["store_id", "date", "menu_item_id"], how="left", suffixes=("_base", ""))
    for col in ("pred_p10", "pred_p50", "pred_p90"):
        out[col] = out[col].where(out[col].notna(), out[f"{col}_base"])
    out["forecast_status"] = out["forecast_status"].where(out["forecast_status"].notna(), out["forecast_status_base"])
    out = out[["store_id", "date", "menu_item_id", "pred_p10", "pred_p50", "pred_p90", "forecast_status"]].copy()

    # Clamp
    for col in ("pred_p10", "pred_p50", "pred_p90"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).clip(lower=0.0)

    return ForecastResult(forecast_df=out, routing_df=routing, feature_columns=DEFAULT_FEATURE_COLS)

