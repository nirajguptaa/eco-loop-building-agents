"""
Shared Analytics Layer (Milestone 6).

Single source of truth for every derived statistic used by both
dashboard/data_loader.py and app/reporting.py. Nothing in this module
does file I/O — callers own reading logs and writing output; this
module only computes, from data already loaded into memory.

Every function here is pure and deterministic: same input entries/
dataframes -> same output, always. No LLM calls, no randomness, no
wall-clock reads. That's what keeps Milestone 6 safe to run in
demo_mode / replay, and safe to call twice (dashboard + report) without
the two ever disagreeing with each other.

`compute_decision_analytics` and `entries_to_df` are moved here
unchanged from dashboard/data_loader.py (Milestone 5) so the dashboard
and the new executive report compute decision-quality stats (avg
confidence, largest adjustment, risk distribution, ...) exactly once,
in exactly one place.
"""
from collections import Counter
from typing import Optional

import pandas as pd


RISK_SCORE = {"low": 1, "medium": 2, "high": 3}


# ---------------------------------------------------------------------
# Log shaping (moved from dashboard/data_loader.py, unchanged)
# ---------------------------------------------------------------------
def entries_to_df(entries: list) -> pd.DataFrame:
    """Flattens the nested {metrics, action, note} log structure into a
    flat DataFrame — one row per timestep, columns for each metric and
    action field, ready for plotting or analysis."""
    rows = []
    for e in entries:
        row = {"timestep": e["timestep"], "note": e.get("note", "")}
        row.update({f"metric_{k}": v for k, v in e.get("metrics", {}).items()})
        row.update({f"action_{k}": v for k, v in e.get("action", {}).items()})
        rows.append(row)
    return pd.DataFrame(rows).sort_values("timestep").reset_index(drop=True)


# ---------------------------------------------------------------------
# Decision Analytics (Milestone 5, feature 6 — moved unchanged)
# ---------------------------------------------------------------------
def compute_decision_analytics(ai_df: Optional[pd.DataFrame]) -> Optional[dict]:
    """Returns None (not an empty dict) if the AI run isn't available or
    none of the structured fields it depends on have real data yet (e.g.
    a pre-Milestone-5 transcript with the new columns present but null),
    so callers can tell 'no data' apart from 'zero'."""
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


