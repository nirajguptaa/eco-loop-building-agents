"""One-off script to (re)generate data/mock_metrics.csv.
Deterministic via a fixed random seed — run this if the CSV is ever
deleted or you want to regenerate a fresh mock day."""
import csv
import math
import os
import random

# Resolve output path relative to the repo root (parent of this scripts/
# folder), not the caller's current working directory. This makes the
# script safe to run from anywhere: `python scripts/generate_mock_data.py`
# or `cd scripts && python generate_mock_data.py` both write to the same
# correct data/mock_metrics.csv.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "mock_metrics.csv")

NUM_TIMESTEPS = 96  # 24h at 15-min steps — must match config.yaml's loop.max_iterations

random.seed(42)
rows = []
for t in range(NUM_TIMESTEPS):
    hour = (t * 15 / 60) % 24
    occupancy = 1 if 8 <= hour <= 18 else 0
    outdoor = 22 + 6 * math.sin((hour - 6) / 24 * 2 * math.pi)
    zone_temp = 23 + 1.5 * math.sin((hour - 9) / 24 * 2 * math.pi) + random.uniform(-0.3, 0.3)
    energy = (2.5 if occupancy else 1.0) + max(0, outdoor - 24) * 0.15 + random.uniform(-0.1, 0.1)
    rows.append([t, round(hour, 2), occupancy, round(outdoor, 2), round(zone_temp, 2), round(energy, 3)])

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestep", "hour", "occupancy", "outdoor_temp_c", "zone_temp_c", "energy_kwh"])
    w.writerows(rows)

print(f"wrote {len(rows)} rows to {OUTPUT_PATH}")