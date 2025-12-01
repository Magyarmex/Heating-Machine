import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


class ConfigError(Exception):
    """Raised when configuration validation fails."""


@dataclass
class HeatPreset:
    name: str
    target_temperature_c: float
    ramp_rate_c_per_minute: float
    high_risk: bool = False
    requires_elevated_approval: bool = False

    @classmethod
    def from_dict(cls, payload: Dict) -> "HeatPreset":
        try:
            name = str(payload["name"])
            target_temperature_c = float(payload["target_temperature_c"])
            ramp_rate_c_per_minute = float(payload["ramp_rate_c_per_minute"])
            high_risk = bool(payload.get("high_risk", False))
            requires_elevated_approval = bool(payload.get("requires_elevated_approval", False))
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid heat preset definition: {exc}") from exc

        preset = cls(
            name=name,
            target_temperature_c=target_temperature_c,
            ramp_rate_c_per_minute=ramp_rate_c_per_minute,
            high_risk=high_risk,
            requires_elevated_approval=requires_elevated_approval,
        )
        preset.validate()
        return preset

    def validate(self) -> None:
        if not self.name:
            raise ConfigError("Heat preset name cannot be empty")
        if self.target_temperature_c <= 0:
            raise ConfigError(f"Target temperature for preset '{self.name}' must be positive")
        if self.ramp_rate_c_per_minute <= 0:
            raise ConfigError(f"Ramp rate for preset '{self.name}' must be positive")


