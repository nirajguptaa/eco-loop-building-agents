from collections import deque

from app.llm_provider import LLMProvider

SYSTEM_PROMPT = """You are an autonomous building energy control agent.
Your PRIMARY objective is minimizing HVAC energy consumption.
Your SECONDARY objective is keeping zone temperature strictly within 20-26 C.
Comfort is a hard constraint (never violate it) — but within that constraint,
always choose the action that uses the LEAST energy.

Rules you must follow, in priority order:
1. If the previous setpoint is provided and it still keeps zone temperature
   within the comfort range for current conditions, KEEP IT UNCHANGED.
   Do not change a setpoint that is already working.
2. Only change the setpoint if current or projected conditions would violate
   comfort bounds, or if a clearly more efficient setpoint is still safely
   within bounds.
3. When you do change it, make the SMALLEST adjustment that fixes the issue.
   Do not overshoot or over-correct.
4. If occupancy is 0 (unoccupied), favor the setpoint closest to the warm
   end of the comfort range (up to 26 C) to minimize cooling energy, since
   comfort is not being actively experienced.
5. If occupancy is 1 (occupied), stay within comfort bounds but still prefer
   the warmest setpoint that keeps conditions comfortable — do not
   over-cool "to be safe."
6. Never oscillate: do not swing the setpoint back and forth between
   consecutive decisions. Stability is valued over fine-tuning.

You are also given two additional inputs — use both instead of reasoning
about the current instant in isolation:
- A FORECAST of outdoor temperature and occupancy for the next few
  timesteps. Use it to anticipate — e.g. pre-adjust ahead of an occupancy
  change or an outdoor temperature swing — rather than only reacting after
  conditions already changed.
- Your own RECENT DECISION HISTORY (setpoint and energy trend). Use it to
  reason about whether your last few decisions are working, not just
  whether the current single step looks fine.

Respond with ONLY a JSON object in exactly this shape:
{
  "temperature_setpoint": <number, Celsius>,
  "lighting": <number, percent 0-100>,
  "ventilation": "<low|medium|high>",
  "reason": "<one short sentence explaining the decision, including whether you kept or changed the previous setpoint and why>",
  "confidence": <number 0.0-1.0, how confident you are this is the best action given current and forecast conditions>,
  "risk_level": "<low|medium|high — comfort or energy risk if conditions shift beyond forecast>",
  "forecast_summary": "<one short sentence on what the forecast shows and how it influenced this decision>",
  "alternative_considered": "<one short sentence on an alternative action you considered and rejected, and why>"
}
"""


def build_forecast_block(forecast: list) -> str:
    if not forecast:
        return "Forecast: none available (end of data horizon or forecasting disabled).\n"
    lines = [
        f"  t+{i + 1}: outdoor_temp_c={f['outdoor_temp_c']}, "
        f"occupancy={'occupied' if f['occupancy'] else 'unoccupied'}"
        for i, f in enumerate(forecast)
    ]
    return f"Forecast (next {len(forecast)} steps):\n" + "\n".join(lines) + "\n"


def build_memory_block(history: list) -> str:
    if not history:
        return "Decision history: none yet (first decision of this run).\n"
    lines = [
        f"  t={h['timestep']}: setpoint={h['setpoint']}C, energy={h['energy_kwh']}kWh, "
        f"reason=\"{h['reason']}\""
        for h in history
    ]
    return "Recent decision history (oldest first):\n" + "\n".join(lines) + "\n"


