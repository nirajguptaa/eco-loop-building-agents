"""
Eco-Loop Building Agents — Dashboard

Renders KPIs, comparison charts, and the AI decision log from the
existing pipeline outputs only. Contains no simulation, agent, or
validation logic of its own — all of that already exists in app/ and
is reused via dashboard/data_loader.py. This file is presentation only.

UI pass (this revision): styling, layout, and component structure only.
No data loading, computation, or gating logic was changed — every
data.X value below is read exactly as load_dashboard_data() returns it.
"""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from data_loader import load_dashboard_data


st.set_page_config(
    page_title="Eco-Loop Building Agents",
    layout="wide",
    initial_sidebar_state="collapsed",
)

data = load_dashboard_data()
comfort_cfg = data.cfg["comfort"]


# =======================================================================
# Design system — CSS only. No logic lives here.
# =======================================================================
st.markdown("""
<style>
:root {
    --el-bg: #0e1117;
    --el-surface: #161b24;
    --el-surface-2: #1c222d;
    --el-border: #2a3140;
    --el-text: #e6e8eb;
    --el-text-muted: #8b93a3;
    --el-accent: #4c8dff;
    --el-green: #3ecf8e;
    --el-amber: #e8a33d;
    --el-red: #e5484d;
}

.stApp { background-color: var(--el-bg); }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }

h1, h2, h3, h4, .el-section-title { font-family: -apple-system, "Segoe UI", sans-serif; color: var(--el-text); }

.el-header {
    display: flex; align-items: baseline; justify-content: space-between;
    border-bottom: 1px solid var(--el-border); padding-bottom: 14px; margin-bottom: 24px;
}
.el-header-title { font-size: 22px; font-weight: 600; color: var(--el-text); }
.el-header-sub { font-size: 13px; color: var(--el-text-muted); }

.el-section-title {
    font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--el-text-muted); margin: 28px 0 12px 0; padding-top: 8px;
    border-top: 1px solid var(--el-border);
}
.el-section-title.first { border-top: none; padding-top: 0; margin-top: 0; }

/* KPI cards */
.el-kpi-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.el-kpi-card {
    flex: 1 1 150px; background: var(--el-surface); border: 1px solid var(--el-border);
    border-radius: 10px; padding: 16px 18px; min-width: 150px;
}
.el-kpi-label { font-size: 12px; color: var(--el-text-muted); font-weight: 500; margin-bottom: 6px; }
.el-kpi-value { font-size: 26px; font-weight: 600; color: var(--el-text); line-height: 1.1; }
.el-kpi-sub { font-size: 12px; color: var(--el-text-muted); margin-top: 6px; }
.el-kpi-card.accent-green { border-left: 3px solid var(--el-green); }
.el-kpi-card.accent-red { border-left: 3px solid var(--el-red); }
.el-kpi-card.accent-blue { border-left: 3px solid var(--el-accent); }

/* Generic metric-group card */
.el-card {
    background: var(--el-surface); border: 1px solid var(--el-border);
    border-radius: 10px; padding: 18px 20px; margin-bottom: 16px;
}
.el-card-title { font-size: 13px; font-weight: 600; color: var(--el-text-muted); margin-bottom: 12px; }

/* Recommendations */
.el-reco {
    background: var(--el-surface); border: 1px solid var(--el-border);
    border-left: 3px solid var(--el-accent); border-radius: 8px;
    padding: 14px 18px; margin-bottom: 8px; color: var(--el-text); font-size: 14px; line-height: 1.5;
}
.el-insight {
    background: var(--el-surface-2); border-radius: 8px;
    padding: 12px 16px; margin-bottom: 6px; color: var(--el-text); font-size: 14px; line-height: 1.5;
}

/* Tighten Streamlit's own metric widget where still used, and plotly charts */
div[data-testid="stMetric"] {
    background: var(--el-surface); border: 1px solid var(--el-border);
    border-radius: 10px; padding: 14px 16px;
}
.js-plotly-plot { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


def kpi_card(label: str, value: str, sub: str = "", accent: str = "") -> str:
    cls = f"el-kpi-card {accent}".strip()
    sub_html = f'<div class="el-kpi-sub">{sub}</div>' if sub else ""
    return f'<div class="{cls}"><div class="el-kpi-label">{label}</div><div class="el-kpi-value">{value}</div>{sub_html}</div>'


def section_title(text: str, first: bool = False) -> None:
    cls = "el-section-title first" if first else "el-section-title"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)


PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=44, b=36),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=12)),
    font=dict(size=12, color="#e6e8eb"),
    height=340,
)


# =======================================================================
# Header
# =======================================================================
st.markdown(
    '<div class="el-header">'
    '<div class="el-header-title">Eco-Loop Building Agents</div>'
    '<div class="el-header-sub">Autonomous HVAC control — savings &amp; decision analytics</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Status messages — always shown first, honest about what's missing
# ---------------------------------------------------------------------
if not data.baseline.available:
    st.warning(
        f"**Baseline run not ready.** {data.baseline.error or ''} "
        f"({data.baseline.timesteps_found}/{data.cfg['loop']['max_iterations']} timesteps found)"
    )
if not data.ai.available:
    st.warning(
        f"**AI run not ready.** {data.ai.error or ''} "
        f"({data.ai.timesteps_found}/{data.cfg['loop']['max_iterations']} timesteps found)"
    )
if data.summary_error:
    st.info(data.summary_error)

if not data.baseline.available and not data.ai.available:
    st.stop()  # nothing else on this page can render meaningfully


# ---------------------------------------------------------------------
# KPI cards — only rendered when savings_summary.json exists AND is
# currently fresh (see dashboard/data_loader.py:_check_summary_staleness).
# Existence alone is not enough: a summary file from a previous
# successful run can still be sitting on disk while the current AI or
# baseline log is incomplete or has been overwritten since. Showing
# those numbers next to an "AI run not ready" warning would let stale
# results look like live ones — worse than showing nothing.
# ---------------------------------------------------------------------
section_title("Summary", first=True)
if data.summary and not data.summary_stale:
    s = data.summary
    comfort_ok = s["comfort_maintained"]
    cards_html = '<div class="el-kpi-row">' + "".join([
        kpi_card("Baseline energy", f"{s['baseline']['total_energy_kwh']} kWh"),
        kpi_card("AI energy", f"{s['ai_driven']['total_energy_kwh']} kWh", accent="accent-blue"),
        kpi_card("Energy saved", f"{s['energy_saved_kwh']} kWh", accent="accent-green"),
        kpi_card("Energy saved %", f"{s['energy_saved_pct']}%", accent="accent-green"),
        kpi_card("Comfort maintained", "Yes" if comfort_ok else "No",
                 accent="accent-green" if comfort_ok else "accent-red"),
        kpi_card("Comfort violations", f"{s['ai_driven']['comfort_violations']}",
                 accent="accent-green" if s['ai_driven']['comfort_violations'] == 0 else "accent-red"),
    ]) + '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)
elif data.summary and data.summary_stale:
    st.warning(f"**KPI summary is stale — not displayed.** {data.summary_stale_reason}")
else:
    st.info(
        "KPI summary not available yet. Run `python -m app.comparison` "
        "once both the baseline and AI simulations have completed."
    )


# ---------------------------------------------------------------------
# Executive Summary (Milestone 6). Gated exactly like the KPI cards
# above (fresh summary + both logs available) since data.executive_summary
# is derived from the same inputs via the shared app/analytics.py layer.
# ---------------------------------------------------------------------
section_title("Executive summary")
if data.executive_summary:
    es = data.executive_summary

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<div class="el-card"><div class="el-card-title">Decision quality</div>', unsafe_allow_html=True)
        r1, r2 = st.columns(2)
        r1.metric("Total AI decisions", es["total_ai_decisions"])
        r2.metric("Avg confidence", es["avg_confidence"])
        r3, r4 = st.columns(2)
        r3.metric("Avg risk", f"{es['avg_risk_level']} ({es['avg_risk_score']})" if es["avg_risk_level"] else "n/a")
        r4.metric("Largest HVAC adjustment", f"{es['largest_hvac_adjustment_c']} C")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_b:
        st.markdown('<div class="el-card"><div class="el-card-title">Operational context</div>', unsafe_allow_html=True)
        mca = es["most_common_action"]
        r5, r6 = st.columns(2)
        r5.metric(
            "Peak occupancy",
            f"{es['peak_occupancy']['occupied_pct']}%",
            help=f"{es['peak_occupancy']['occupied_timesteps']} of the run's timesteps were occupied."
        )
        r6.metric(
            "Peak energy period",
            es["peak_energy_period"]["time_of_day"],
            help=f"t={es['peak_energy_period']['timestep']}, {es['peak_energy_period']['energy_kwh']} kWh"
        )
        st.metric(
            "Most common action",
            f"{mca['value']}" if mca["value"] is not None else "n/a",
            help=f"{mca['field']}, {mca['pct']}% of decisions" if mca["value"] is not None else None
        )
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info(
        "Executive summary not available yet — needs a fresh, complete baseline "
        "and AI run. Run `python -m app.reporting` once both simulations and "
        "`python -m app.comparison` have completed."
    )


# ---------------------------------------------------------------------
# Charts — only rendered when both logs are individually available.
# Each chart degrades gracefully: if only one side is available, that
# one line still renders rather than blocking the whole section.
# ---------------------------------------------------------------------
section_title("Charts")

if data.baseline.available or data.ai.available:
    chart_col_1, chart_col_2 = st.columns(2)

    # --- Energy over time ---
    with chart_col_1:
        fig_energy = go.Figure()
        if data.baseline.available:
            fig_energy.add_trace(go.Scatter(
                x=data.baseline.df["timestep"], y=data.baseline.df["metric_energy_kwh"],
                mode="lines", name="Baseline", line=dict(color="#8b93a3", width=2)
            ))
        if data.ai.available:
            fig_energy.add_trace(go.Scatter(
                x=data.ai.df["timestep"], y=data.ai.df["metric_energy_kwh"],
                mode="lines", name="AI-driven", line=dict(color="#4c8dff", width=2)
            ))
        fig_energy.update_layout(title="Energy use over time", xaxis_title="Timestep", yaxis_title="kWh", **PLOTLY_LAYOUT)
        st.plotly_chart(fig_energy, width="stretch", config={"displayModeBar": False})

    # --- Zone temperature over time, with comfort band shaded ---
    with chart_col_2:
        fig_temp = go.Figure()
        fig_temp.add_hrect(
            y0=comfort_cfg["min_temp_c"], y1=comfort_cfg["max_temp_c"],
            fillcolor="#3ecf8e", opacity=0.08, line_width=0,
            annotation_text="Comfort band", annotation_position="top left",
            annotation_font=dict(size=11, color="#8b93a3"),
        )
        if data.baseline.available:
            fig_temp.add_trace(go.Scatter(
                x=data.baseline.df["timestep"], y=data.baseline.df["metric_zone_temp_c"],
                mode="lines", name="Baseline zone temp", line=dict(color="#8b93a3", width=2)
            ))
        if data.ai.available:
            fig_temp.add_trace(go.Scatter(
                x=data.ai.df["timestep"], y=data.ai.df["metric_zone_temp_c"],
                mode="lines", name="AI zone temp", line=dict(color="#4c8dff", width=2)
            ))
        fig_temp.update_layout(title="Zone temperature over time", xaxis_title="Timestep", yaxis_title="°C", **PLOTLY_LAYOUT)
        st.plotly_chart(fig_temp, width="stretch", config={"displayModeBar": False})

    chart_col_3, chart_col_4 = st.columns(2)

    # --- Setpoint over time ---
    with chart_col_3:
        fig_setpoint = go.Figure()
        if data.baseline.available:
            fig_setpoint.add_trace(go.Scatter(
                x=data.baseline.df["timestep"], y=data.baseline.df["action_temperature_setpoint"],
                mode="lines", name="Baseline setpoint", line=dict(dash="dot", color="#8b93a3", width=2)
            ))
        if data.ai.available:
            fig_setpoint.add_trace(go.Scatter(
                x=data.ai.df["timestep"], y=data.ai.df["action_temperature_setpoint"],
                mode="lines+markers", name="AI setpoint", line=dict(color="#4c8dff", width=2), marker=dict(size=5)
            ))
        fig_setpoint.update_layout(title="Temperature setpoint over time", xaxis_title="Timestep", yaxis_title="°C", **PLOTLY_LAYOUT)
        st.plotly_chart(fig_setpoint, width="stretch", config={"displayModeBar": False})

    # --- Occupancy timeline, only if the column is present ---
    with chart_col_4:
        occupancy_source = data.ai.df if data.ai.available else (data.baseline.df if data.baseline.available else None)
        if occupancy_source is not None and "metric_occupancy" in occupancy_source.columns:
            fig_occ = go.Figure()
            fig_occ.add_trace(go.Scatter(
                x=occupancy_source["timestep"], y=occupancy_source["metric_occupancy"],
                mode="lines", line_shape="hv", name="Occupancy", fill="tozeroy",
                line=dict(color="#e8a33d", width=1.5), fillcolor="rgba(232,163,61,0.15)"
            ))
            fig_occ.update_layout(
                title="Occupancy over time", xaxis_title="Timestep",
                yaxis=dict(title="Occupied (1) / Unoccupied (0)", tickvals=[0, 1]),
                **PLOTLY_LAYOUT
            )
            st.plotly_chart(fig_occ, width="stretch", config={"displayModeBar": False})
else:
    st.info("No chart data available yet — run the baseline and/or AI simulation first.")


# ---------------------------------------------------------------------
# AI decision table
# ---------------------------------------------------------------------
section_title("AI decision log")
if data.ai.available:
    table_df = data.ai.df[[
        "timestep", "metric_zone_temp_c", "action_temperature_setpoint",
        "action_lighting", "action_ventilation", "action_reason"
    ]].rename(columns={
        "metric_zone_temp_c": "zone_temp_c",
        "action_temperature_setpoint": "setpoint_c",
        "action_lighting": "lighting_pct",
        "action_ventilation": "ventilation",
        "action_reason": "ai_reason",
    })
    st.dataframe(
        table_df,
        use_container_width=True,
        height=420,
        column_config={
            "timestep": st.column_config.NumberColumn("Timestep", width="small"),
            "zone_temp_c": st.column_config.NumberColumn("Zone temp (°C)", format="%.2f", width="small"),
            "setpoint_c": st.column_config.NumberColumn("Setpoint (°C)", format="%.2f", width="small"),
            "lighting_pct": st.column_config.NumberColumn("Lighting (%)", width="small"),
            "ventilation": st.column_config.TextColumn("Ventilation", width="small"),
            "ai_reason": st.column_config.TextColumn("AI reason", width="large"),
        },
    )
else:
    st.info(
        f"AI decision log not available. {data.ai.error or ''} "
        f"Run `python -m app.main` to generate it."
    )


# ---------------------------------------------------------------------
# Decision Explainability (Milestone 5, feature 5) — reasoning timeline,
# confidence trend, risk distribution, verification results. Gated on
# actually having non-null structured data, not just column presence,
# since a replayed pre-Milestone-5 transcript has these columns but they
# are all null/"unknown" — showing charts for that would be misleading.
# Every existing section above is untouched.
# ---------------------------------------------------------------------
section_title("Decision explainability")
_has_explainability = bool(data.analytics) and data.ai.available
if _has_explainability:
    df = data.ai.df
    exp_col_1, exp_col_2 = st.columns(2)

    if "confidence_trend" in data.analytics:
        with exp_col_1:
            fig_conf = go.Figure()
            fig_conf.add_trace(go.Scatter(
                x=df["timestep"], y=pd.to_numeric(df["action_confidence"], errors="coerce"),
                mode="lines+markers", name="Confidence", line=dict(color="#4c8dff", width=2), marker=dict(size=5)
            ))
            fig_conf.update_layout(
                title="Decision confidence over time", xaxis_title="Timestep",
                yaxis_title="Confidence (0-1)", yaxis_range=[0, 1], **PLOTLY_LAYOUT
            )
            st.plotly_chart(fig_conf, width="stretch", config={"displayModeBar": False})

    if "risk_distribution" in data.analytics:
        with exp_col_2:
            risk_counts = data.analytics["risk_distribution"]
            risk_colors = {"low": "#3ecf8e", "medium": "#e8a33d", "high": "#e5484d"}
            fig_risk = go.Figure(data=[go.Bar(
                x=list(risk_counts.keys()), y=list(risk_counts.values()),
                marker_color=[risk_colors.get(k, "#4c8dff") for k in risk_counts.keys()]
            )])
            fig_risk.update_layout(title="Risk level distribution", xaxis_title="Risk level", yaxis_title="Count", **PLOTLY_LAYOUT)
            st.plotly_chart(fig_risk, width="stretch", config={"displayModeBar": False})

    if "action_verification_passed" in df.columns:
        verified_col = df["action_verification_passed"].dropna()
        if not verified_col.empty:
            pass_counts = verified_col.astype(bool).value_counts()
            fig_verify = go.Figure(data=[go.Bar(
                x=["Passed" if k else "Flagged" for k in pass_counts.index],
                y=pass_counts.values,
                marker_color=["#3ecf8e" if k else "#e8a33d" for k in pass_counts.index],
            )])
            fig_verify.update_layout(title="Self-verification results", yaxis_title="Count", **PLOTLY_LAYOUT)
            st.plotly_chart(fig_verify, width="stretch", config={"displayModeBar": False})

    st.markdown('<div class="el-card-title" style="margin-top:8px;">Reasoning timeline</div>', unsafe_allow_html=True)
    reasoning_cols = {
        "timestep": "timestep",
        "action_reason": "reason",
        "action_confidence": "confidence",
        "action_risk_level": "risk_level",
        "action_forecast_summary": "forecast_summary",
        "action_alternative_considered": "alternative_considered",
        "action_verification_passed": "verified",
        "action_verification_notes": "verification_notes",
    }
    present = [c for c in reasoning_cols if c in df.columns]
    st.dataframe(
        df[present].rename(columns=reasoning_cols),
        use_container_width=True, height=350
    )
else:
    st.info(
        "No structured decision data (confidence, risk level, forecast reasoning) "
        "found for this run yet. This appears if you're replaying a transcript "
        "recorded before Milestone 5, or verification is disabled. Run "
        "`python -m app.main` with a live LLM call to record a fresh transcript "
        "with structured output, then switch demo_mode back to true."
    )


# ---------------------------------------------------------------------
# Decision Analytics (Milestone 5, feature 6)
# ---------------------------------------------------------------------
section_title("Decision analytics")
if data.analytics:
    a = data.analytics
    metric_defs = []
    if "avg_confidence" in a:
        metric_defs.append(("Avg confidence", f"{a['avg_confidence']}"))
    if "avg_adjustment_c" in a:
        metric_defs.append(("Avg adjustment", f"{a['avg_adjustment_c']} C"))
    if "largest_adjustment_c" in a:
        metric_defs.append(("Largest adjustment", f"{a['largest_adjustment_c']} C"))
    if "adjustment_frequency_pct" in a:
        metric_defs.append(("Adjustment frequency", f"{a['adjustment_frequency_pct']}%"))
    if "verification_pass_rate_pct" in a:
        metric_defs.append(("Verification pass rate", f"{a['verification_pass_rate_pct']}%"))

    if metric_defs:
        cards_html = '<div class="el-kpi-row">' + "".join(
            [kpi_card(label, value) for label, value in metric_defs]
        ) + '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)
else:
    st.info(
        "Decision analytics not available yet — needs a completed AI run "
        "with structured decision output (see note above)."
    )


# ---------------------------------------------------------------------
# AI Performance (Milestone 6) — a compact recap of decision-quality
# stats for judges, pulling from the same data.analytics dict as the
# Decision Analytics section above (no recomputation).
# ---------------------------------------------------------------------
section_title("AI performance")
if data.analytics:
    a = data.analytics
    perf_lines = []
    if "avg_confidence" in a:
        perf_lines.append(f"- Average confidence: **{a['avg_confidence']}**")
    if "verification_pass_rate_pct" in a:
        perf_lines.append(f"- Self-verification pass rate: **{a['verification_pass_rate_pct']}%**")
    if "risk_distribution" in a:
        risk_str = ", ".join(f"{k}: {v}" for k, v in a["risk_distribution"].items())
        perf_lines.append(f"- Risk distribution: {risk_str}")
    st.markdown('<div class="el-card">' + ("<br>".join(perf_lines) if perf_lines else "No AI performance data available yet.") + '</div>', unsafe_allow_html=True)
else:
    st.info("AI performance stats need a completed AI run with structured decision output.")


# ---------------------------------------------------------------------
# Decision Stability (Milestone 6) — how often the agent actually
# changes the setpoint vs holds it, reusing the same adjustment-
# frequency figures from data.analytics.
# ---------------------------------------------------------------------
section_title("Decision stability")
if data.analytics and "adjustment_frequency_pct" in data.analytics:
    a = data.analytics
    stability_cols = st.columns(3)
    stability_cols[0].metric("Setpoint changed", f"{a['adjustment_frequency_pct']}% of steps")
    stability_cols[1].metric("Avg adjustment", f"{a.get('avg_adjustment_c', 'n/a')} C")
    stability_cols[2].metric("Largest adjustment", f"{a.get('largest_adjustment_c', 'n/a')} C")
    if a["adjustment_frequency_pct"] < 20:
        st.success("Setpoint decisions are stable — changes are infrequent, not oscillating.")
    else:
        st.warning("Setpoint changes are frequent — worth checking whether the agent is reacting to noise.")
else:
    st.info("Decision stability metrics need a completed AI run with structured decision output.")


# ---------------------------------------------------------------------
# Top Insights (Milestone 6) — deterministic, rule-based sentences from
# app.analytics.generate_insights(), computed once in data_loader.py.
# ---------------------------------------------------------------------
section_title("Top insights")
if data.insights:
    for insight in data.insights:
        st.markdown(f'<div class="el-insight">{insight}</div>', unsafe_allow_html=True)
else:
    st.info(
        "Building insights not available yet — needs a fresh, complete baseline "
        "and AI run (same requirement as the Executive Summary above)."
    )


# ---------------------------------------------------------------------
# Recommendations (Milestone 6) — deterministic, rule-based operational
# suggestions from app.analytics.generate_recommendations().
# ---------------------------------------------------------------------
section_title("Recommendations")
if data.recommendations:
    for rec in data.recommendations:
        st.markdown(f'<div class="el-reco">{rec}</div>', unsafe_allow_html=True)
else:
    st.info(
        "Recommendations not available yet — needs a fresh, complete baseline "
        "and AI run (same requirement as the Executive Summary above)."
    )