from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class CrostonModel:
    """Croston/SBA-style intermittent demand forecaster (simple, auditable fallback)."""

    alpha: float = 0.1
    method: str = "sba"  # "classic" | "sba"

    def fit_predict(self, y: np.ndarray, horizon: int) -> np.ndarray:
        y = np.asarray(y, dtype=float)
        y = np.where(np.isfinite(y), y, 0.0)
        n = len(y)
        if n == 0:
            return np.zeros(horizon, dtype=float)

        # initialize with first non-zero
        nz = np.where(y > 0)[0]
        if len(nz) == 0:
            return np.zeros(horizon, dtype=float)
        first = nz[0]
        z = y[first]  # demand size
        p = 1.0  # inter-arrival
        last_nz = first

        for t in range(first + 1, n):
            if y[t] > 0:
                z = z + self.alpha * (y[t] - z)
                interval = float(t - last_nz)
                p = p + self.alpha * (interval - p)
                last_nz = t

        f = z / max(p, 1e-6)
        if self.method.lower() == "sba":
            f = (1 - self.alpha / 2.0) * f
        return np.maximum(0.0, np.full(horizon, f, dtype=float))

