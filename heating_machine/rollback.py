from __future__ import annotations

from typing import Dict, Iterable

from .config_loader import ConfigLoader
from .health import HealthGate
from .metrics import MetricsCollector
from .release_manager import CanaryReleaseManager
from .validation import ValidationSuite


def run_canary_with_rollback(
    environment: str,
    health_snapshots: Iterable[Dict[str, float]],
    telemetry: Dict[str, float | int | str],
) -> CanaryReleaseManager:
    loader = ConfigLoader()
    profile = loader.load(environment)
    metrics = MetricsCollector()
    health_gate = HealthGate(profile.health_thresholds, metrics)
    validation_suite = ValidationSuite(profile.validation_checks, metrics)
    manager = CanaryReleaseManager(profile, metrics, health_gate, validation_suite)
    manager.run_canary(health_snapshots, telemetry)
    return manager


def one_click_rollback(manager: CanaryReleaseManager) -> None:
    manager.rollback()
