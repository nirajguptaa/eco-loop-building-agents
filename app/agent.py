from app.llm_provider import LLMProvider

SYSTEM_PROMPT = """You are an autonomous building energy control agent.
You will be given live building sensor metrics. Decide the best control
action to minimize energy use while keeping occupants comfortable.

Respond with ONLY a JSON object in exactly this shape:
{
  "temperature_setpoint": <number, Celsius>,
  "lighting": <number, percent 0-100>,
  "ventilation": "<low|medium|high>",
  "reason": "<one short sentence explaining the decision>"
}
"""

def build_user_prompt(metrics: dict, comfort_cfg: dict) -> str:
    return (
        f"Current metrics:\n"
        f"- zone_temp_c: {metrics['zone_temp_c']}\n"
        f"- outdoor_temp_c: {metrics['outdoor_temp_c']}\n"
        f"- energy_kwh (last step): {metrics['energy_kwh']}\n"
        f"- occupancy: {'occupied' if metrics['occupancy'] else 'unoccupied'}\n"
        f"- pmv (comfort index, target -0.5 to 0.5): {metrics['pmv']}\n\n"
        f"Comfort bounds: setpoint must stay between "
        f"{comfort_cfg['setpoint_min_c']} and {comfort_cfg['setpoint_max_c']} C.\n"
        f"Acceptable zone temp range: {comfort_cfg['min_temp_c']}-{comfort_cfg['max_temp_c']} C.\n"
        f"If unoccupied, prioritize energy savings. If occupied, prioritize comfort."
    )


class Agent:
    def __init__(self, llm: LLMProvider, comfort_cfg: dict):
        self.llm = llm
        self.comfort_cfg = comfort_cfg

    def decide(self, metrics: dict) -> dict:
        user_prompt = build_user_prompt(metrics, self.comfort_cfg)
        return self.llm.get_action(SYSTEM_PROMPT, user_prompt)