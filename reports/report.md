# Eco-Loop Building Agents — Executive Report

## Executive Summary
- **Total AI-driven energy:** 154.394 kWh
- **Baseline energy:** 171.966 kWh
- **Energy saved:** 17.572 kWh (10.22%)
- **Comfort maintained:** Yes
- **Total AI decisions:** 96
- **Average confidence:** None
- **Average risk:** None (score None)
- **Peak occupancy:** 41 timesteps (42.7% of the run)
- **Peak energy period:** t=49 (12:15), 2.853 kWh
- **Largest HVAC adjustment:** 0.0 C
- **Most common action:** ventilation = low (100.0% of decisions)

## Simulation Statistics
| | Baseline | AI-driven |
|---|---|---|
| Timesteps | 96 | 96 |
| Total energy (kWh) | 171.966 | 154.394 |
| Avg zone temp (C) | 22.99 | 23.88 |
| Comfort violations | 0 | 0 |
| Comfort violation rate | 0.0% | 0.0% |

## AI Performance
- Average setpoint adjustment: 0.0 C
- Largest setpoint adjustment: 0.0 C
- Setpoint changed in 0.0% of decisions (Decision Stability)

## Building Insights
- Peak energy demand (2.853 kWh at t=49, 12:15) occurred during an occupied period, consistent with occupancy-driven cooling and lighting load.
- Most savings occurred while occupied (15.92 kWh saved occupied vs 1.65 kWh unoccupied) — the agent is finding efficiency even under active comfort constraints.
- Outdoor temperature increased HVAC demand — average energy use was 2.334 kWh above the median outdoor temperature vs 0.912 kWh below it.
- Lighting reductions contributed to savings — average AI lighting level (0.0%) was below the baseline's fixed 80%.
- Comfort was maintained throughout the simulation with zero violations of the 20-26 C comfort band.
- Setpoint decisions were highly stable — changed in only 0.0% of steps, avoiding unnecessary oscillation.
- Confidence scores were not available for this run (likely a replayed transcript recorded before Milestone 5, or a run without structured output).
- Self-verification results were not available for this run.

## Recommendations
- Increase the forecast horizon (currently 4 steps) so the agent can anticipate occupancy and outdoor-temperature swings further ahead.
- Pre-cool before occupancy: lower the setpoint one or two steps ahead of an occupancy transition instead of reacting only after occupancy begins.
- Overnight ventilation is already minimized during unoccupied nighttime hours — no change recommended here.
- Investigate the afternoon peak at 12:15 (t=49, 2.853 kWh) — this is a good candidate for a targeted setpoint or forecast-horizon adjustment.
- Tune the lighting schedule to track occupancy more closely — current occupied vs unoccupied lighting levels are similar, leaving savings on the table.
