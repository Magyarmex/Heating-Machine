from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import json


@dataclass
class EnvironmentProfile:
    name: str
    min_heat: int
    max_heat: int
    canary_steps: int
    health_thresholds: Dict[str, float]
    validation_checks: List[str]

    @property
    def increment(self) -> int:
        if self.canary_steps <= 0:
            return 0
        step = max(1, (self.max_heat - self.min_heat) // self.canary_steps)
        return step


class ConfigLoader:
    def __init__(self, config_path: Path | str = "configs/environments.json") -> None:
        self.config_path = Path(config_path)

    def load(self, environment: str) -> EnvironmentProfile:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file {self.config_path} missing")

        with self.config_path.open("r", encoding="utf-8") as handle:
            raw_config = json.load(handle) or {}

        if environment not in raw_config:
            available = ", ".join(sorted(raw_config.keys()))
            raise KeyError(f"Environment '{environment}' not found. Available: {available}")

        env_config = raw_config[environment]
        return EnvironmentProfile(
            name=environment,
            min_heat=int(env_config.get("min_heat", 0)),
            max_heat=int(env_config.get("max_heat", 0)),
            canary_steps=int(env_config.get("canary_steps", 0)),
            health_thresholds={k: float(v) for k, v in (env_config.get("health_thresholds") or {}).items()},
            validation_checks=list(env_config.get("validation_checks") or []),
        )
