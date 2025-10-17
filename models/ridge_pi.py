from typing import Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.base import BaseEstimator


class ProbabilisticRegressor:
    """Wrapper that fits a point regressor and computes prediction intervals via residual bootstrap.

    Contract:
    - fit(X, y): fits internal model and stores residuals
    - predict(X): returns point predictions
    - predict_interval(X, alpha=0.05, n_boot=200): returns (lower, upper) arrays for (1-alpha) PI.

    This is simple and robust for small shops. For better calibrated quantiles consider lightGBM or quantile regression.
    """

    def __init__(self, base_model: Optional[BaseEstimator] = None, random_state: int = 0):
        self.base_model = base_model or Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=1.0))])
        self.random_state = random_state
        self._residuals = None

    def fit(self, X: pd.DataFrame, y: pd.Series):
        Xc = X.copy()
        self.base_model.fit(Xc, y)
        preds = self.base_model.predict(Xc)
        self._residuals = (y.values - preds)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.base_model.predict(X.copy())

    def predict_interval(self, X: pd.DataFrame, alpha: float = 0.05, n_boot: int = 500) -> Tuple[np.ndarray, np.ndarray]:
        """Compute (lower, upper) for (1-alpha) central interval using residual bootstrap.

        Note: Assumes residuals are iid; with time series this is an approximation. Block bootstrap could be used.
        """
        rng = np.random.default_rng(self.random_state)
        preds = self.predict(X)
        if self._residuals is None or len(self._residuals) == 0:
            raise RuntimeError("Model must be fit before calling predict_interval")
        sims = np.empty((n_boot, len(preds)))
        for i in range(n_boot):
            res_sample = rng.choice(self._residuals, size=len(preds), replace=True)
            sims[i, :] = preds + res_sample
        lower = np.quantile(sims, q=alpha/2, axis=0)
        upper = np.quantile(sims, q=1-alpha/2, axis=0)
        return lower, upper