@dataclass
class DurationCeiling:
    max_minutes: int
    cooldown_minutes: int

    @classmethod
    def from_dict(cls, payload: Dict) -> "DurationCeiling":
        try:
            max_minutes = int(payload["max_minutes"])
            cooldown_minutes = int(payload.get("cooldown_minutes", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid duration ceiling definition: {exc}") from exc

        ceiling = cls(max_minutes=max_minutes, cooldown_minutes=cooldown_minutes)
        ceiling.validate()
        return ceiling

    def validate(self) -> None:
        if self.max_minutes <= 0:
            raise ConfigError("Max minutes must be positive")
        if self.cooldown_minutes < 0:
            raise ConfigError("Cooldown minutes cannot be negative")


@dataclass
class ThrottleThresholds:
    max_cpu_load: float
    max_temperature_c: float
    max_power_draw_watts: float

    @classmethod
    def from_dict(cls, payload: Dict) -> "ThrottleThresholds":
        try:
            max_cpu_load = float(payload["max_cpu_load"])
            max_temperature_c = float(payload["max_temperature_c"])
            max_power_draw_watts = float(payload["max_power_draw_watts"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid throttle threshold definition: {exc}") from exc

        thresholds = cls(
            max_cpu_load=max_cpu_load,
            max_temperature_c=max_temperature_c,
            max_power_draw_watts=max_power_draw_watts,
        )
        thresholds.validate()
        return thresholds

    def validate(self) -> None:
        if not 0 < self.max_cpu_load <= 1:
            raise ConfigError("Max CPU load must be between 0 and 1 inclusive")
        if self.max_temperature_c <= 0:
            raise ConfigError("Max temperature must be positive")
        if self.max_power_draw_watts <= 0:
            raise ConfigError("Max power draw must be positive")


@dataclass
class SafetyFlags:
    disable_high_risk_modes: bool = False
    require_elevated_approval: bool = False

    @classmethod
    def from_dict(cls, payload: Dict) -> "SafetyFlags":
        return cls(
            disable_high_risk_modes=bool(payload.get("disable_high_risk_modes", False)),
            require_elevated_approval=bool(payload.get("require_elevated_approval", False)),
        )


@dataclass
class Config:
    presets: List[HeatPreset]
    duration_ceiling: DurationCeiling
    throttle_thresholds: ThrottleThresholds
    flags: SafetyFlags
    disabled_high_risk_presets: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: Dict) -> "Config":
        try:
            raw_presets = payload["presets"]
            duration_data = payload["duration_ceiling"]
            throttle_data = payload["throttle_thresholds"]
            flags_data = payload.get("flags", {})
        except KeyError as exc:
            raise ConfigError(f"Missing required configuration section: {exc}") from exc

        presets = [HeatPreset.from_dict(item) for item in raw_presets]
        duration_ceiling = DurationCeiling.from_dict(duration_data)
        throttle_thresholds = ThrottleThresholds.from_dict(throttle_data)
        flags = SafetyFlags.from_dict(flags_data)

        config = cls(
            presets=presets,
            duration_ceiling=duration_ceiling,
            throttle_thresholds=throttle_thresholds,
            flags=flags,
        )
        config.validate()
        return config

    def validate(self) -> None:
        disabled: List[str] = []
        validated_presets: List[HeatPreset] = []
        for preset in self.presets:
            if self.flags.disable_high_risk_modes and preset.high_risk:
                disabled.append(preset.name)
                continue
            if self.flags.require_elevated_approval and preset.high_risk and not preset.requires_elevated_approval:
                raise ConfigError(
                    f"Preset '{preset.name}' is high risk and requires elevated approval, but no approval flag set"
                )
            validated_presets.append(preset)

        if not validated_presets:
            raise ConfigError("No enabled heat presets remain after applying safety flags")

        self.presets = validated_presets
        self.disabled_high_risk_presets = tuple(disabled)


@dataclass
class ConfigMetrics:
    reload_attempts: int = 0
    successful_reloads: int = 0
    validation_failures: int = 0
    high_risk_modes_disabled: int = 0
    last_reload_timestamp: Optional[float] = None
    last_error: Optional[str] = None

    def as_dict(self) -> Dict[str, Optional[float]]:
        return {
            "reload_attempts": self.reload_attempts,
            "successful_reloads": self.successful_reloads,
            "validation_failures": self.validation_failures,
            "high_risk_modes_disabled": self.high_risk_modes_disabled,
            "last_reload_timestamp": self.last_reload_timestamp,
            "last_error": self.last_error,
        }


class ConfigManager:
    """Manage loading and validating heat machine configurations."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._last_loaded_mtime: Optional[float] = None
        self.config: Optional[Config] = None
        self.metrics = ConfigMetrics()
        self.load()

    def load(self) -> Config:
        self.metrics.reload_attempts += 1
        try:
            with open(self.config_path, "r", encoding="utf-8") as config_file:
                payload = json.load(config_file)
            config = Config.from_dict(payload)
            self._last_loaded_mtime = os.path.getmtime(self.config_path)
            self.config = config
            self.metrics.successful_reloads += 1
            self.metrics.high_risk_modes_disabled = len(config.disabled_high_risk_presets)
            self.metrics.last_reload_timestamp = time.time()
            self.metrics.last_error = None
            return config
        except (OSError, json.JSONDecodeError, ConfigError) as exc:
            self.metrics.validation_failures += 1
            self.metrics.last_error = str(exc)
            raise

    def reload_if_stale(self, *, force: bool = False) -> bool:
        """Reload configuration when the file mtime changes or when forced.

        Returns True when a reload occurred, False otherwise.
        """
        if force:
            self.load()
            return True

        try:
            current_mtime = os.path.getmtime(self.config_path)
        except OSError:
            # Surface the issue through metrics and prevent silent failures.
            self.metrics.validation_failures += 1
            self.metrics.last_error = "Configuration file missing during reload check"
            raise

        if self._last_loaded_mtime is None or current_mtime > self._last_loaded_mtime:
            self.load()
            return True
        return False

    def is_mode_allowed(self, preset_name: str) -> bool:
        if not self.config:
            raise ConfigError("Configuration not loaded")
        for preset in self.config.presets:
            if preset.name == preset_name:
                if preset.high_risk and self.config.flags.disable_high_risk_modes:
                    return False
                if preset.high_risk and self.config.flags.require_elevated_approval and not preset.requires_elevated_approval:
                    return False
                return True
        return False

    def approval_required(self, preset_name: str) -> bool:
        if not self.config:
            raise ConfigError("Configuration not loaded")
        for preset in self.config.presets:
            if preset.name == preset_name:
                return preset.high_risk and (
                    self.config.flags.require_elevated_approval or preset.requires_elevated_approval
                )
        return False

    def debug_snapshot(self) -> Dict[str, object]:
        return {
            "metrics": self.metrics.as_dict(),
            "disabled_high_risk_presets": list(self.config.disabled_high_risk_presets) if self.config else [],
            "active_presets": [preset.name for preset in self.config.presets] if self.config else [],
        }
