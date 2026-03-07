from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd


def run_dir(run_id: str, base_dir: str = "artifacts/runs") -> str:
    return os.path.join(base_dir, run_id)


def ensure_run_dir(run_id: str, base_dir: str = "artifacts/runs") -> str:
    d = run_dir(run_id, base_dir=base_dir)
    os.makedirs(d, exist_ok=True)
    return d


def write_csv(df: pd.DataFrame, path: str) -> str:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def write_json(obj: Dict[str, Any], path: str) -> str:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
    return path


@dataclass(frozen=True)
class WrittenArtifacts:
    run_id: str
    base_path: str
    daily_plan_csv: str
    ingredient_plan_csv: Optional[str]
    advisories_csv: str
    forecast_csv: str
    forecast_summary_json: str
    explanations_json: str
    status_json: str


def write_run_artifacts(
    *,
    run_id: str,
    daily_plan_df: pd.DataFrame,
    ingredient_plan_df: Optional[pd.DataFrame],
    advisories_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    forecast_summary: Dict[str, Any],
    explanations: Dict[str, Any],
    status: Dict[str, Any],
    base_dir: str = "artifacts/runs",
    mirror_current: bool = True,
) -> WrittenArtifacts:
    base = ensure_run_dir(run_id, base_dir=base_dir)

    daily_plan_csv = write_csv(daily_plan_df, os.path.join(base, "daily_plan.csv"))
    forecast_csv = write_csv(forecast_df, os.path.join(base, "forecast.csv"))
    advisories_csv = write_csv(advisories_df, os.path.join(base, "advisories.csv"))
    ingredient_plan_csv = None
    if ingredient_plan_df is not None:
        ingredient_plan_csv = write_csv(ingredient_plan_df, os.path.join(base, "ingredient_plan.csv"))

    forecast_summary_json = write_json(forecast_summary, os.path.join(base, "forecast_summary.json"))
    explanations_json = write_json(explanations, os.path.join(base, "explanations.json"))
    status_json = write_json(status, os.path.join(base, "status.json"))

    if mirror_current:
        os.makedirs("artifacts", exist_ok=True)
        # Keep backward compatible “current” copies for existing frontend paths.
        write_csv(daily_plan_df, "artifacts/daily_plan.csv")
        write_csv(advisories_df, "artifacts/advisories.csv")
        if ingredient_plan_df is not None:
            write_csv(ingredient_plan_df, "artifacts/ingredient_plan.csv")
        write_json(forecast_summary, "artifacts/forecast_summary.json")

    return WrittenArtifacts(
        run_id=run_id,
        base_path=base,
        daily_plan_csv=daily_plan_csv,
        ingredient_plan_csv=ingredient_plan_csv,
        advisories_csv=advisories_csv,
        forecast_csv=forecast_csv,
        forecast_summary_json=forecast_summary_json,
        explanations_json=explanations_json,
        status_json=status_json,
    )

