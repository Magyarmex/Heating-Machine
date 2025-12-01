import pathlib
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from heating_machine.config import MachineConfig
from heating_machine.controller import HeatingMachineController


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def build_controller(clock: FakeClock, **overrides) -> HeatingMachineController:
    config = MachineConfig(
        max_temperature=overrides.get("max_temperature", 90.0),
        max_runtime_seconds=overrides.get("max_runtime_seconds", 10.0),
        heartbeat_timeout_seconds=overrides.get("heartbeat_timeout_seconds", 3.0),
        sensor_threshold=overrides.get("sensor_threshold", 80.0),
        max_load=overrides.get("max_load", 1.0),
    )
    return HeatingMachineController(config=config, clock=clock)


def test_start_and_stop_flow_records_metrics_and_flags():
    clock = FakeClock()
    controller = build_controller(clock)

    job = controller.start(job_id="job-1", requested_runtime=5.0, load=0.5, sensor_reading=40.0)
    assert controller.state == "running"
    assert job.target_stop_time == pytest.approx(5.0)

    controller.heartbeat(job_id="job-1")
    clock.advance(1.0)
    controller.stop(reason="user_request")

    snapshot = controller.debug_snapshot()
    assert snapshot["starts"] == 1
    assert snapshot["stops"] == 1
    assert snapshot["shutdowns"] == 0
    assert controller.status()["state"] == "stopped"
    assert controller.status()["last_error"] == "user_request"


def test_limit_enforcement_handles_runtime_and_temperature():
    clock = FakeClock()
    controller = build_controller(clock)
    controller.start(job_id="runtime-limited", requested_runtime=20.0, load=0.8, sensor_reading=45.0)

    # Advance beyond the max_runtime_seconds to trigger an auto shutdown
    clock.advance(11.0)
    controller.evaluate_safety(sensor_reading=50.0, load=0.8)

    snapshot = controller.debug_snapshot()
    assert controller.status()["state"] == "safe_shutdown"
    assert controller.status()["last_error"] == "runtime_exceeded"
    assert snapshot["shutdowns"] == 1
    assert snapshot["limit_enforced"] == 1

    # Temperature breach uses a fresh controller to isolate metrics
    clock = FakeClock()
    controller = build_controller(clock)
    controller.start(job_id="temp-limited", requested_runtime=5.0, load=0.8, sensor_reading=45.0)

    controller.evaluate_safety(sensor_reading=95.0, load=0.9)
    snapshot = controller.debug_snapshot()
    assert controller.status()["state"] == "safe_shutdown"
    assert controller.status()["last_error"] == "sensor_threshold_breach"
    assert snapshot["sensor_breach"] == 1
    assert snapshot["shutdowns"] == 1


def test_configuration_validation_rejects_bad_values():
    bad_config = MachineConfig(
        max_temperature=-1,
        max_runtime_seconds=5,
        heartbeat_timeout_seconds=2,
        sensor_threshold=1,
        max_load=1,
    )
    with pytest.raises(ValueError):
        bad_config.validate()

    inverted_thresholds = MachineConfig(
        max_temperature=50,
        max_runtime_seconds=5,
        heartbeat_timeout_seconds=2,
        sensor_threshold=55,
        max_load=1,
    )
    with pytest.raises(ValueError):
        inverted_thresholds.validate()

    clock = FakeClock()
    controller = build_controller(clock)
    with pytest.raises(ValueError):
        controller.start(job_id="bad-runtime", requested_runtime=0, load=0.5)


def test_fault_injection_covers_runaway_missed_heartbeat_and_sensor_breach():
    # Runaway detection
    clock = FakeClock()
    controller = build_controller(clock)
    controller.start(job_id="runaway", requested_runtime=5.0, load=0.9, sensor_reading=45.0)
    controller.evaluate_safety(sensor_reading=50.0, load=1.35)
    snapshot = controller.debug_snapshot()
    assert controller.status()["state"] == "safe_shutdown"
    assert controller.status()["last_error"] == "runaway_job_detected"
    assert snapshot["runaway_jobs"] == 1

    # Missed heartbeat
    clock = FakeClock()
    controller = build_controller(clock, heartbeat_timeout_seconds=2.0)
    controller.start(job_id="heartbeat", requested_runtime=5.0, load=0.8, sensor_reading=45.0)
    clock.advance(3.0)
    controller.evaluate_safety(sensor_reading=50.0, load=0.8)
    snapshot = controller.debug_snapshot()
    assert controller.status()["state"] == "safe_shutdown"
    assert controller.status()["last_error"] == "missed_heartbeat"
    assert snapshot["heartbeat_missed"] >= 1

    # Sensor breach mid-flight
    clock = FakeClock()
    controller = build_controller(clock)
    controller.start(job_id="sensor", requested_runtime=5.0, load=0.8, sensor_reading=45.0)
    controller.evaluate_safety(sensor_reading=82.0, load=0.8)
    snapshot = controller.debug_snapshot()
    assert controller.status()["state"] == "safe_shutdown"
    assert controller.status()["last_error"] == "sensor_threshold_breach"
    assert snapshot["sensor_breach"] == 1
