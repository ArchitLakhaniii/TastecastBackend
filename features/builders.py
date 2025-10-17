from datetime import date
import pandas as pd
from typing import List


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
