from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List


class ConfigError(Exception):
    """Raised when configuration validation fails."""


@dataclass
class HeatPreset:
    name: str
    target_temperature_c: float
    ramp_rate_c_per_minute: float
    high_risk: bool = False
    requires_elevated_approval: bool = False

    def validate(self) -> None:
        for field_name, value in (
            ("target_temperature_c", self.target_temperature_c),
            ("ramp_rate_c_per_minute", self.ramp_rate_c_per_minute),
        ):
            if value <= 0:
                raise ConfigError(f"{field_name} must be positive")


@dataclass
class DurationCeiling:
    max_minutes: int
    cooldown_minutes: int

    def validate(self) -> None:
        if self.max_minutes <= 0:
            raise ConfigError("max_minutes must be positive")
        if self.cooldown_minutes < 0:
            raise ConfigError("cooldown_minutes cannot be negative")


@dataclass
class ThrottleThresholds:
    max_cpu_load: float
    max_temperature_c: float
    max_power_draw_watts: float

    def validate(self) -> None:
        for field_name, value in (
            ("max_cpu_load", self.max_cpu_load),
            ("max_temperature_c", self.max_temperature_c),
            ("max_power_draw_watts", self.max_power_draw_watts),
        ):
            if value <= 0:
                raise ConfigError(f"{field_name} must be positive")


@dataclass
class SafetyFlags:
    disable_high_risk_modes: bool = True
    require_elevated_approval: bool = False


@dataclass
class Config:
    presets: List[HeatPreset]
    duration_ceiling: DurationCeiling
    throttle_thresholds: ThrottleThresholds
    flags: SafetyFlags

    @classmethod
    def from_dict(cls, payload: Dict) -> "Config":
        try:
            raw_presets = payload["presets"]
            raw_duration = payload["duration_ceiling"]
            raw_throttle = payload["throttle_thresholds"]
            raw_flags = payload["flags"]
        except KeyError as exc:  # pragma: no cover - explicit for clarity
            raise ConfigError(f"Missing required config section: {exc.args[0]}") from exc

        presets = [
            HeatPreset(
                name=item["name"],
                target_temperature_c=float(item["target_temperature_c"]),
                ramp_rate_c_per_minute=float(item["ramp_rate_c_per_minute"]),
                high_risk=bool(item.get("high_risk", False)),
                requires_elevated_approval=bool(item.get("requires_elevated_approval", False)),
            )
            for item in raw_presets
        ]

        duration = DurationCeiling(
            max_minutes=int(raw_duration["max_minutes"]),
            cooldown_minutes=int(raw_duration.get("cooldown_minutes", 0)),
        )

        thresholds = ThrottleThresholds(
            max_cpu_load=float(raw_throttle["max_cpu_load"]),
            max_temperature_c=float(raw_throttle["max_temperature_c"]),
            max_power_draw_watts=float(raw_throttle["max_power_draw_watts"]),
        )

        flags = SafetyFlags(
            disable_high_risk_modes=bool(raw_flags.get("disable_high_risk_modes", True)),
            require_elevated_approval=bool(raw_flags.get("require_elevated_approval", False)),
        )

        config = cls(
            presets=presets,
            duration_ceiling=duration,
            throttle_thresholds=thresholds,
            flags=flags,
        )
        config.validate()
        return config

    @classmethod
    def from_file(cls, path: Path | str) -> "Config":
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls.from_dict(payload)

    def validate(self) -> None:
        if not self.presets:
            raise ConfigError("At least one preset must be defined")
        for preset in self.presets:
            preset.validate()
        self.duration_ceiling.validate()
        self.throttle_thresholds.validate()


@dataclass
class ConfigMetrics:
    reload_attempts: int = 0
    high_risk_modes_disabled: int = 0


class ConfigManager:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Config file {self.path} is missing")
        self.metrics = ConfigMetrics()
        self._last_mtime: float | None = None
        self._disabled_high_risk: List[str] = []
        self.config = self._load()

    def _load(self) -> Config:
        config = Config.from_file(self.path)
        config = self._apply_flags(config)
        self._last_mtime = self.path.stat().st_mtime
        return config

    def _apply_flags(self, config: Config) -> Config:
        self._disabled_high_risk = []
        if config.flags.disable_high_risk_modes:
            allowed_presets = []
            for preset in config.presets:
                if preset.high_risk:
                    self._disabled_high_risk.append(preset.name)
                else:
                    allowed_presets.append(preset)
            if self._disabled_high_risk:
                self.metrics.high_risk_modes_disabled += len(self._disabled_high_risk)
            config = replace(config, presets=allowed_presets)

        if config.flags.require_elevated_approval:
            for preset in config.presets:
                if preset.high_risk and not preset.requires_elevated_approval:
                    raise ConfigError(
                        f"Preset '{preset.name}' requires elevated approval when flagged"
                    )
        return config

    def reload_if_stale(self) -> bool:
        mtime = self.path.stat().st_mtime
        if self._last_mtime is not None and mtime <= self._last_mtime:
            return False
        self.metrics.reload_attempts += 1
        self.config = self._load()
        return True

    def is_mode_allowed(self, preset_name: str) -> bool:
        return any(preset.name == preset_name for preset in self.config.presets)

    def approval_required(self, preset_name: str) -> bool:
        preset = next((p for p in self.config.presets if p.name == preset_name), None)
        if preset is None:
            return False
        return preset.requires_elevated_approval or (
            preset.high_risk and self.config.flags.require_elevated_approval
        )

    def debug_snapshot(self) -> Dict[str, object]:
        return {
            "disabled_high_risk_presets": list(self._disabled_high_risk),
            "reload_attempts": self.metrics.reload_attempts,
            "high_risk_modes_disabled": self.metrics.high_risk_modes_disabled,
            "presets": [preset.name for preset in self.config.presets],
        }


@dataclass
class MachineConfig:
    """Configuration contract for the heating machine safety envelope."""

    max_temperature: float
    max_runtime_seconds: float
    heartbeat_timeout_seconds: float
    sensor_threshold: float
    max_load: float = 1.0

    def validate(self) -> None:
        """Ensure the configuration is sane before running."""
        for field_name, value in (
            ("max_temperature", self.max_temperature),
            ("max_runtime_seconds", self.max_runtime_seconds),
            ("heartbeat_timeout_seconds", self.heartbeat_timeout_seconds),
            ("sensor_threshold", self.sensor_threshold),
            ("max_load", self.max_load),
        ):
            if value <= 0:
                raise ValueError(f"{field_name} must be greater than zero")

        if self.sensor_threshold > self.max_temperature:
            raise ValueError("sensor_threshold cannot exceed max_temperature")
