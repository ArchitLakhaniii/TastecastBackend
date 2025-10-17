import matplotlib.pyplot as plt
import pandas as pd
from typing import Optional


def plot_backtest(hist: pd.DataFrame, pred: pd.DataFrame, col_date: str = "date", col_true: str = "qty_sold", col_pred: str = "pred", out_png: Optional[str] = None):
    df = hist.merge(pred[[col_date, col_pred]], on=col_date, how="left")
    df[col_date] = pd.to_datetime(df[col_date])
    plt.figure(figsize=(10,4))
    plt.plot(df[col_date], df[col_true], label="actual")
    plt.plot(df[col_date], df[col_pred], label="pred")
    plt.legend()
    plt.tight_layout()
    if out_png:
        plt.savefig(out_png)
    return plt

