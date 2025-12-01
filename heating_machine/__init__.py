"""Heating machine configuration management package."""

from .config import (
    Config,
    ConfigError,
    ConfigManager,
    ConfigMetrics,
    DurationCeiling,
    HeatPreset,
    SafetyFlags,
    ThrottleThresholds,
)

__all__ = [
    "Config",
    "ConfigError",
    "ConfigManager",
    "ConfigMetrics",
    "DurationCeiling",
    "HeatPreset",
    "SafetyFlags",
    "ThrottleThresholds",
]
