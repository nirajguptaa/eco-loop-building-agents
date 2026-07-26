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
    mtime: Optional[float] = None


@dataclass
class DashboardData:
    cfg: dict
    baseline: LogLoadResult
    ai: LogLoadResult
    summary: Optional[dict] = None
    summary_error: Optional[str] = None
    summary_stale: bool = False
    summary_stale_reason: Optional[str] = None


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


def _mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _load_one(path: str, label: str, expected_timesteps: int) -> LogLoadResult:
    mtime = _mtime(path)
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
        return LogLoadResult(available=False, error=str(e), timesteps_found=found, mtime=mtime)

    return LogLoadResult(available=True, df=_entries_to_df(entries), timesteps_found=len(entries), mtime=mtime)


def _load_summary(path: str):
    if not os.path.exists(path):
        return None, f"Summary file not found: {path}. Run `python -m app.comparison` after both simulations complete."
    try:
        with open(path) as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"Summary file is corrupted: {path} ({e}). Re-run `python -m app.comparison`."


def _check_summary_staleness(baseline: LogLoadResult, ai: LogLoadResult, summary_mtime: Optional[float]):
    """Returns (is_stale, reason). A summary is stale — meaning it must
    not be shown as if it were current — if either log is not currently
    valid/complete, or if the summary file is older than a log it's
    supposed to describe (i.e. a log changed after the last time
    `python -m app.comparison` was run)."""
    if not baseline.available or not ai.available:
        return True, (
            "A previous savings_summary.json exists on disk, but it can't "
            "be trusted right now because the baseline and/or AI log "
            "underneath it is currently incomplete or invalid."
        )

    if summary_mtime is not None:
        newest_log_mtime = max(
            m for m in (baseline.mtime, ai.mtime) if m is not None
        ) if (baseline.mtime or ai.mtime) else None
        if newest_log_mtime is not None and summary_mtime < newest_log_mtime:
            return True, (
                "savings_summary.json is older than the current run logs — "
                "it reflects a previous run. Re-run `python -m app.comparison` "
                "to refresh it before trusting these numbers."
            )

    return False, None


def load_dashboard_data() -> DashboardData:
    cfg = load_config()
    expected = cfg["loop"]["max_iterations"]

    baseline = _load_one(cfg["paths"]["baseline_log_output"], "Baseline", expected)
    ai = _load_one(cfg["paths"]["ai_log_output"], "AI", expected)
    summary, summary_error = _load_summary(cfg["paths"]["summary_output"])
    summary_mtime = _mtime(cfg["paths"]["summary_output"])

    summary_stale, summary_stale_reason = (False, None)
    if summary is not None:
        summary_stale, summary_stale_reason = _check_summary_staleness(baseline, ai, summary_mtime)

    return DashboardData(
        cfg=cfg, baseline=baseline, ai=ai, summary=summary, summary_error=summary_error,
        summary_stale=summary_stale, summary_stale_reason=summary_stale_reason,
    )