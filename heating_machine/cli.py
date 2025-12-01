from __future__ import annotations

import argparse
from typing import Dict

from .config_loader import ConfigLoader
from .health import HealthGate
from .metrics import MetricsCollector
from .release_manager import CanaryReleaseManager
from .validation import ValidationSuite


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heating machine deployment controller")
    parser.add_argument("environment", choices=["development", "staging", "production"], help="Target environment")
    parser.add_argument(
        "--simulate-error-rate",
        type=float,
        nargs="*",
        default=[0.0],
        help="Error rate samples used to simulate canary health checks",
    )
    parser.add_argument(
        "--simulate-cpu-spike",
        type=float,
        nargs="*",
        default=[0.0],
        help="CPU spike samples used to simulate canary health checks",
    )
    parser.add_argument("--monitoring", action="store_true", help="Flag to indicate monitoring is active")
    parser.add_argument("--release-notes", action="store_true", help="Flag to confirm release notes are published")
    parser.add_argument(
        "--available-capacity",
        type=int,
        default=0,
        help="Available capacity percentage before raising heat levels",
    )
    return parser.parse_args()


def build_manager(environment: str, telemetry: Dict[str, float | int | str]) -> CanaryReleaseManager:
    loader = ConfigLoader()
    profile = loader.load(environment)
    metrics = MetricsCollector()
    health_gate = HealthGate(profile.health_thresholds, metrics)
    validation_suite = ValidationSuite(profile.validation_checks, metrics)
    return CanaryReleaseManager(profile, metrics, health_gate, validation_suite)


def main() -> None:
    args = _parse_args()
    telemetry = {
        "monitoring": args.monitoring,
        "release_notes": args.release_notes,
        "available_capacity": args.available_capacity,
    }
    manager = build_manager(args.environment, telemetry)

    snapshots = []
    for error_rate, cpu_spike in zip(args.simulate_error_rate, args.simulate_cpu_spike):
        snapshots.append({"error_rate": error_rate, "cpu_spike": cpu_spike})

    state = manager.run_canary(snapshots, telemetry)

    for event in manager.metrics.events:
        print(f"[{event.level.upper()}] {event.message}: {event.details}")

    if state.failed:
        print("Rollback completed. Heat level returned to", state.heat_level)
    else:
        print("Deployment successful at heat level", state.heat_level)


if __name__ == "__main__":
    main()
