"""
Baseline Runner — simulates a traditional rule-based BMS: a fixed
setpoint applied every timestep, no AI reasoning involved. This is
the comparison point that makes the AI run's savings % meaningful.

Runs entirely on the same DataProvider interface as the AI loop, so
switching Development -> Production mode later requires zero changes
here either.
"""
from app.config import load_config
from app.logger import RunLogger
from app.data_provider.mock_provider import MockDataProvider


def build_fixed_action(cfg: dict) -> dict:
    b = cfg["baseline"]
    return {
        "temperature_setpoint": b["fixed_setpoint_c"],
        "lighting": b["fixed_lighting_pct"],
        "ventilation": b["fixed_ventilation"],
        "reason": "fixed rule-based baseline (no AI reasoning)",
    }


def run_baseline():
    cfg = load_config()
    provider = MockDataProvider(cfg["paths"]["mock_metrics_csv"])
    logger = RunLogger(cfg["paths"]["baseline_log_output"])
    fixed_action = build_fixed_action(cfg)

    for t in range(cfg["loop"]["max_iterations"]):
        metrics = provider.get_metrics(t)
        provider.apply_action(fixed_action)
        logger.log(t, metrics, fixed_action, "fixed baseline action")
        print(f"[baseline t={t}] temp={metrics['zone_temp_c']}C energy={metrics['energy_kwh']}kWh "
              f"-> setpoint={fixed_action['temperature_setpoint']}")


if __name__ == "__main__":
    run_baseline()