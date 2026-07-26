from abc import ABC, abstractmethod


class DataProvider(ABC):
    """Every provider (Mock or EnergyPlus) implements exactly these two
    methods. The agent, executor, logger, and dashboard only ever talk
    to this interface — they never know which mode is active."""

    @abstractmethod
    def get_metrics(self, timestep: int) -> dict:
        """Returns: {zone_temp_c, energy_kwh, pmv, occupancy, outdoor_temp_c}"""
        raise NotImplementedError

    @abstractmethod
    def apply_action(self, action: dict) -> bool:
        """Applies {temperature_setpoint, lighting, ventilation}.
        Returns True if accepted, False if rejected/failed."""
        raise NotImplementedError