"""
Comparison — reads baseline_run_log.jsonl and ai_run_log.jsonl,
computes total energy use, % reduction, and comfort-bound violations
for each run. Writes a single savings_summary.json consumed later by
the dashboard, and prints a human-readable report now.

This is the module that actually produces the number your submission
is scored on: "explicitly prove percentage reductions in total kWh
consumed while maintaining thermal comfort boundaries."

Correctness note: a comparison is only trustworthy if both logs are
complete. This module refuses to compute anything from a partial or
malformed log rather than silently producing a misleading number.
"""
import json
import os
import sys
from app.config import load_config


class LogValidationError(Exception):
    """Raised when a log file is missing, empty, corrupted, or incomplete.
    Carries a human-readable message intended to be printed as-is."""
    pass


def load_log(path: str, label: str) -> list:
    if not os.path.exists(path):
        raise LogValidationError(
            f"ERROR: {label} log not found.\n"
            f"Expected file: {path}\n"
            f"Run the corresponding simulation before comparing."
        )

    entries = []
    with open(path) as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise LogValidationError(
                    f"ERROR: {label} log is corrupted.\n"
                    f"File: {path}\n"
                    f"Invalid JSON at line {line_num}: {e}\n"
                    f"Re-run the simulation to regenerate a clean log."
                )

    if not entries:
        raise LogValidationError(
            f"ERROR: {label} log is empty.\n"
            f"File: {path}\n"
            f"Run the corresponding simulation before comparing."
        )

    return entries


def validate_complete(entries: list, expected: int, label: str, path: str):
    if len(entries) != expected:
        raise LogValidationError(
            f"ERROR: {label} run is incomplete.\n"
            f"Expected: {expected} timesteps\n"
            f"Found: {len(entries)} timesteps\n"
            f"File: {path}\n"
            f"Re-run the simulation before comparing."
        )


def summarize_run(entries: list, comfort_cfg: dict) -> dict:
    total_energy = sum(e["metrics"]["energy_kwh"] for e in entries)
    violations = sum(
        1 for e in entries
        if not (comfort_cfg["min_temp_c"] <= e["metrics"]["zone_temp_c"] <= comfort_cfg["max_temp_c"])
    )
    avg_temp = sum(e["metrics"]["zone_temp_c"] for e in entries) / len(entries)
    return {
        "timesteps": len(entries),
        "total_energy_kwh": round(total_energy, 3),
        "avg_zone_temp_c": round(avg_temp, 2),
        "comfort_violations": violations,
        "comfort_violation_rate_pct": round(100 * violations / len(entries), 1),
    }


def compare() -> dict:
    """Returns the comparison result dict on success.
    Raises LogValidationError (with a print-ready message) on any
    validation failure — caller is responsible for printing it and
    exiting without writing savings_summary.json."""
    cfg = load_config()
    expected = cfg["loop"]["max_iterations"]

    baseline_path = cfg["paths"]["baseline_log_output"]
    ai_path = cfg["paths"]["ai_log_output"]

    baseline_entries = load_log(baseline_path, "Baseline")
    ai_entries = load_log(ai_path, "AI")

    validate_complete(baseline_entries, expected, "Baseline", baseline_path)
    validate_complete(ai_entries, expected, "AI", ai_path)

    baseline_summary = summarize_run(baseline_entries, cfg["comfort"])
    ai_summary = summarize_run(ai_entries, cfg["comfort"])

    energy_saved_kwh = baseline_summary["total_energy_kwh"] - ai_summary["total_energy_kwh"]
    energy_saved_pct = (
        round(100 * energy_saved_kwh / baseline_summary["total_energy_kwh"], 2)
        if baseline_summary["total_energy_kwh"] > 0 else 0.0
    )

    result = {
        "baseline": baseline_summary,
        "ai_driven": ai_summary,
        "energy_saved_kwh": round(energy_saved_kwh, 3),
        "energy_saved_pct": energy_saved_pct,
        "comfort_maintained": ai_summary["comfort_violations"] <= baseline_summary["comfort_violations"],
    }

    with open(cfg["paths"]["summary_output"], "w") as f:
        json.dump(result, f, indent=2)

    return result


def print_report(result: dict):
    print("\n=== Eco-Loop Savings Report ===")
    print(f"Baseline total energy:  {result['baseline']['total_energy_kwh']} kWh "
          f"({result['baseline']['comfort_violations']} comfort violations)")
    print(f"AI-driven total energy: {result['ai_driven']['total_energy_kwh']} kWh "
          f"({result['ai_driven']['comfort_violations']} comfort violations)")
    print(f"Energy saved: {result['energy_saved_kwh']} kWh ({result['energy_saved_pct']}%)")
    print(f"Comfort maintained (violations did not increase): {result['comfort_maintained']}")
    print("================================\n")


if __name__ == "__main__":
    try:
        result = compare()
        print_report(result)
    except LogValidationError as e:
        print(str(e))
        sys.exit(1)