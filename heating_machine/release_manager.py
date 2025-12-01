from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from .config_loader import EnvironmentProfile
from .health import HealthGate
from .metrics import MetricsCollector
from .validation import ValidationSuite


@dataclass
class ReleaseState:
    environment: str
    heat_level: int
    last_stable: int
    history: List[int]
    failed: bool = False


class CanaryReleaseManager:
    def __init__(
        self,
        profile: EnvironmentProfile,
        metrics: MetricsCollector,
        health_gate: HealthGate,
        validation_suite: ValidationSuite,
    ) -> None:
        self.profile = profile
        self.metrics = metrics
        self.health_gate = health_gate
        self.validation_suite = validation_suite
        self.state = ReleaseState(
            environment=profile.name,
            heat_level=profile.min_heat,
            last_stable=profile.min_heat,
            history=[profile.min_heat],
        )

    def _raise_heat(self) -> None:
        next_level = min(self.profile.max_heat, self.state.heat_level + self.profile.increment)
        self.state.last_stable = self.state.heat_level
        self.state.heat_level = next_level
        self.state.history.append(next_level)
        self.metrics.record_event(
            "heat_increased",
            environment=self.profile.name,
            new_heat=next_level,
            last_stable=self.state.last_stable,
        )

    def rollback(self) -> None:
        self.metrics.record_error(
            "rollback_triggered",
            environment=self.profile.name,
            rollback_to=self.state.last_stable,
        )
        self.state.heat_level = self.state.last_stable
        self.state.history.append(self.state.last_stable)
        self.state.failed = True

    def run_canary(self, health_snapshots: Iterable[Dict[str, float]], telemetry: Dict[str, float | int | str]) -> ReleaseState:
        if not self.validation_suite.run(telemetry):
            self.rollback()
            return self.state

        for snapshot in health_snapshots:
            if not self.health_gate.is_healthy(snapshot):
                self.rollback()
                break
            self._raise_heat()

        if not self.state.failed and self.state.heat_level >= self.profile.max_heat:
            self.metrics.record_event("rollout_complete", environment=self.profile.name, target=self.state.heat_level)

        return self.state
