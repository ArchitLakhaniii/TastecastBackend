from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from schemas.canonical import ValidationIssue


def basic_quality_checks_sales_fact(df: pd.DataFrame) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    # impossible dates: far future/past sanity (soft)
    if "date" in df.columns:
        d = pd.to_datetime(df["date"], errors="coerce")
        if d.notna().any():
            min_d = d.min()
            max_d = d.max()
            if min_d < pd.Timestamp("2000-01-01"):
                issues.append(
                    ValidationIssue(
                        level="warning",
                        code="very_old_dates",
                        message=f"sales_fact has very old dates (min={min_d.date().isoformat()})",
                    )
                )
            if max_d > pd.Timestamp.now() + pd.Timedelta(days=365):
                issues.append(
                    ValidationIssue(
                        level="warning",
                        code="far_future_dates",
                        message=f"sales_fact has far-future dates (max={max_d.date().isoformat()})",
                    )
                )

    # extreme missing stretches / duplicates mostly handled by canonical validator; keep this light for now.
    return issues


def build_validation_report(issues: List[ValidationIssue]) -> dict:
    return {
        "ok": not any(i.level == "error" for i in issues),
        "errors": [i.__dict__ for i in issues if i.level == "error"],
        "warnings": [i.__dict__ for i in issues if i.level == "warning"],
    }

