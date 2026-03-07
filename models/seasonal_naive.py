from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SeasonalNaiveModel:
    """Simple seasonal-naive baseline: same day last week, with fallback to rolling mean."""

    seasonality_days: int = 7
    fallback_window: int = 28

    def predict_series(self, hist: pd.Series, horizon: int) -> np.ndarray:
        y = pd.to_numeric(hist, errors="coerce").fillna(0.0).astype(float).values
        out = np.zeros(horizon, dtype=float)
        for h in range(horizon):
            idx = len(y) - self.seasonality_days + h
            if idx >= 0 and idx < len(y):
                out[h] = max(0.0, float(y[idx]))
            else:
                tail = y[max(0, len(y) - self.fallback_window) :]
                out[h] = max(0.0, float(np.mean(tail)) if len(tail) else 0.0)
        return out


def seasonal_naive_forecast(
    sales_fact: pd.DataFrame,
    *,
    date_col: str = "date",
    group_cols: tuple[str, str] = ("store_id", "menu_item_id"),
    target_col: str = "qty_sold",
    horizon_days: int = 30,
) -> pd.DataFrame:
    df = sales_fact.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(list(group_cols) + [date_col]).reset_index(drop=True)
    model = SeasonalNaiveModel()

    rows = []
    for (store_id, item_id), g in df.groupby(list(group_cols), sort=False):
        g = g.sort_values(date_col)
        hist_y = g[target_col]
        last_date = pd.to_datetime(g[date_col].max())
        preds = model.predict_series(hist_y, horizon=horizon_days)
        for i in range(horizon_days):
            d = last_date + pd.Timedelta(days=i + 1)
            rows.append(
                {
                    "store_id": store_id,
                    "date": d,
                    "menu_item_id": item_id,
                    "pred_p50": float(preds[i]),
                    "pred_p10": float(max(0.0, preds[i] * 0.8)),
                    "pred_p90": float(preds[i] * 1.2),
                    "forecast_status": "baseline_seasonal_naive",
                }
            )
    return pd.DataFrame(rows)

