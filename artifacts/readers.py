from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import pandas as pd

from artifacts.writers import run_dir


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_run_artifacts(run_id: str, base_dir: str = "artifacts/runs") -> Dict[str, Any]:
    base = run_dir(run_id, base_dir=base_dir)
    if not os.path.exists(base):
        raise FileNotFoundError(f"run_id not found: {run_id}")

    out: Dict[str, Any] = {"run_id": run_id}
    daily_plan_path = os.path.join(base, "daily_plan.csv")
    advisories_path = os.path.join(base, "advisories.csv")
    forecast_path = os.path.join(base, "forecast.csv")
    ingredient_plan_path = os.path.join(base, "ingredient_plan.csv")
    summary_path = os.path.join(base, "forecast_summary.json")
    explanations_path = os.path.join(base, "explanations.json")
    status_path = os.path.join(base, "status.json")

    out["daily_plan_df"] = pd.read_csv(daily_plan_path) if os.path.exists(daily_plan_path) else None
    out["advisories_df"] = pd.read_csv(advisories_path) if os.path.exists(advisories_path) else None
    out["forecast_df"] = pd.read_csv(forecast_path) if os.path.exists(forecast_path) else None
    out["ingredient_plan_df"] = pd.read_csv(ingredient_plan_path) if os.path.exists(ingredient_plan_path) else None
    out["forecast_summary"] = _read_json(summary_path) if os.path.exists(summary_path) else None
    out["explanations"] = _read_json(explanations_path) if os.path.exists(explanations_path) else None
    out["status"] = _read_json(status_path) if os.path.exists(status_path) else None
    return out


def find_latest_run_id(base_dir: str = "artifacts/runs") -> Optional[str]:
    if not os.path.exists(base_dir):
        return None
    dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    if not dirs:
        return None
    # newest by mtime
    dirs.sort(key=lambda d: os.path.getmtime(os.path.join(base_dir, d)), reverse=True)
    return dirs[0]

