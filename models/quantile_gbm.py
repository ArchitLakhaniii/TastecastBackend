from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


@dataclass
class QuantileGBM:
    """Quantile forecaster using scikit-learn HGBR(loss='quantile')."""

    quantile: float
    max_depth: Optional[int] = 6
    learning_rate: float = 0.06
    max_iter: int = 400
    random_state: int = 0

    model: Optional[HistGradientBoostingRegressor] = None
    feature_columns: Optional[List[str]] = None
    _store_codes: Optional[Dict[str, int]] = None
    _item_codes: Optional[Dict[str, int]] = None

    def _encode_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if self._store_codes is None:
            stores = sorted(out["store_id"].astype(str).unique().tolist())
            self._store_codes = {s: i for i, s in enumerate(stores)}
        if self._item_codes is None:
            items = sorted(out["menu_item_id"].astype(str).unique().tolist())
            self._item_codes = {s: i for i, s in enumerate(items)}
        out["store_code"] = out["store_id"].astype(str).map(self._store_codes).fillna(-1).astype(int)
        out["item_code"] = out["menu_item_id"].astype(str).map(self._item_codes).fillna(-1).astype(int)
        return out

    def fit(self, feats: pd.DataFrame, y: pd.Series, feature_columns: Sequence[str]) -> "QuantileGBM":
        X = self._encode_ids(feats)
        cols = list(feature_columns) + ["store_code", "item_code"]
        self.feature_columns = cols
        X = X[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        yv = pd.to_numeric(y, errors="coerce").fillna(0.0).clip(lower=0.0)

        self.model = HistGradientBoostingRegressor(
            loss="quantile",
            quantile=float(self.quantile),
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            max_iter=self.max_iter,
            random_state=self.random_state,
        )
        self.model.fit(X, yv)
        return self

    def predict(self, feats: pd.DataFrame) -> np.ndarray:
        if self.model is None or self.feature_columns is None:
            raise RuntimeError("Model not fit")
        X = self._encode_ids(feats)
        X = X[self.feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        pred = self.model.predict(X)
        return np.maximum(0.0, pred.astype(float))

