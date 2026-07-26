import os
import yaml

def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    return cfg

def get_llm_api_key(cfg: dict) -> str:
    key_env = cfg["llm"]["api_key_env"]
    key = os.environ.get(key_env)
    if not key and not cfg.get("demo_mode"):
        raise RuntimeError(
            f"Environment variable {key_env} is not set. "
            f"Export your LLM provider's API key before running in live mode."
        )
    return key or ""