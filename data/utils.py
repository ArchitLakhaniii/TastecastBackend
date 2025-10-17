from typing import Dict
import pandas as pd
import numpy as np
from features.builders import add_base_features


def upgrade_to_per_ingredient_restock_flags(df: pd.DataFrame) -> pd.DataFrame:
    if {"restocked_apples","restocked_dough"}.issubset(df.columns):
        return df.copy()
    df = df.sort_values("date").reset_index(drop=True).copy()
    restocked_apples = [0]
    restocked_dough  = [0]
    for i in range(1, len(df)):
        restocked_apples.append(int(df.loc[i,"apples_start"] > df.loc[i-1,"apples_end"]))
        restocked_dough.append(int(df.loc[i,"dough_start"]  > df.loc[i-1,"dough_end"]))
    df["restocked_apples"] = restocked_apples
    df["restocked_dough"]  = restocked_dough
    return df


def forecast_next_days_window(df_all: pd.DataFrame, model, days_ahead: int, start_year: int = 2026) -> pd.DataFrame:
    hist = df_all[["date","qty_sold"]].copy().sort_values("date").reset_index(drop=True)
    start_date = pd.to_datetime(hist["date"].max()) + pd.Timedelta(days=1)
    end_cutoff = pd.Timestamp(f"{start_year}-12-31")
    end_date = min(start_date + pd.Timedelta(days=days_ahead-1), end_cutoff)
    out, work, current_date = [], hist.copy(), start_date
    # if model supports intervals, prepare to call predict_interval; else fallback
    supports_pi = hasattr(model, "predict_interval")
    while current_date <= end_date:
        tmp = pd.concat([work, pd.DataFrame([{"date": current_date}])], ignore_index=True)
        tmp = add_base_features(tmp).iloc[-1:]
        X = tmp[["dow","month","is_weekend","is_xmas","is_july4","is_piday","is_thanksgiving","lag_1","lag_7","roll7","roll28"]]
        yhat = float(model.predict(X).item())
        if supports_pi:
            try:
                lower, upper = model.predict_interval(X)
                lower = float(lower.item())
                upper = float(upper.item())
            except Exception:
                lower, upper = yhat, yhat
        else:
            lower, upper = yhat, yhat
        qty = max(0, int(round(yhat)))
        out.append({
            "date": current_date,
            "qty_sold": qty,
            "pred_mean": yhat,
            "pred_lower": lower,
            "pred_upper": upper,
        })
        work = pd.concat([work, pd.DataFrame([{"date": current_date, "qty_sold": qty}])], ignore_index=True)
        current_date += pd.Timedelta(days=1)
    return pd.DataFrame(out)
