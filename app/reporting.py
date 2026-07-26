"""
Executive Reporting (Milestone 6).

Entry point: `python -m app.reporting`.

Reads the existing baseline and AI run logs the same way
`python -m app.comparison` does (via app.comparison.load_log /
validate_complete — unchanged, no re-implementation), calls
app.comparison.compare() to refresh savings_summary.json exactly as
before, then uses the shared analytics layer (app/analytics.py) — the
same functions dashboard/data_loader.py calls — to compute the
executive summary, building insights, and recommendations.

Writes:
  - data/executive_summary.json  (paths.executive_summary_output)
  - reports/report.md            (paths.report_output)

Entirely deterministic and offline: no LLM calls happen here, only
already-recorded log entries are read and summarized. Safe to run in
demo_mode or after a live run alike.
"""
import json
import os
import sys

from app.config import load_config
from app.comparison import compare, load_log, validate_complete, LogValidationError
from app.analytics import (
    entries_to_df,
    compute_decision_analytics,
    compute_executive_summary,
    generate_insights,
    generate_recommendations,
)


def _load_entries(cfg: dict):
    expected = cfg["loop"]["max_iterations"]
    baseline_path = cfg["paths"]["baseline_log_output"]
    ai_path = cfg["paths"]["ai_log_output"]

    baseline_entries = load_log(baseline_path, "Baseline")
    ai_entries = load_log(ai_path, "AI")
    validate_complete(baseline_entries, expected, "Baseline", baseline_path)
    validate_complete(ai_entries, expected, "AI", ai_path)
    return baseline_entries, ai_entries


def build_report(cfg: dict = None) -> dict:
    """Returns the full report payload (comparison + executive summary +
    decision analytics + insights + recommendations). Pure computation
    plus one call to app.comparison.compare() (which does its own,
    already-existing file write) — no other file I/O happens here."""
    cfg = cfg or load_config()

    comparison_result = compare()  # single source of truth for totals; refreshes savings_summary.json

    baseline_entries, ai_entries = _load_entries(cfg)
    baseline_df = entries_to_df(baseline_entries)
    ai_df = entries_to_df(ai_entries)

    decision_analytics = compute_decision_analytics(ai_df) or {}
    executive_summary = compute_executive_summary(
        baseline_df, ai_df, comparison_result, cfg["comfort"], cfg["loop"], decision_analytics
    )
    insights = generate_insights(baseline_df, ai_df, executive_summary, cfg["comfort"], cfg["baseline"])
    recommendations = generate_recommendations(
        baseline_df, ai_df, executive_summary, insights, cfg["agent"], cfg["loop"]
    )

    return {
        "comparison": comparison_result,
        "executive_summary": executive_summary,
        "decision_analytics": decision_analytics,
        "insights": insights,
        "recommendations": recommendations,
    }


def write_executive_summary(executive_summary: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(executive_summary, f, indent=2)


def _fmt_action(action: dict) -> str:
    value = action.get("value")
    pct = action.get("pct")
    return f"{action.get('field')} = {value} ({pct}% of decisions)" if value is not None else "n/a"


def render_report_md(report: dict, cfg: dict) -> str:
    s = report["executive_summary"]
    comp = report["comparison"]
    da = report["decision_analytics"]

    lines = []
    lines.append("# Eco-Loop Building Agents — Executive Report")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append(f"- **Total AI-driven energy:** {s['total_energy_kwh']} kWh")
    lines.append(f"- **Baseline energy:** {s['baseline_energy_kwh']} kWh")
    lines.append(f"- **Energy saved:** {s['energy_saved_kwh']} kWh ({s['energy_saved_pct']}%)")
    lines.append(f"- **Comfort maintained:** {'Yes' if s['comfort_maintained'] else 'No'}")
    lines.append(f"- **Total AI decisions:** {s['total_ai_decisions']}")
    lines.append(f"- **Average confidence:** {s['avg_confidence']}")
    lines.append(f"- **Average risk:** {s['avg_risk_level']} (score {s['avg_risk_score']})")
    lines.append(
        f"- **Peak occupancy:** {s['peak_occupancy']['occupied_timesteps']} timesteps "
        f"({s['peak_occupancy']['occupied_pct']}% of the run)"
    )
    lines.append(
        f"- **Peak energy period:** t={s['peak_energy_period']['timestep']} "
        f"({s['peak_energy_period']['time_of_day']}), {s['peak_energy_period']['energy_kwh']} kWh"
    )
    lines.append(f"- **Largest HVAC adjustment:** {s['largest_hvac_adjustment_c']} C")
    lines.append(f"- **Most common action:** {_fmt_action(s['most_common_action'])}")
    lines.append("")

    lines.append("## Simulation Statistics")
    lines.append("| | Baseline | AI-driven |")
    lines.append("|---|---|---|")
    lines.append(f"| Timesteps | {comp['baseline']['timesteps']} | {comp['ai_driven']['timesteps']} |")
    lines.append(f"| Total energy (kWh) | {comp['baseline']['total_energy_kwh']} | {comp['ai_driven']['total_energy_kwh']} |")
    lines.append(f"| Avg zone temp (C) | {comp['baseline']['avg_zone_temp_c']} | {comp['ai_driven']['avg_zone_temp_c']} |")
    lines.append(f"| Comfort violations | {comp['baseline']['comfort_violations']} | {comp['ai_driven']['comfort_violations']} |")
    lines.append(f"| Comfort violation rate | {comp['baseline']['comfort_violation_rate_pct']}% | {comp['ai_driven']['comfort_violation_rate_pct']}% |")
    lines.append("")

    lines.append("## AI Performance")
    if da:
        if "avg_confidence" in da:
            lines.append(f"- Average confidence: {da['avg_confidence']}")
        if "avg_adjustment_c" in da:
            lines.append(f"- Average setpoint adjustment: {da['avg_adjustment_c']} C")
        if "largest_adjustment_c" in da:
            lines.append(f"- Largest setpoint adjustment: {da['largest_adjustment_c']} C")
        if "adjustment_frequency_pct" in da:
            lines.append(f"- Setpoint changed in {da['adjustment_frequency_pct']}% of decisions (Decision Stability)")
        if "verification_pass_rate_pct" in da:
            lines.append(f"- Self-verification pass rate: {da['verification_pass_rate_pct']}%")
        if "risk_distribution" in da:
            risk_str = ", ".join(f"{k}: {v}" for k, v in da["risk_distribution"].items())
            lines.append(f"- Risk distribution: {risk_str}")
    else:
        lines.append("- No structured decision data available for this run.")
    lines.append("")

    lines.append("## Building Insights")
    for insight in report["insights"]:
        lines.append(f"- {insight}")
    lines.append("")

    lines.append("## Recommendations")
    for rec in report["recommendations"]:
        lines.append(f"- {rec}")
    lines.append("")

    return "\n".join(lines)


def write_report_md(report: dict, cfg: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(render_report_md(report, cfg))


def run() -> None:
    cfg = load_config()
    report = build_report(cfg)

    exec_summary_path = cfg["paths"]["executive_summary_output"]
    report_path = cfg["paths"]["report_output"]

    write_executive_summary(report["executive_summary"], exec_summary_path)
    write_report_md(report, cfg, report_path)

    print(f"Executive summary written to {exec_summary_path}")
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    try:
        run()
    except LogValidationError as e:
        print(str(e))
        sys.exit(1)