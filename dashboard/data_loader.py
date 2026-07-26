"""
Dashboard Data Loader — reads baseline log, AI log, and savings_summary.json.

Deliberately reuses app.comparison.load_log / validate_complete rather than
re-implementing parsing: those are already validated (missing file, empty
file, corrupted line, incomplete run). The only difference here is that a
Streamlit page can't call sys.exit() on bad data — so each source is loaded
independently and failures are returned as status, not raised, letting the
dashboard show "baseline ready, AI run not yet completed" instead of crashing.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from app.config import load_config
from app.comparison import load_log, validate_complete, LogValidationError


@dataclass
class LogLoadResult:
    available: bool
    df: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    timesteps_found: int = 0


@dataclass
class DashboardData:
    cfg: dict
    baseline: LogLoadResult
    ai: LogLoadResult
    summary: Optional[dict] = None
    summary_error: Optional[str] = None


def _entries_to_df(entries: list) -> pd.DataFrame:
    """Flattens the nested {metrics, action, note} log structure into a
    flat DataFrame — one row per timestep, columns for each metric and
    action field, ready for plotting."""
    rows = []
    for e in entries:
        row = {"timestep": e["timestep"], "note": e.get("note", "")}
        row.update({f"metric_{k}": v for k, v in e.get("metrics", {}).items()})
        row.update({f"action_{k}": v for k, v in e.get("action", {}).items()})
        rows.append(row)
    return pd.DataFrame(rows).sort_values("timestep").reset_index(drop=True)


def _load_one(path: str, label: str, expected_timesteps: int) -> LogLoadResult:
    try:
        entries = load_log(path, label)
        validate_complete(entries, expected_timesteps, label, path)
    except LogValidationError as e:
        # Best-effort count for a friendlier "N of M timesteps" status even
        # when validation failed (e.g. an incomplete run) — falls back to 0
        # if the file is missing or too corrupted to count at all.
        found = 0
        if os.path.exists(path):
            try:
                with open(path) as f:
                    found = sum(1 for line in f if line.strip())
            except OSError:
                found = 0
        return LogLoadResult(available=False, error=str(e), timesteps_found=found)

    return LogLoadResult(available=True, df=_entries_to_df(entries), timesteps_found=len(entries))


def _load_summary(path: str):
    if not os.path.exists(path):
        return None, f"Summary file not found: {path}. Run `python -m app.comparison` after both simulations complete."
    try:
        with open(path) as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"Summary file is corrupted: {path} ({e}). Re-run `python -m app.comparison`."


def load_dashboard_data() -> DashboardData:
    cfg = load_config()
    expected = cfg["loop"]["max_iterations"]

    baseline = _load_one(cfg["paths"]["baseline_log_output"], "Baseline", expected)
    ai = _load_one(cfg["paths"]["ai_log_output"], "AI", expected)
    summary, summary_error = _load_summary(cfg["paths"]["summary_output"])

    return DashboardData(cfg=cfg, baseline=baseline, ai=ai, summary=summary, summary_error=summary_error)