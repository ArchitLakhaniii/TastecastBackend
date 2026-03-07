from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SeriesClass:
    kind: str  # "dense" | "regular" | "intermittent" | "cold_start" | "inactive"
    reason: str


def classify_series(y: pd.Series) -> SeriesClass:
    """Classify a demand series for model routing (spec §18, §26)."""
    yy = pd.to_numeric(y, errors="coerce").fillna(0.0).clip(lower=0.0).values
    n = len(yy)
    if n < 14:
        return SeriesClass(kind="cold_start", reason="too_few_observations")

    zero_ratio = float(np.mean(yy <= 0))
    nonzero = yy[yy > 0]
    nonzero_n = int(len(nonzero))

    if nonzero_n == 0:
        return SeriesClass(kind="inactive", reason="all_zero")
    if zero_ratio > 0.4 or nonzero_n < 60:
        return SeriesClass(kind="intermittent", reason=f"zero_ratio={zero_ratio:.2f}, nonzero_n={nonzero_n}")
    if n >= 180 and zero_ratio < 0.2:
        return SeriesClass(kind="dense", reason=f"n={n}, zero_ratio={zero_ratio:.2f}")
    return SeriesClass(kind="regular", reason=f"n={n}, zero_ratio={zero_ratio:.2f}")


def classify_sales_fact(sales_fact: pd.DataFrame) -> pd.DataFrame:
    """Return per (store_id, menu_item_id) routing metadata."""
    rows = []
    df = sales_fact.copy().sort_values(["store_id", "menu_item_id", "date"])
    for (store_id, item_id), g in df.groupby(["store_id", "menu_item_id"], sort=False):
        cls = classify_series(g["qty_sold"])
        rows.append(
            {
                "store_id": store_id,
                "menu_item_id": item_id,
                "series_kind": cls.kind,
                "series_reason": cls.reason,
                "n_obs": int(len(g)),
                "zero_ratio": float((pd.to_numeric(g["qty_sold"], errors="coerce").fillna(0.0) <= 0).mean()),
            }
        )
    return pd.DataFrame(rows)

