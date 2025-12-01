from heating_machine.config_loader import EnvironmentProfile
from heating_machine.health import HealthGate
from heating_machine.metrics import MetricsCollector
from heating_machine.release_manager import CanaryReleaseManager
from heating_machine.validation import ValidationSuite


def _build_manager():
    profile = EnvironmentProfile(
        name="test",
        min_heat=5,
        max_heat=15,
        canary_steps=2,
        health_thresholds={"error_rate": 0.05, "cpu_spike": 0.9},
        validation_checks=["ensure_min_capacity", "ensure_monitoring"],
    )
    metrics = MetricsCollector()
    health_gate = HealthGate(profile.health_thresholds, metrics)
    validation_suite = ValidationSuite(profile.validation_checks, metrics)
    return CanaryReleaseManager(profile, metrics, health_gate, validation_suite)


def test_validation_failure_triggers_rollback():
    manager = _build_manager()
    telemetry = {"available_capacity": 10, "monitoring": False}

    state = manager.run_canary([
        {"error_rate": 0.01, "cpu_spike": 0.1},
        {"error_rate": 0.02, "cpu_spike": 0.2},
    ], telemetry)

    assert state.failed is True
    assert state.heat_level == state.last_stable == 5
    assert any(event.level == "error" and event.message == "rollback_triggered" for event in manager.metrics.events)


def test_health_gate_failure_rolls_back_to_last_stable():
    manager = _build_manager()
    telemetry = {"available_capacity": 30, "monitoring": True}

    state = manager.run_canary([
        {"error_rate": 0.01, "cpu_spike": 0.1},
        {"error_rate": 0.1, "cpu_spike": 0.95},
    ], telemetry)

    assert state.failed is True
    assert state.heat_level == state.last_stable
    assert manager.state.history[-1] == state.last_stable


def test_successful_rollout_reaches_max_heat():
    manager = _build_manager()
    telemetry = {"available_capacity": 50, "monitoring": True}

    state = manager.run_canary([
        {"error_rate": 0.01, "cpu_spike": 0.1},
        {"error_rate": 0.02, "cpu_spike": 0.2},
        {"error_rate": 0.02, "cpu_spike": 0.2},
    ], telemetry)

    assert state.failed is False
    assert state.heat_level == manager.profile.max_heat
    assert any(event.message == "rollout_complete" for event in manager.metrics.events)
