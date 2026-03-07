from datetime import date
import pandas as pd
from typing import List, Sequence, Optional


def is_thanksgiving_ts(ts: pd.Timestamp) -> int:
    first = date(ts.year, 11, 1)
    off = (3 - first.weekday()) % 7
    tg = pd.Timestamp(first) + pd.Timedelta(days=off) + pd.Timedelta(weeks=3)
    return int(ts.normalize() == tg.normalize())


def add_base_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add weekday, month, holiday flags, lags and rolling means.

    Assumptions:
    - input df must have a `date` column and a `qty_sold` column.
    - returns copy with new columns added.
    """
    f = df.copy()
    f["date"] = pd.to_datetime(f["date"])
    f = f.sort_values("date").reset_index(drop=True)
    f["dow"] = f["date"].dt.weekday
    f["month"] = f["date"].dt.month
    f["is_weekend"] = (f["dow"] >= 5).astype(int)
    f["is_xmas"] = ((f["date"].dt.month == 12) & (f["date"].dt.day == 25)).astype(int)
    f["is_july4"] = ((f["date"].dt.month == 7) & (f["date"].dt.day == 4)).astype(int)
    f["is_piday"] = ((f["date"].dt.month == 3) & (f["date"].dt.day == 14)).astype(int)
    f["is_thanksgiving"] = f["date"].apply(lambda x: is_thanksgiving_ts(pd.Timestamp(x))).astype(int)
    # lags/rolls
    f["lag_1"] = f["qty_sold"].shift(1)
    f["lag_7"] = f["qty_sold"].shift(7)
    f["roll7"] = f["qty_sold"].shift(1).rolling(7, min_periods=1).mean()
    f["roll28"] = f["qty_sold"].shift(1).rolling(28, min_periods=1).mean()
    return f


def add_grouped_time_features(
    df: pd.DataFrame,
    *,
    date_col: str = "date",
    target_col: str = "qty_sold",
    group_cols: Sequence[str] = ("store_id", "menu_item_id"),
    lags: Sequence[int] = (1, 7, 14, 28),
    rolling_windows: Sequence[int] = (7, 28),
    min_periods: int = 3,
) -> pd.DataFrame:
    """Leak-safe feature builder for pooled restaurant forecasting.

    Produces calendar features + per-series lags and rolling stats using *only* prior values:
    - lag_k uses shift(k)
    - rolling_{w} uses shift(1).rolling(w)
    """
    f = df.copy()
    f[date_col] = pd.to_datetime(f[date_col])
    f = f.sort_values(list(group_cols) + [date_col]).reset_index(drop=True)

    # calendar features
    f["dow"] = f[date_col].dt.weekday
    f["month"] = f[date_col].dt.month
    f["weekofyear"] = f[date_col].dt.isocalendar().week.astype(int)
    f["quarter"] = f[date_col].dt.quarter
    f["is_weekend"] = (f["dow"] >= 5).astype(int)
    f["is_xmas"] = ((f[date_col].dt.month == 12) & (f[date_col].dt.day == 25)).astype(int)
    f["is_july4"] = ((f[date_col].dt.month == 7) & (f[date_col].dt.day == 4)).astype(int)
    f["is_piday"] = ((f[date_col].dt.month == 3) & (f[date_col].dt.day == 14)).astype(int)
    f["is_thanksgiving"] = f[date_col].apply(lambda x: is_thanksgiving_ts(pd.Timestamp(x))).astype(int)

    # lags + rolling per series
    gb = f.groupby(list(group_cols), sort=False)[target_col]
    for k in lags:
        f[f"lag_{k}"] = gb.shift(k)

    def _add_rolls(g: pd.DataFrame) -> pd.DataFrame:
        s = g[target_col].shift(1)
        out = pd.DataFrame(index=g.index)
        for w in rolling_windows:
            out[f"roll_mean_{w}"] = s.rolling(w, min_periods=1).mean()
            out[f"roll_std_{w}"] = s.rolling(w, min_periods=min_periods).std(ddof=1).fillna(0.0)
        out["is_zero"] = (g[target_col].fillna(0) <= 0).astype(int)
        out["zero_ratio_28"] = out["is_zero"].shift(1).rolling(28, min_periods=7).mean()
        return out

    # include_groups=False avoids pandas future behavior changes
    rolls = f.groupby(list(group_cols), sort=False, group_keys=False).apply(_add_rolls, include_groups=False)
    f = f.join(rolls)

    return f
