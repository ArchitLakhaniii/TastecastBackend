import pandas as pd
from typing import Tuple


def export_plan(plan_df: pd.DataFrame, path: str) -> str:
    # ensure parent directory exists
    import os
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    # Make an operator-friendly copy: integer quantities for visible columns
    op = plan_df.copy()
    # integer columns expected by operators
    for col in [c for c in op.columns if c in ("qty_total", "special_added") or c.endswith("_need")]:
        try:
            op[col] = op[col].astype(int)
        except Exception:
            # fallback: round then cast
            op[col] = op[col].round().fillna(0).astype(int)

    op.to_csv(path, index=False)
    return path


def export_advisories(adv_df: pd.DataFrame, path: str) -> str:
    import os
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    # Operator-facing advisories: ensure integer quantities where appropriate
    op = adv_df.copy()
    if "qty" in op.columns:
        # qty is BUY qty — coerce to nullable integer safely
        op["qty"] = pd.to_numeric(op["qty"], errors="coerce").astype("Int64")
    if "special_qty" in op.columns:
        # special_qty should be integer (0 when missing for BUY rows)
        op["special_qty"] = pd.to_numeric(op["special_qty"], errors="coerce").fillna(0).astype(int)

    # Round pred_* for operator CSV to 1 decimal to avoid confusing decimals
    for col in ("pred_mean", "pred_lower", "pred_upper"):
        if col in op.columns:
            try:
                op[col] = op[col].round(1)
            except Exception:
                pass

    op.to_csv(path, index=False)
    return path
