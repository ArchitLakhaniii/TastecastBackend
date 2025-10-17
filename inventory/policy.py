from typing import Dict, Iterable, Tuple
import numpy as np


class RecipeMatrix:
    """Simple recipe matrix mapping ingredient -> units per item.

    Accepts either a dict like {"apples":3, "dough":1} or a DataFrame-like mapping.
    """
    def __init__(self, mapping: Dict[str, float]):
        self.mapping = dict(mapping)

    def ingredients(self) -> Iterable[str]:
        return list(self.mapping.keys())

    def needed_for_items(self, n_items: int) -> Dict[str, float]:
        return {k: v * n_items for k, v in self.mapping.items()}


def z_from_service_level(sl: float) -> float:
    """Return z-score corresponding to service level using scipy's normal ppf.

    Requires scipy in the environment (added to requirements.txt).
    """
    from scipy.stats import norm

    return float(norm.ppf(sl))


def compute_safety_stock(daily_demand_std: float, lead_time_days: int, service_level: float) -> float:
    """Compute safety stock (units) using normal-approximation.

    Formula: safety = z * sigma_daily * sqrt(lead_time_days)
    where z is the normal deviate for the target service level.
    """
    safety = z_from_service_level(service_level) * float(daily_demand_std) * (lead_time_days ** 0.5)
    return float(max(0.0, safety))


def compute_reorder_point(avg_daily_demand: float, lead_time_days: int, safety_stock: float) -> float:
    return avg_daily_demand * lead_time_days + safety_stock


def round_up_lot(qty: float, lot_size: int) -> int:
    """Round qty up to nearest lot size. If lot_size <= 0, return ceil(qty)."""
    import math
    if lot_size and lot_size > 0:
        return int(math.ceil(qty / lot_size) * lot_size)
    return int(math.ceil(qty))


def normalize_weekdays(days) -> list:
    """Accept ints 0-6 or strings like 'Mon','Thu' and return list of ints 0..6.

    Invalid entries are ignored.
    """
    mapping = {"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}
    out = []
    if isinstance(days, (list, tuple)):
        for d in days:
            if isinstance(d, int) and 0 <= d <= 6:
                out.append(d)
            elif isinstance(d, str):
                key = d.strip()[:3].lower()
                if key in mapping:
                    out.append(mapping[key])
    return sorted(list(set(out)))


def rolling_std_proxy(series, window=7, min_periods=3):
    """Compute rolling std with fallback: if too short, use 25% of rolling mean as proxy."""
    import numpy as np
    s = series.rolling(window=window, min_periods=1)
    std = s.std(ddof=1)
    mean = s.mean()
    proxy = std.fillna(0)
    mask = proxy < 1e-6
    proxy[mask] = (mean[mask] * 0.25).fillna(1.0)
    return proxy
