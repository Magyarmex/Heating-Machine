import logging
import queue
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional

from .logging_utils import configure_logging


@dataclass
class EngineMetrics:
    target_load: float = 0.0
    actual_load: float = 0.0
    queue_depth: int = 0
    throttling_events: int = 0
    safety_trip_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_error: Optional[str] = None

    def snapshot(self) -> Dict[str, object]:
        return {
            "target_load": self.target_load,
            "actual_load": self.actual_load,
            "queue_depth": self.queue_depth,
            "throttling_events": self.throttling_events,
            "safety_trip_counts": dict(self.safety_trip_counts),
            "last_error": self.last_error,
        }


@dataclass
class EngineJob:
    duration: float
    source: str = "control"


class LoadEngine:
    """CPU load generator with guardrails and instrumentation."""

    def __init__(
        self,
        control_interval: float = 0.5,
        max_safe_load: float = 0.9,
        queue_limit: int = 32,
        smoothing_factor: float = 0.35,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.control_interval = control_interval
        self.max_safe_load = max_safe_load
        self.metrics = EngineMetrics()
        self._metrics_lock = threading.Lock()
        self._job_queue: queue.Queue[EngineJob] = queue.Queue(maxsize=queue_limit)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._session_end_time: Optional[float] = None
        self._session_active = False
        self._smoothing_factor = smoothing_factor
        self.logger = logger or configure_logging()
        self._last_guardrail_trigger: Optional[str] = None
        self._start_time: Optional[float] = None
        self._debug_mode = False

    # Session lifecycle -------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._start_time = time.time()
        self.logger.info("engine_started", extra={"extra_data": {"event": "session_start"}})

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.logger.info("engine_stopped", extra={"extra_data": {"event": "session_end"}})

    def start_session(self, duration: Optional[float] = None) -> None:
        now = time.perf_counter()
        self._session_end_time = now + duration if duration else None
        self._session_active = True
        self.logger.info(
            "session_started",
            extra={"extra_data": {"event": "session_start", "duration": duration}},
        )

    def stop_session(self) -> None:
        self._session_active = False
        self._session_end_time = None
        self.logger.info("session_finished", extra={"extra_data": {"event": "session_end"}})

    # Guardrails & configuration ---------------------------------------
    def set_target_load(self, target: float) -> float:
        target = min(max(target, 0.0), 1.0)
        adjusted_target = target
        if target > self.max_safe_load:
            adjusted_target = self.max_safe_load
            self._record_safety_trip("max_safe_load", target)
        with self._metrics_lock:
            self.metrics.target_load = adjusted_target
        return adjusted_target

    def _record_safety_trip(self, reason: str, requested: Optional[float] = None) -> None:
        with self._metrics_lock:
            self.metrics.safety_trip_counts[reason] += 1
        self._last_guardrail_trigger = reason
        self.logger.warning(
            "guardrail_triggered",
            extra={
                "extra_data": {
                    "event": "guardrail",
                    "reason": reason,
                    "requested_load": requested,
                    "safety_trip_counts": dict(self.metrics.safety_trip_counts),
                }
            },
        )
        if requested:
            self.logger.info(
                "guardrail_snapshot",
                extra={
                    "extra_data": {
                        "event": "guardrail_snapshot",
                        "actual_load": self.metrics.actual_load,
                        "target_load": self.metrics.target_load,
                        "requested_load": requested,
                        "queue_depth": self.metrics.queue_depth,
                    }
                },
            )

    # Health & readiness -----------------------------------------------
    def health(self) -> Dict[str, object]:
        with self._metrics_lock:
            return {
                "status": "ok",
                "metrics": self.metrics.snapshot(),
                "guardrail": self._last_guardrail_trigger,
            }

    def diagnostics(self) -> Dict[str, object]:
        """Return derived debug metrics, flags, and hints for dashboards."""

        with self._metrics_lock:
            metrics = self.metrics.snapshot()
        uptime_seconds = time.time() - self._start_time if self._start_time else 0.0
        flags = []
        if metrics["actual_load"] > 0.82:
            flags.append(
                {
                    "code": "LOAD-HOT",
                    "severity": "warn",
                    "message": "Actual load above 82%; monitor closely.",
                }
            )
        if metrics["queue_depth"] >= self._job_queue.maxsize * 0.75:
            flags.append(
                {
                    "code": "QUEUE-PRESSURE",
                    "severity": "warn",
                    "message": "Queue nearing capacity; throttling likely.",
                }
            )
        if metrics["last_error"]:
            flags.append({"code": "ERROR", "severity": "error", "message": metrics["last_error"]})

        cooldown_advice = "Stable"
        if metrics["throttling_events"] > 0 or metrics["safety_trip_counts"].get("overload"):
            cooldown_advice = "Reduce load and allow cooldown"

        return {
            "uptime_seconds": round(uptime_seconds, 2),
            "flags": flags,
            "cooldown_advice": cooldown_advice,
            "debug_mode": self._debug_mode,
        }

    def set_debug_mode(self, enabled: bool) -> None:
        self._debug_mode = enabled
        self.logger.info(
            "debug_mode_toggled",
            extra={"extra_data": {"event": "debug_mode", "enabled": enabled}},
        )

    def ready(self) -> Dict[str, object]:
        degraded = False
        reason = None
        with self._metrics_lock:
            if any(self.metrics.safety_trip_counts.values()):
                degraded = True
                reason = "safety_trip"
            elif self.metrics.queue_depth >= self._job_queue.maxsize * 0.9:
                degraded = True
                reason = "backpressure"
        status = "ready" if not degraded else "degraded"
        return {"status": status, "reason": reason}

    # Metrics ----------------------------------------------------------
    def _update_actual_load(self, busy_time: float) -> None:
        measured = min(max(busy_time / self.control_interval, 0.0), 1.0)
        with self._metrics_lock:
            previous = self.metrics.actual_load
            updated = (1 - self._smoothing_factor) * previous + self._smoothing_factor * measured
            self.metrics.actual_load = updated
            self.metrics.queue_depth = self._job_queue.qsize()
            if updated > self.max_safe_load:
                self._record_safety_trip("overload", requested=updated)

    def _increment_throttling(self) -> None:
        with self._metrics_lock:
            self.metrics.throttling_events += 1
            self.metrics.queue_depth = self._job_queue.qsize()
        self.logger.info(
            "throttling",
            extra={
                "extra_data": {
                    "event": "throttle",
                    "queue_depth": self.metrics.queue_depth,
                    "throttling_events": self.metrics.throttling_events,
                }
            },
        )

    # Control loop -----------------------------------------------------
    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            start = time.perf_counter()
            self.run_cycle()
            elapsed = time.perf_counter() - start
            sleep_for = max(self.control_interval - elapsed, 0.0)
            if sleep_for:
                time.sleep(sleep_for)

    def run_cycle(self) -> None:
        try:
            self._maybe_schedule_work()
            busy_time = self._process_one_job()
            if busy_time is None:
                # No job executed; decay actual load
                self._update_actual_load(0.0)
        except Exception as exc:  # noqa: BLE001
            with self._metrics_lock:
                self.metrics.last_error = str(exc)
            self.logger.exception(
                "control_loop_error", extra={"extra_data": {"event": "error", "error": str(exc)}}
            )
            self.logger.error(
                "control_loop_error_flag",
                extra={
                    "extra_data": {
                        "event": "error_flag",
                        "category": "control_loop",
                        "message": str(exc),
                        "queue_depth": self.metrics.queue_depth,
                        "throttling_events": self.metrics.throttling_events,
                    }
                },
            )

    def _maybe_schedule_work(self) -> None:
        now = time.perf_counter()
        if self._session_active and self._session_end_time and now >= self._session_end_time:
            self.stop_session()
        if not self._session_active:
            return
        target_load = self.metrics.target_load
        busy_duration = target_load * self.control_interval
        if busy_duration <= 0:
            return
        if self._job_queue.full():
            self._increment_throttling()
            return
        job = EngineJob(duration=busy_duration, source="control")
        self._job_queue.put_nowait(job)

    def _process_one_job(self) -> Optional[float]:
        try:
            job = self._job_queue.get_nowait()
        except queue.Empty:
            return None
        start = time.perf_counter()
        self._spin(job.duration)
        busy_time = time.perf_counter() - start
        self._update_actual_load(busy_time)
        self._job_queue.task_done()
        return busy_time

    @staticmethod
    def _spin(duration: float) -> None:
        end_time = time.perf_counter() + duration
        while time.perf_counter() < end_time:
            pass
