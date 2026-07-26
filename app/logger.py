import json
import time


class RunLogger:
    def __init__(self, path: str):
        self.path = path
        open(self.path, "w").close()  # fresh file per run

    def log(self, timestep: int, metrics: dict, action: dict, result_note: str):
        entry = {
            "timestamp": time.time(),
            "timestep": timestep,
            "metrics": metrics,
            "action": action,
            "note": result_note,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")