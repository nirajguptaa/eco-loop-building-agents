"""
Eco-Loop Building Agents — Dashboard

Renders KPIs, comparison charts, and the AI decision log from the
existing pipeline outputs only. Contains no simulation, agent, or
validation logic of its own — all of that already exists in app/ and
is reused via dashboard/data_loader.py. This file is presentation only.
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


st.set_page_config(page_title="Eco-Loop Building Agents", layout="wide")
st.title("🏢 Eco-Loop Building Agents — Savings Dashboard")

data = load_dashboard_data()
comfort_cfg = data.cfg["comfort"]


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
if data.summary and not data.summary_stale:
    s = data.summary
    st.subheader("Summary")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Baseline Energy", f"{s['baseline']['total_energy_kwh']} kWh")
    c2.metric("AI Energy", f"{s['ai_driven']['total_energy_kwh']} kWh")
    c3.metric("Energy Saved", f"{s['energy_saved_kwh']} kWh")
    c4.metric("Energy Saved %", f"{s['energy_saved_pct']}%")
    c5.metric("Comfort Maintained", "Yes" if s["comfort_maintained"] else "No")
    c6.metric("AI Comfort Violations", s["ai_driven"]["comfort_violations"])
elif data.summary and data.summary_stale:
    st.warning(f"**KPI summary is stale — not displayed.** {data.summary_stale_reason}")
else:
    st.info(
        "KPI summary not available yet. Run `python -m app.comparison` "
        "once both the baseline and AI simulations have completed."
    )


# ---------------------------------------------------------------------
# Charts — only rendered when both logs are individually available.
# Each chart degrades gracefully: if only one side is available, that
# one line still renders rather than blocking the whole section.
# ---------------------------------------------------------------------
st.subheader("Charts")

if data.baseline.available or data.ai.available:
    # --- Energy over time ---
    fig_energy = go.Figure()
    if data.baseline.available:
        fig_energy.add_trace(go.Scatter(
            x=data.baseline.df["timestep"], y=data.baseline.df["metric_energy_kwh"],
            mode="lines", name="Baseline"
        ))
    if data.ai.available:
        fig_energy.add_trace(go.Scatter(
            x=data.ai.df["timestep"], y=data.ai.df["metric_energy_kwh"],
            mode="lines", name="AI-driven"
        ))
    fig_energy.update_layout(title="Energy Use Over Time", xaxis_title="Timestep", yaxis_title="kWh")
    st.plotly_chart(fig_energy, use_container_width=True)

    # --- Zone temperature over time, with comfort band shaded ---
    fig_temp = go.Figure()
    fig_temp.add_hrect(
        y0=comfort_cfg["min_temp_c"], y1=comfort_cfg["max_temp_c"],
        fillcolor="green", opacity=0.08, line_width=0,
        annotation_text="Comfort band", annotation_position="top left"
    )
    if data.baseline.available:
        fig_temp.add_trace(go.Scatter(
            x=data.baseline.df["timestep"], y=data.baseline.df["metric_zone_temp_c"],
            mode="lines", name="Baseline zone temp"
        ))
    if data.ai.available:
        fig_temp.add_trace(go.Scatter(
            x=data.ai.df["timestep"], y=data.ai.df["metric_zone_temp_c"],
            mode="lines", name="AI zone temp"
        ))
    fig_temp.update_layout(title="Zone Temperature Over Time", xaxis_title="Timestep", yaxis_title="°C")
    st.plotly_chart(fig_temp, use_container_width=True)

    # --- Setpoint over time ---
    fig_setpoint = go.Figure()
    if data.baseline.available:
        fig_setpoint.add_trace(go.Scatter(
            x=data.baseline.df["timestep"], y=data.baseline.df["action_temperature_setpoint"],
            mode="lines", name="Baseline setpoint", line=dict(dash="dot")
        ))
    if data.ai.available:
        fig_setpoint.add_trace(go.Scatter(
            x=data.ai.df["timestep"], y=data.ai.df["action_temperature_setpoint"],
            mode="lines+markers", name="AI setpoint"
        ))
    fig_setpoint.update_layout(title="Temperature Setpoint Over Time", xaxis_title="Timestep", yaxis_title="°C")
    st.plotly_chart(fig_setpoint, use_container_width=True)

    # --- Occupancy timeline, only if the column is present ---
    occupancy_source = data.ai.df if data.ai.available else (data.baseline.df if data.baseline.available else None)
    if occupancy_source is not None and "metric_occupancy" in occupancy_source.columns:
        fig_occ = go.Figure()
        fig_occ.add_trace(go.Scatter(
            x=occupancy_source["timestep"], y=occupancy_source["metric_occupancy"],
            mode="lines", line_shape="hv", name="Occupancy", fill="tozeroy"
        ))
        fig_occ.update_layout(
            title="Occupancy Over Time", xaxis_title="Timestep",
            yaxis=dict(title="Occupied (1) / Unoccupied (0)", tickvals=[0, 1])
        )
        st.plotly_chart(fig_occ, use_container_width=True)
else:
    st.info("No chart data available yet — run the baseline and/or AI simulation first.")


# ---------------------------------------------------------------------
# AI decision table
# ---------------------------------------------------------------------
st.subheader("AI Decision Log")
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
    st.dataframe(table_df, use_container_width=True, height=400)
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
st.subheader("Decision Explainability")
_has_explainability = bool(data.analytics) and data.ai.available
if _has_explainability:
    df = data.ai.df

    if "confidence_trend" in data.analytics:
        fig_conf = go.Figure()
        fig_conf.add_trace(go.Scatter(
            x=df["timestep"], y=pd.to_numeric(df["action_confidence"], errors="coerce"),
            mode="lines+markers", name="Confidence"
        ))
        fig_conf.update_layout(
            title="Decision Confidence Over Time", xaxis_title="Timestep",
            yaxis_title="Confidence (0-1)", yaxis_range=[0, 1]
        )
        st.plotly_chart(fig_conf, use_container_width=True)

    if "risk_distribution" in data.analytics:
        risk_counts = data.analytics["risk_distribution"]
        fig_risk = go.Figure(data=[go.Bar(x=list(risk_counts.keys()), y=list(risk_counts.values()))])
        fig_risk.update_layout(title="Risk Level Distribution", xaxis_title="Risk level", yaxis_title="Count")
        st.plotly_chart(fig_risk, use_container_width=True)

    if "action_verification_passed" in df.columns:
        verified_col = df["action_verification_passed"].dropna()
        if not verified_col.empty:
            pass_counts = verified_col.astype(bool).value_counts()
            fig_verify = go.Figure(data=[go.Bar(
                x=["Passed" if k else "Flagged" for k in pass_counts.index],
                y=pass_counts.values
            )])
            fig_verify.update_layout(title="Self-Verification Results", yaxis_title="Count")
            st.plotly_chart(fig_verify, use_container_width=True)

    st.markdown("**Reasoning timeline**")
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
st.subheader("Decision Analytics")
if data.analytics:
    a = data.analytics
    cols = st.columns(4)
    if "avg_confidence" in a:
        cols[0].metric("Avg Confidence", a["avg_confidence"])
    if "avg_adjustment_c" in a:
        cols[1].metric("Avg Adjustment", f"{a['avg_adjustment_c']} C")
    if "largest_adjustment_c" in a:
        cols[2].metric("Largest Adjustment", f"{a['largest_adjustment_c']} C")
    if "adjustment_frequency_pct" in a:
        cols[3].metric("Adjustment Frequency", f"{a['adjustment_frequency_pct']}%")
    if "verification_pass_rate_pct" in a:
        st.metric("Verification Pass Rate", f"{a['verification_pass_rate_pct']}%")
else:
    st.info(
        "Decision analytics not available yet — needs a completed AI run "
        "with structured decision output (see note above)."
    )