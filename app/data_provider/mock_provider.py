import csv
from app.data_provider.base import DataProvider


class MockDataProvider(DataProvider):
    """Development Mode. Reads prerecorded, physically-plausible metrics
    (shape resembles a real EnergyPlus baseline day) and applies a simple,
    documented heuristic so control actions have a visible, honest effect
    on next-step energy use. This lets the agent, executor, dashboard, and
    logger be built and fully tested before EnergyPlus is touched at all."""

    def __init__(self, csv_path: str):
        with open(csv_path) as f:
            self.rows = list(csv.DictReader(f))
        self.last_action = None

    def get_metrics(self, timestep: int) -> dict:
        row = self.rows[timestep % len(self.rows)]
        zone_temp = float(row["zone_temp_c"])
        energy = float(row["energy_kwh"])

        # Heuristic: last accepted setpoint change nudges zone temp and
        # energy use in the physically expected direction. Documented,
        # not hidden — see ARCHITECTURE.md.
        if self.last_action:
            setpoint = self.last_action.get("temperature_setpoint")
            if setpoint is not None:
                zone_temp += (setpoint - zone_temp) * 0.3
                energy *= 0.9 if setpoint > zone_temp else 1.05

        return {
            "timestep": timestep,
            "zone_temp_c": round(zone_temp, 2),
            "energy_kwh": round(energy, 3),
            "pmv": round((zone_temp - 23) / 3, 2),  # simplified comfort proxy
            "occupancy": int(row["occupancy"]),
            "outdoor_temp_c": float(row["outdoor_temp_c"]),
        }

    def apply_action(self, action: dict) -> bool:
        self.last_action = action
        return True