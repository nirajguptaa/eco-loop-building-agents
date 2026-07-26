"""
Replay LLM Provider — returns pre-recorded actions in order instead of
calling a live API. Used when config.yaml has demo_mode: true.

Pairs with the `record_path` option on LLMProvider (see app/llm_provider.py):
run once live to record a transcript, then replay that transcript
indefinitely at zero API cost. This is what makes a deterministic demo
video possible, and lets anyone (including a judge without a Groq key)
reproduce your AI run from the committed transcript file.

Same get_action(system_prompt, user_prompt) method signature as
LLMProvider, so Agent.decide() and everything above it works unchanged
with either provider — the caller never needs to know which one it has.
"""

import json
import os


class ReplayExhaustedError(Exception):
    """Raised when the transcript is missing, empty, or corrupted."""
    pass


class ReplayLLMProvider:
    def __init__(self, transcript_path: str):
        if not os.path.exists(transcript_path):
            raise ReplayExhaustedError(
                f"ERROR: demo_mode is enabled but no transcript was found.\n"
                f"Expected file: {transcript_path}\n"
                f"Run a live simulation once (demo_mode: false, valid API key) "
                f"to record one, or provide a transcript manually before "
                f"switching to demo_mode: true."
            )

        self._actions = []

        with open(transcript_path, "r") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()

                if not line:
                    continue

                try:
                    self._actions.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ReplayExhaustedError(
                        f"ERROR: demo transcript is corrupted.\n"
                        f"File: {transcript_path}\n"
                        f"Invalid JSON at line {line_num}: {e}\n"
                        f"Re-record the transcript with a live run."
                    )

        if not self._actions:
            raise ReplayExhaustedError(
                f"ERROR: demo transcript is empty.\n"
                f"File: {transcript_path}\n"
                f"Run a live simulation once (demo_mode: false) to record one."
            )

        self._index = 0

    def get_action(self, system_prompt: str, user_prompt: str) -> dict:
        """
        Return the next recorded action.

        If the transcript is shorter than the configured simulation,
        continue replaying by cycling through the recorded actions.
        This allows demo_mode to complete all iterations without making
        any API calls.

        system_prompt and user_prompt are accepted only to preserve the
        same interface as LLMProvider.
        """

        if not self._actions:
            raise ReplayExhaustedError(
                "ERROR: Demo transcript contains no recorded actions."
            )

        action = self._actions[self._index % len(self._actions)]
        self._index += 1
        return action