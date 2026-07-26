class ExecutionResult:
    def __init__(self, accepted: bool, action: dict, note: str = ""):
        self.accepted = accepted
        self.action = action
        self.note = note


class Executor:
    """Validates LLM actions against hard comfort/safety bounds before
    they ever reach the data provider. This is the Thermal Comfort
    safeguard enforced in code — not left to hope-the-prompt-works."""

    def __init__(self, provider, comfort_cfg: dict):
        self.provider = provider
        self.comfort_cfg = comfort_cfg

    def run(self, action: dict) -> ExecutionResult:
        setpoint = action.get("temperature_setpoint")
        lo, hi = self.comfort_cfg["setpoint_min_c"], self.comfort_cfg["setpoint_max_c"]

        if setpoint is None or not (lo <= setpoint <= hi):
            clamped = max(lo, min(hi, setpoint if setpoint is not None else (lo + hi) / 2))
            action["temperature_setpoint"] = clamped
            note = f"Setpoint {setpoint} out of bounds [{lo},{hi}] — clamped to {clamped}."
            ok = self.provider.apply_action(action)
            return ExecutionResult(ok, action, note)

        ok = self.provider.apply_action(action)
        return ExecutionResult(ok, action, "accepted as-is")