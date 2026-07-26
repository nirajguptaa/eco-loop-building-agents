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
    analytics: Optional[dict] = None


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


def compute_decision_analytics(ai_df: Optional[pd.DataFrame]) -> Optional[dict]:
    """Decision Analytics (Milestone 5, feature 6). Reads only from the
    already-loaded AI dataframe — no new file I/O, no duplicated parsing.
    Returns None (not an empty dict) if the AI run isn't available or
    none of the structured fields it depends on have real data yet (e.g.
    a pre-Milestone-5 transcript with the new columns present but null),
    so the dashboard can tell 'no data' apart from 'zero'."""
    if ai_df is None or ai_df.empty:
        return None

    analytics: dict = {}

    if "action_confidence" in ai_df.columns:
        conf = pd.to_numeric(ai_df["action_confidence"], errors="coerce").dropna()
        if not conf.empty:
            analytics["avg_confidence"] = round(float(conf.mean()), 3)
            analytics["confidence_trend"] = conf.tolist()

    if "action_risk_level" in ai_df.columns:
        risk = ai_df["action_risk_level"].dropna()
        risk = risk[risk != "unknown"]
        if not risk.empty:
            analytics["risk_distribution"] = risk.value_counts().to_dict()

    if "action_temperature_setpoint" in ai_df.columns:
        setpoints = pd.to_numeric(ai_df["action_temperature_setpoint"], errors="coerce")
        deltas = setpoints.diff().abs().dropna()
        if not deltas.empty:
            analytics["avg_adjustment_c"] = round(float(deltas.mean()), 3)
            analytics["largest_adjustment_c"] = round(float(deltas.max()), 3)
            analytics["adjustment_frequency_pct"] = round(
                100 * float((deltas > 0).sum()) / len(deltas), 1
            )

    if "action_verification_passed" in ai_df.columns:
        verified = ai_df["action_verification_passed"].dropna()
        if not verified.empty:
            analytics["verification_pass_rate_pct"] = round(
                100 * float(verified.astype(bool).mean()), 1
            )

    return analytics or None


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

    analytics = compute_decision_analytics(ai.df) if ai.available else None

    return DashboardData(
        cfg=cfg, baseline=baseline, ai=ai, summary=summary, summary_error=summary_error,
        summary_stale=summary_stale, summary_stale_reason=summary_stale_reason,
        analytics=analytics,
    )