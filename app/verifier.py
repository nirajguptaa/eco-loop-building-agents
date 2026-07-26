"""
Verifier — Self-Verification stage (Milestone 5, feature 4).

Sits between Agent.decide() and Executor.run(). Deliberately rule-based,
not a second LLM call: checking a JSON action for bound compliance and
internal consistency doesn't need a model, and a second LLM call would
add latency/cost/failure-modes for no clear benefit. See SKILL notes in
the milestone brief — "prefer rule-based unless clearly justified."

Non-blocking by design: this ANNOTATES the action with a pass/fail flag
and human-readable notes for explainability/dashboard purposes. It does
NOT stop the action from reaching the Executor. The Executor remains the
one and only hard safety gate (it clamps out-of-bounds setpoints before
they ever reach the data provider) — that authority is not duplicated or
weakened here.
"""


class Verifier:
    def __init__(self, comfort_cfg: dict, verification_cfg: dict = None):
        verification_cfg = verification_cfg or {}
        self.enabled = verification_cfg.get("enabled", True)
        self.comfort_cfg = comfort_cfg
        self.max_setpoint_jump_c = verification_cfg.get("max_setpoint_jump_c", 3.0)

    def verify(self, action: dict, previous_action: dict = None) -> tuple:
        """Returns (passed: bool, notes: str). Never raises — a verifier
        that can crash the loop is worse than no verifier."""
        if not self.enabled:
            return True, "verification disabled in config"

        notes = []
        passed = True
        setpoint = action.get("temperature_setpoint")
        lo = self.comfort_cfg["setpoint_min_c"]
        hi = self.comfort_cfg["setpoint_max_c"]

        if setpoint is None:
            passed = False
            notes.append("missing temperature_setpoint")
        elif not (lo <= setpoint <= hi):
            passed = False
            notes.append(f"setpoint {setpoint}C outside comfort bounds [{lo},{hi}]C")

        if (
            previous_action
            and previous_action.get("temperature_setpoint") is not None
            and setpoint is not None
        ):
            jump = abs(setpoint - previous_action["temperature_setpoint"])
            if jump > self.max_setpoint_jump_c:
                passed = False
                notes.append(
                    f"setpoint jump of {jump:.2f}C exceeds max allowed "
                    f"{self.max_setpoint_jump_c}C"
                )

        risk_level = action.get("risk_level")
        confidence = action.get("confidence")
        if risk_level == "high" and confidence is not None:
            try:
                if float(confidence) >= 0.9:
                    notes.append(
                        "inconsistent: risk_level=high paired with confidence>=0.9"
                    )
            except (TypeError, ValueError):
                pass

        if not notes:
            notes.append("all checks passed")

        return passed, "; ".join(notes)