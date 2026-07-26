from app.data_provider.base import DataProvider


class EnergyPlusProvider(DataProvider):
    """Production Mode. Wraps the PyEnergyPlus live callback API.
    Implemented in the EnergyPlus integration milestone — kept as a
    stub now so main.py and config can already point at 'production'
    mode without the rest of the app changing shape."""

    def __init__(self, idf_path: str, epw_path: str):
        self.idf_path = idf_path
        self.epw_path = epw_path
        raise NotImplementedError(
            "EnergyPlus integration not yet implemented — use mode: development in config.yaml"
        )

    def get_metrics(self, timestep: int) -> dict:
        raise NotImplementedError

    def apply_action(self, action: dict) -> bool:
        raise NotImplementedError

    def get_forecast(self, timestep: int, window: int) -> list:
        raise NotImplementedError