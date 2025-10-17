import numpy as np
import pandas as pd


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    mask = denom == 0
    denom[mask] = 1.0
    return float(np.mean(np.abs(y_true - y_pred) / denom))


def mase(y_true: np.ndarray, y_pred: np.ndarray, y_train: np.ndarray, m: int = 1) -> float:
    # Mean Absolute Scaled Error using seasonal naive with seasonality m
    n = len(y_train)
    d = np.mean(np.abs(y_train[m:] - y_train[:-m]))
    errors = np.abs(y_true - y_pred)
    if d == 0:
        return float(np.mean(errors))
    return float(np.mean(errors) / d)
