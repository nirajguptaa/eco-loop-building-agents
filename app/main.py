from app.config import load_config, get_llm_api_key
from app.llm_provider import LLMProvider
from app.agent import Agent
from app.executor import Executor
from app.logger import RunLogger
from app.data_provider.mock_provider import MockDataProvider


def build_provider(cfg: dict):
    if cfg["mode"] == "development":
        return MockDataProvider(cfg["paths"]["mock_metrics_csv"])
    elif cfg["mode"] == "production":
        from app.data_provider.energyplus_provider import EnergyPlusProvider
        return EnergyPlusProvider(idf_path="data/baseline_reference.idf", epw_path="")
    raise ValueError(f"Unknown mode: {cfg['mode']}")


def run():
    cfg = load_config()
    api_key = get_llm_api_key(cfg)

    provider = build_provider(cfg)
    llm = LLMProvider(cfg, api_key)
    agent = Agent(llm, cfg["comfort"], cfg["agent"])
    executor = Executor(provider, cfg["comfort"])
    logger = RunLogger(cfg["paths"]["ai_log_output"])

    previous_action = None
    for t in range(cfg["loop"]["max_iterations"]):
        metrics = provider.get_metrics(t)
        action = agent.decide(metrics, previous_action=previous_action)
        result = executor.run(action)
        previous_action = result.action
        logger.log(t, metrics, result.action, result.note)
        print(f"[t={t}] temp={metrics['zone_temp_c']}C energy={metrics['energy_kwh']}kWh "
              f"-> setpoint={result.action.get('temperature_setpoint')} ({result.note})")


if __name__ == "__main__":
    run()