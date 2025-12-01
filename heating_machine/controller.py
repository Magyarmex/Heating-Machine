import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from .config import MachineConfig


@dataclass
class JobState:
    job_id: str
    start_time: float
    target_stop_time: float
    last_heartbeat: float
    load: float
    sensor_reading: float


@dataclass
class DebugMetrics:
    starts: int = 0
    stops: int = 0
    shutdowns: int = 0
    heartbeat_missed: int = 0
    sensor_breach: int = 0
    runaway_jobs: int = 0
    limit_enforced: int = 0
    config_errors: int = 0


class HeatingMachineController:
    """Coordinates the heating machine lifecycle and safety checks."""

    def __init__(self, config: MachineConfig, clock: Optional[Callable[[], float]] = None):
        self.config = config
        self.clock = clock or time.time
        self.config.validate()

        self.state: str = "idle"
        self.active_job: Optional[JobState] = None
        self.flags: Dict[str, Optional[str]] = {"safe_shutdown": False, "last_error": None}
        self.metrics = DebugMetrics()

    def start(self, job_id: str, requested_runtime: float, load: float, sensor_reading: float = 0.0) -> JobState:
        """Start the heating workload after validating bounds."""
        self.config.validate()
        if self.active_job is not None:
            self.flags.update(last_error="job_already_running")
            raise RuntimeError("Job already running")

        if requested_runtime <= 0:
            self.metrics.config_errors += 1
            raise ValueError("requested_runtime must be greater than zero")

        if load <= 0 or load > self.config.max_load:
            self.metrics.limit_enforced += 1
            raise ValueError("load must be within the configured limits")

        if sensor_reading >= self.config.sensor_threshold:
            self.metrics.sensor_breach += 1
            raise RuntimeError("sensor reading already above safety threshold")

        now = self.clock()
        target_stop_time = now + min(requested_runtime, self.config.max_runtime_seconds)
        self.active_job = JobState(
            job_id=job_id,
            start_time=now,
            target_stop_time=target_stop_time,
            last_heartbeat=now,
            load=load,
            sensor_reading=sensor_reading,
        )
        self.state = "running"
        self.flags.update(safe_shutdown=False, last_error=None)
        self.metrics.starts += 1
        return self.active_job

    def heartbeat(self, job_id: str) -> None:
        if self.active_job is None or self.active_job.job_id != job_id:
            self.metrics.heartbeat_missed += 1
            raise RuntimeError("Heartbeat received for unknown job")

        self.active_job.last_heartbeat = self.clock()

    def stop(self, reason: str = "user_stop") -> None:
        if self.active_job is None:
            return
        self.state = "stopped"
        self.active_job = None
        self.metrics.stops += 1
        self.flags.update(last_error=reason, safe_shutdown=False)

    def evaluate_safety(self, sensor_reading: float, load: float) -> None:
        """Run safety checks and shut down when a limit is exceeded."""
        if self.active_job is None:
            return

        now = self.clock()
        job = self.active_job
        job.sensor_reading = sensor_reading
        job.load = load

        if now >= job.target_stop_time:
            self._safe_shutdown("runtime_exceeded")
            self.metrics.limit_enforced += 1
            return

        if now - job.last_heartbeat > self.config.heartbeat_timeout_seconds:
            self.metrics.heartbeat_missed += 1
            self._safe_shutdown("missed_heartbeat")
            return

        if sensor_reading >= self.config.max_temperature or sensor_reading >= self.config.sensor_threshold:
            self.metrics.sensor_breach += 1
            self._safe_shutdown("sensor_threshold_breach")
            return

        if load > self.config.max_load * 1.25:
            # runaway detection: load significantly exceeds the envelope
            self.metrics.runaway_jobs += 1
            self._safe_shutdown("runaway_job_detected")
            return

    def _safe_shutdown(self, reason: str) -> None:
        self.state = "safe_shutdown"
        self.flags.update(safe_shutdown=True, last_error=reason)
        self.metrics.shutdowns += 1
        self.active_job = None

    def status(self) -> Dict[str, Optional[str]]:
        return {"state": self.state, **self.flags}

    def debug_snapshot(self) -> Dict[str, float]:
        return {
            "starts": self.metrics.starts,
            "stops": self.metrics.stops,
            "shutdowns": self.metrics.shutdowns,
            "heartbeat_missed": self.metrics.heartbeat_missed,
            "sensor_breach": self.metrics.sensor_breach,
            "runaway_jobs": self.metrics.runaway_jobs,
            "limit_enforced": self.metrics.limit_enforced,
            "config_errors": self.metrics.config_errors,
        }
