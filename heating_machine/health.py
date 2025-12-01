from __future__ import annotations

from typing import Dict

from .metrics import MetricsCollector


class HealthGate:
    def __init__(self, thresholds: Dict[str, float], metrics: MetricsCollector) -> None:
        self.thresholds = thresholds
        self.metrics = metrics

    def is_healthy(self, observed_metrics: Dict[str, float]) -> bool:
        for key, threshold in self.thresholds.items():
            value = float(observed_metrics.get(key, 0))
            if value > threshold:
                self.metrics.record_health(
                    "health_gate_blocked",
                    metric=key,
                    observed=value,
                    threshold=threshold,
                )
                return False

        self.metrics.record_health("health_gate_passed", **observed_metrics)
        return True