def build_user_prompt(
    metrics: dict,
    comfort_cfg: dict,
    previous_action: dict = None,
    forecast: list = None,
    history: list = None,
) -> str:
    if previous_action and previous_action.get("temperature_setpoint") is not None:
        prev_line = (
            f"Previous setpoint: {previous_action['temperature_setpoint']} C "
            f"(previous reason: {previous_action.get('reason', 'n/a')}).\n"
            f"Default to keeping this unless current conditions require a change.\n"
        )
    else:
        prev_line = "No previous setpoint on record (first decision of the run).\n"

    return (
        f"Current metrics:\n"
        f"- zone_temp_c: {metrics['zone_temp_c']}\n"
        f"- outdoor_temp_c: {metrics['outdoor_temp_c']}\n"
        f"- energy_kwh (last step): {metrics['energy_kwh']}\n"
        f"- occupancy: {'occupied' if metrics['occupancy'] else 'unoccupied'}\n"
        f"- pmv (comfort index, target -0.5 to 0.5): {metrics['pmv']}\n\n"
        f"{prev_line}\n"
        f"{build_forecast_block(forecast or [])}\n"
        f"{build_memory_block(history or [])}\n"
        f"Comfort bounds: setpoint must stay between "
        f"{comfort_cfg['setpoint_min_c']} and {comfort_cfg['setpoint_max_c']} C.\n"
        f"Acceptable zone temp range: {comfort_cfg['min_temp_c']}-{comfort_cfg['max_temp_c']} C.\n"
        f"Remember: minimize energy first, within the hard comfort constraint. "
        f"Prefer keeping the previous setpoint if it still satisfies comfort."
    )


class Agent:
    def __init__(self, llm: LLMProvider, comfort_cfg: dict, agent_cfg: dict):
        self.llm = llm
        self.comfort_cfg = comfort_cfg
        self.min_meaningful_change_c = agent_cfg["min_meaningful_change_c"]
        # Decision Memory (Milestone 5, feature 2): bounded rolling history
        # of past decisions the agent reasons over, instead of only the
        # single previous action. Configurable, defaults to 5 if unset so
        # existing configs without this key still work.
        self.memory_window = agent_cfg.get("memory_window", 5)
        self.history = deque(maxlen=self.memory_window) if self.memory_window > 0 else deque(maxlen=0)

    def decide(self, timestep: int, metrics: dict, forecast: list = None, previous_action: dict = None) -> dict:
        user_prompt = build_user_prompt(
            metrics, self.comfort_cfg, previous_action, forecast, list(self.history)
        )
        action = self.llm.get_action(SYSTEM_PROMPT, user_prompt)
        action = self._apply_structured_defaults(action)
        action = self._apply_stability_guard(action, previous_action)
        self._update_history(timestep, metrics, action)
        return action

    @staticmethod
    def _apply_structured_defaults(action: dict) -> dict:
        """Structured Decision Output (Milestone 5, feature 3). Fills
        defaults for the new fields so replaying an OLD transcript
        (recorded before this milestone, missing these keys) still works
        unchanged — required for demo_mode backward compatibility."""
        action.setdefault("confidence", None)
        action.setdefault("risk_level", "unknown")
        action.setdefault("forecast_summary", "")
        action.setdefault("alternative_considered", "")
        return action

    def _update_history(self, timestep: int, metrics: dict, action: dict) -> None:
        if self.memory_window <= 0:
            return
        self.history.append({
            "timestep": timestep,
            "setpoint": action.get("temperature_setpoint"),
            "energy_kwh": metrics.get("energy_kwh"),
            "reason": action.get("reason", ""),
        })

    def _apply_stability_guard(self, action: dict, previous_action: dict) -> dict:
        if not previous_action or previous_action.get("temperature_setpoint") is None:
            return action
        prev_sp = previous_action["temperature_setpoint"]
        new_sp = action.get("temperature_setpoint")
        if new_sp is not None and abs(new_sp - prev_sp) < self.min_meaningful_change_c:
            action["temperature_setpoint"] = prev_sp
            action["reason"] = (
                f"{action.get('reason', '')} "
                f"[stability guard: change of {abs(new_sp - prev_sp):.2f}C was below "
                f"{self.min_meaningful_change_c}C threshold, kept previous setpoint {prev_sp}C]"
            ).strip()
        return action