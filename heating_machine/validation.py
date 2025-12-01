from __future__ import annotations

from typing import Dict, List

from .metrics import MetricsCollector


class ValidationSuite:
    def __init__(self, checks: List[str], metrics: MetricsCollector) -> None:
        self.checks = checks
        self.metrics = metrics

    def run(self, telemetry: Dict[str, float | int | str]) -> bool:
        failed_checks = []

        if "ensure_min_capacity" in self.checks and telemetry.get("available_capacity", 0) < 20:
            failed_checks.append("ensure_min_capacity")

        if "ensure_monitoring" in self.checks and not telemetry.get("monitoring", False):
            failed_checks.append("ensure_monitoring")

        if "ensure_release_notes" in self.checks and not telemetry.get("release_notes", False):
            failed_checks.append("ensure_release_notes")

        if failed_checks:
            self.metrics.record_error("validation_failed", failed_checks=failed_checks, telemetry=telemetry)
            return False

        self.metrics.record_event("validation_passed", telemetry=telemetry)
        return True