# ---------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------
def timestep_to_clock(timestep: int, timestep_minutes: int) -> str:
    """Formats a timestep index as a 24h clock time, assuming the run
    starts at 00:00. Purely a display helper — does not affect any
    computed statistic."""
    total_minutes = (timestep * timestep_minutes) % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _mode_with_count(series: pd.Series) -> tuple:
    """Most frequent value in a series, tie-broken by first appearance
    order (not by pandas' internal hash order) so the result is stable
    across runs and pandas versions given the same data."""
    counts = Counter(series.dropna().tolist())
    if not counts:
        return None, 0
    first_seen = {}
    for v in series.dropna().tolist():
        first_seen.setdefault(v, len(first_seen))
    best = min(counts.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
    return best[0], best[1]


# ---------------------------------------------------------------------
# Executive Summary Generator (Milestone 6, feature 1)
# ---------------------------------------------------------------------
def compute_executive_summary(
    baseline_df: pd.DataFrame,
    ai_df: pd.DataFrame,
    comparison_result: dict,
    comfort_cfg: dict,
    loop_cfg: dict,
    decision_analytics: Optional[dict] = None,
) -> dict:
    """Builds the executive_summary.json payload.

    Reuses `comparison_result` (the dict app.comparison.compare() already
    computes and writes to savings_summary.json) for total/baseline
    energy, savings, and comfort_maintained — that's the single
    implementation of those numbers, this function does not recompute
    them. Reuses `decision_analytics` (compute_decision_analytics output)
    for avg_confidence and largest_adjustment_c for the same reason.
    Everything else here (peak occupancy, peak energy period, most
    common action) is new and computed once, from the flattened
    dataframes, so the dashboard and the report always show identical
    numbers.
    """
    decision_analytics = decision_analytics or {}
    timestep_minutes = loop_cfg.get("timestep_minutes", 15)

    total_ai_decisions = len(ai_df)

    # Peak occupancy: occupancy is a 0/1 signal, so "peak" means how much
    # of the run was occupied, not a single instant.
    occupied_timesteps = int(ai_df["metric_occupancy"].sum()) if "metric_occupancy" in ai_df.columns else 0
    peak_occupancy = {
        "occupied_timesteps": occupied_timesteps,
        "occupied_pct": round(100 * occupied_timesteps / len(ai_df), 1) if len(ai_df) else 0.0,
    }

    # Peak energy period: the single timestep with the highest AI-run
    # energy draw. idxmax breaks ties at the first occurrence, so this
    # is deterministic for a fixed log.
    peak_idx = ai_df["metric_energy_kwh"].idxmax()
    peak_row = ai_df.loc[peak_idx]
    peak_energy_period = {
        "timestep": int(peak_row["timestep"]),
        "time_of_day": timestep_to_clock(int(peak_row["timestep"]), timestep_minutes),
        "energy_kwh": round(float(peak_row["metric_energy_kwh"]), 3),
        "occupied": bool(peak_row.get("metric_occupancy", 0)),
    }

    # Average risk: map low/medium/high to 1/2/3 so "average risk" is a
    # single deterministic number, plus the nearest label for readability.
    avg_risk_score = None
    avg_risk_level = None
    if "action_risk_level" in ai_df.columns:
        risk_scores = ai_df["action_risk_level"].map(RISK_SCORE).dropna()
        if not risk_scores.empty:
            avg_risk_score = round(float(risk_scores.mean()), 2)
            nearest = min(RISK_SCORE.items(), key=lambda kv: abs(kv[1] - avg_risk_score))
            avg_risk_level = nearest[0]

    # Most common action: the most frequent ventilation setting is the
    # clearest single categorical "action" the agent repeatedly takes
    # (temperature_setpoint is closer to continuous). Documented here
    # since "most common action" is otherwise ambiguous.
    most_common_value, most_common_count = (None, 0)
    if "action_ventilation" in ai_df.columns:
        most_common_value, most_common_count = _mode_with_count(ai_df["action_ventilation"])
    most_common_action = {
        "field": "ventilation",
        "value": most_common_value,
        "count": most_common_count,
        "pct": round(100 * most_common_count / total_ai_decisions, 1) if total_ai_decisions else 0.0,
    }

    return {
        "total_energy_kwh": comparison_result["ai_driven"]["total_energy_kwh"],
        "baseline_energy_kwh": comparison_result["baseline"]["total_energy_kwh"],
        "energy_saved_kwh": comparison_result["energy_saved_kwh"],
        "energy_saved_pct": comparison_result["energy_saved_pct"],
        "comfort_maintained": comparison_result["comfort_maintained"],
        "total_ai_decisions": total_ai_decisions,
        "avg_confidence": decision_analytics.get("avg_confidence"),
        "avg_risk_score": avg_risk_score,
        "avg_risk_level": avg_risk_level,
        "peak_occupancy": peak_occupancy,
        "peak_energy_period": peak_energy_period,
        "largest_hvac_adjustment_c": decision_analytics.get("largest_adjustment_c"),
        "most_common_action": most_common_action,
    }


# ---------------------------------------------------------------------
# Building Insights Engine (Milestone 6, feature 3)
# ---------------------------------------------------------------------
def generate_insights(
    baseline_df: pd.DataFrame,
    ai_df: pd.DataFrame,
    executive_summary: dict,
    comfort_cfg: dict,
    baseline_cfg: dict,
) -> list:
    """Deterministic, rule-based natural-language insights. Every rule
    below always emits a sentence — the wording branches on the data,
    but a rule never emits zero or two sentences — so the result is a
    fixed 8 insights for any complete pair of logs, comfortably inside
    the required 5-10 range regardless of what the data looks like."""
    insights = []

    # 1. Where did peak demand occur?
    peak = executive_summary["peak_energy_period"]
    if peak["occupied"]:
        insights.append(
            f"Peak energy demand ({peak['energy_kwh']} kWh at t={peak['timestep']}, "
            f"{peak['time_of_day']}) occurred during an occupied period, consistent with "
            f"occupancy-driven cooling and lighting load."
        )
    else:
        insights.append(
            f"Peak energy demand ({peak['energy_kwh']} kWh at t={peak['timestep']}, "
            f"{peak['time_of_day']}) occurred while the space was unoccupied, suggesting "
            f"outdoor conditions rather than occupancy drove the peak."
        )

    # 2. Where did most savings come from?
    if "metric_occupancy" in ai_df.columns and len(baseline_df) == len(ai_df):
        savings_per_step = baseline_df["metric_energy_kwh"].values - ai_df["metric_energy_kwh"].values
        occ = ai_df["metric_occupancy"].values
        savings_occupied = float(savings_per_step[occ == 1].sum())
        savings_unoccupied = float(savings_per_step[occ == 0].sum())
        if savings_unoccupied > savings_occupied:
            insights.append(
                f"Most savings occurred while unoccupied ({round(savings_unoccupied, 2)} kWh saved "
                f"unoccupied vs {round(savings_occupied, 2)} kWh occupied), from raising the setpoint "
                f"when comfort wasn't being actively experienced."
            )
        else:
            insights.append(
                f"Most savings occurred while occupied ({round(savings_occupied, 2)} kWh saved occupied "
                f"vs {round(savings_unoccupied, 2)} kWh unoccupied) — the agent is finding efficiency "
                f"even under active comfort constraints."
            )
    else:
        insights.append("Savings could not be split by occupancy state — occupancy data was unavailable.")

    # 3. Outdoor temperature vs energy
    if "metric_outdoor_temp_c" in ai_df.columns:
        median_temp = ai_df["metric_outdoor_temp_c"].median()
        high_temp_energy = ai_df.loc[ai_df["metric_outdoor_temp_c"] > median_temp, "metric_energy_kwh"].mean()
        low_temp_energy = ai_df.loc[ai_df["metric_outdoor_temp_c"] <= median_temp, "metric_energy_kwh"].mean()
        if pd.notna(high_temp_energy) and pd.notna(low_temp_energy) and high_temp_energy > low_temp_energy:
            insights.append(
                f"Outdoor temperature increased HVAC demand — average energy use was "
                f"{round(high_temp_energy, 3)} kWh above the median outdoor temperature vs "
                f"{round(low_temp_energy, 3)} kWh below it."
            )
        else:
            insights.append(
                "Outdoor temperature showed little to no effect on HVAC demand across this run — "
                "energy use above and below the median outdoor temperature was similar."
            )
    else:
        insights.append("Outdoor temperature data was unavailable for correlation analysis.")

    # 4. Lighting contribution
    if "action_lighting" in ai_df.columns and "fixed_lighting_pct" in baseline_cfg:
        ai_avg_lighting = pd.to_numeric(ai_df["action_lighting"], errors="coerce").mean()
        baseline_lighting = baseline_cfg["fixed_lighting_pct"]
        if pd.notna(ai_avg_lighting) and ai_avg_lighting < baseline_lighting:
            insights.append(
                f"Lighting reductions contributed to savings — average AI lighting level "
                f"({round(ai_avg_lighting, 1)}%) was below the baseline's fixed "
                f"{baseline_lighting}%."
            )
        else:
            insights.append(
                f"Lighting was not reduced below baseline (avg {round(ai_avg_lighting, 1) if pd.notna(ai_avg_lighting) else 'n/a'}% "
                f"vs baseline {baseline_lighting}%) — lighting was not a meaningful contributor to savings here."
            )
    else:
        insights.append("Lighting data was unavailable for comparison against the baseline.")

    # 5. Comfort maintained
    lo, hi = comfort_cfg["min_temp_c"], comfort_cfg["max_temp_c"]
    violations = int((~ai_df["metric_zone_temp_c"].between(lo, hi)).sum())
    if violations == 0:
        insights.append(
            f"Comfort was maintained throughout the simulation with zero violations of the "
            f"{lo}-{hi} C comfort band."
        )
    else:
        insights.append(
            f"The {lo}-{hi} C comfort band was violated in {violations} of {len(ai_df)} timesteps "
            f"({round(100 * violations / len(ai_df), 1)}%)."
        )

    # 6. Decision stability
    adj_freq_pct = None
    if "action_temperature_setpoint" in ai_df.columns:
        setpoints = pd.to_numeric(ai_df["action_temperature_setpoint"], errors="coerce")
        deltas = setpoints.diff().abs().dropna()
        if not deltas.empty:
            adj_freq_pct = round(100 * float((deltas > 0).sum()) / len(deltas), 1)
    if adj_freq_pct is not None:
        if adj_freq_pct < 20:
            insights.append(
                f"Setpoint decisions were highly stable — changed in only {adj_freq_pct}% of steps, "
                f"avoiding unnecessary oscillation."
            )
        else:
            insights.append(
                f"Setpoint decisions changed in {adj_freq_pct}% of steps — worth checking whether the "
                f"agent is reacting to real trends or to noise."
            )
    else:
        insights.append("Setpoint change frequency could not be computed from this log.")

    # 7. Confidence
    avg_conf = executive_summary.get("avg_confidence")
    if avg_conf is not None:
        if avg_conf >= 0.75:
            insights.append(f"The agent reported high average confidence ({avg_conf}) in its decisions.")
        else:
            insights.append(
                f"The agent reported moderate-to-low average confidence ({avg_conf}) — decisions may "
                f"benefit from more context (longer forecast window or memory)."
            )
    else:
        insights.append(
            "Confidence scores were not available for this run (likely a replayed transcript recorded "
            "before Milestone 5, or a run without structured output)."
        )

    # 8. Verification pass rate
    if "action_verification_passed" in ai_df.columns:
        verified = ai_df["action_verification_passed"].dropna()
        if not verified.empty:
            pass_rate = round(100 * float(verified.astype(bool).mean()), 1)
            if pass_rate >= 95:
                insights.append(f"Self-verification passed on {pass_rate}% of decisions, indicating consistent rule compliance.")
            else:
                insights.append(f"Self-verification passed on only {pass_rate}% of decisions — the flagged ones are worth reviewing.")
        else:
            insights.append("Self-verification results were not available for this run.")
    else:
        insights.append("Self-verification results were not available for this run.")

    return insights


# ---------------------------------------------------------------------
# Recommendation Engine (Milestone 6, feature 4)
# ---------------------------------------------------------------------
def generate_recommendations(
    baseline_df: pd.DataFrame,
    ai_df: pd.DataFrame,
    executive_summary: dict,
    insights: list,
    agent_cfg: dict,
    loop_cfg: dict,
) -> list:
    """Deterministic, rule-based operational recommendations. Like
    generate_insights, every rule always emits one recommendation, just
    with different wording depending on the data — giving a stable 5
    recommendations for any complete run."""
    recommendations = []

    # 1. Forecast horizon
    forecast_window = agent_cfg.get("forecast_window", 0)
    if forecast_window < 6:
        recommendations.append(
            f"Increase the forecast horizon (currently {forecast_window} steps) so the agent can "
            f"anticipate occupancy and outdoor-temperature swings further ahead."
        )
    else:
        recommendations.append(
            f"The forecast horizon ({forecast_window} steps) already looks ahead reasonably far — "
            f"only extend it further if pre-cooling/pre-heating is still underperforming."
        )

    # 2. Pre-cooling ahead of occupancy
    precooled = False
    if "metric_occupancy" in ai_df.columns and "action_temperature_setpoint" in ai_df.columns:
        occ = ai_df["metric_occupancy"].values
        setpoints = pd.to_numeric(ai_df["action_temperature_setpoint"], errors="coerce").values
        for i in range(1, len(occ)):
            if occ[i] == 1 and occ[i - 1] == 0:
                if setpoints[i - 1] < setpoints[i]:
                    precooled = True
                    break
    if precooled:
        recommendations.append(
            "Pre-cooling ahead of occupancy transitions is already happening in this run — continue "
            "tuning how many steps ahead the setpoint drops."
        )
    else:
        recommendations.append(
            "Pre-cool before occupancy: lower the setpoint one or two steps ahead of an occupancy "
            "transition instead of reacting only after occupancy begins."
        )

    # 3. Overnight ventilation
    timestep_minutes = loop_cfg.get("timestep_minutes", 15)
    if "metric_occupancy" in ai_df.columns and "action_ventilation" in ai_df.columns:
        clocks = [timestep_to_clock(int(t), timestep_minutes) for t in ai_df["timestep"]]
        is_night = pd.Series([c >= "22:00" or c < "06:00" for c in clocks])
        overnight_unoccupied = ai_df.loc[(ai_df["metric_occupancy"] == 0) & is_night.values, "action_ventilation"]
        if not overnight_unoccupied.empty:
            night_mode, _ = _mode_with_count(overnight_unoccupied)
            if night_mode in ("medium", "high"):
                recommendations.append(
                    f"Reduce overnight ventilation: unoccupied nighttime hours mostly ran at "
                    f"'{night_mode}' ventilation, which is likely more than needed with nobody in the space."
                )
            else:
                recommendations.append(
                    "Overnight ventilation is already minimized during unoccupied nighttime hours — "
                    "no change recommended here."
                )
        else:
            recommendations.append("No unoccupied nighttime hours were found in this run to evaluate overnight ventilation.")
    else:
        recommendations.append("Ventilation or occupancy data was unavailable to evaluate overnight ventilation.")

    # 4. Afternoon peak
    peak = executive_summary["peak_energy_period"]
    if "12:00" <= peak["time_of_day"] < "17:00":
        recommendations.append(
            f"Investigate the afternoon peak at {peak['time_of_day']} (t={peak['timestep']}, "
            f"{peak['energy_kwh']} kWh) — this is a good candidate for a targeted setpoint or "
            f"forecast-horizon adjustment."
        )
    else:
        recommendations.append(
            f"The energy peak occurred at {peak['time_of_day']} (t={peak['timestep']}), outside the "
            f"typical afternoon window — worth confirming this timing matches expected building usage."
        )

    # 5. Lighting schedule
    if "action_lighting" in ai_df.columns and "metric_occupancy" in ai_df.columns:
        lighting = pd.to_numeric(ai_df["action_lighting"], errors="coerce")
        occ = ai_df["metric_occupancy"]
        occ_avg = lighting[occ == 1].mean()
        unocc_avg = lighting[occ == 0].mean()
        if pd.notna(occ_avg) and pd.notna(unocc_avg) and (occ_avg - unocc_avg) > 10:
            recommendations.append(
                "Lighting already tracks occupancy well (higher when occupied, lower when not) — "
                "keep the current schedule."
            )
        else:
            recommendations.append(
                "Tune the lighting schedule to track occupancy more closely — current occupied vs "
                "unoccupied lighting levels are similar, leaving savings on the table."
            )
    else:
        recommendations.append("Lighting or occupancy data was unavailable to evaluate the lighting schedule.")

    return recommendations