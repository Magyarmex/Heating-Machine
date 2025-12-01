import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class HeartbeatMissed(Exception):
    """Raised when a job fails to emit heartbeats before the deadline."""


class SensorLimitExceeded(Exception):
    """Raised when system sensor limits are exceeded and stopping is requested."""


@dataclass
class WorkQueueMetrics:
    started: int = 0
    completed: int = 0
    failed: int = 0
    timed_out: int = 0
    heartbeat_missed: int = 0
    sensor_throttles: int = 0
    sensor_aborts: int = 0
    queue_rejections: int = 0

    def snapshot(self) -> Dict[str, int]:
        return {
            "started": self.started,
            "completed": self.completed,
            "failed": self.failed,
            "timed_out": self.timed_out,
            "heartbeat_missed": self.heartbeat_missed,
            "sensor_throttles": self.sensor_throttles,
            "sensor_aborts": self.sensor_aborts,
            "queue_rejections": self.queue_rejections,
        }


@dataclass
class SensorSnapshot:
    temperature_c: Optional[float] = None
    battery_percent: Optional[float] = None


class SensorPolicy:
    def __init__(
        self,
        reader: Optional[Callable[[], Awaitable[SensorSnapshot] | SensorSnapshot]] = None,
        *,
        max_temperature_c: Optional[float] = None,
        min_battery_percent: Optional[float] = None,
        cooldown_seconds: float = 0.5,
        stop_on_violation: bool = False,
        metrics: WorkQueueMetrics,
    ) -> None:
        self._reader = reader
        self._max_temperature_c = max_temperature_c
        self._min_battery_percent = min_battery_percent
        self._cooldown_seconds = cooldown_seconds
        self._stop_on_violation = stop_on_violation
        self._metrics = metrics

    async def _read_snapshot(self) -> Optional[SensorSnapshot]:
        if self._reader is None:
            return None
        result = self._reader()
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _has_violation(self, snapshot: Optional[SensorSnapshot]) -> bool:
        if snapshot is None:
            return False
        over_temp = (
            self._max_temperature_c is not None
            and snapshot.temperature_c is not None
            and snapshot.temperature_c > self._max_temperature_c
        )
        low_battery = (
            self._min_battery_percent is not None
            and snapshot.battery_percent is not None
            and snapshot.battery_percent < self._min_battery_percent
        )
        return over_temp or low_battery

    async def enforce(self) -> None:
        if self._reader is None:
            return
        while True:
            snapshot = await self._read_snapshot()
            if not self._has_violation(snapshot):
                return
            if self._stop_on_violation:
                self._metrics.sensor_aborts += 1
                raise SensorLimitExceeded(
                    "Sensor thresholds exceeded; stopping queued job"
                )
            self._metrics.sensor_throttles += 1
            logger.debug(
                "Sensor violation detected; throttling for %s seconds",
                self._cooldown_seconds,
            )
            await asyncio.sleep(self._cooldown_seconds)


class Heartbeat:
    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._event = asyncio.Event()
        self.ping()

    def ping(self) -> None:
        self._event.set()

    async def monitor(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._event.wait(), timeout=self._interval)
            except asyncio.TimeoutError as exc:
                raise HeartbeatMissed("Heartbeat not received within interval") from exc
            self._event.clear()


@dataclass
class JobRequest:
    fn: Callable[["JobContext"], Awaitable[Any]]
    duration_limit: Optional[float]
    heartbeat_interval: Optional[float]
    future: asyncio.Future


class JobContext:
    def __init__(self, heartbeat: Optional[Heartbeat]) -> None:
        self._heartbeat = heartbeat

    def ping(self) -> None:
        if self._heartbeat:
            self._heartbeat.ping()

    async def sleep(self, delay: float) -> None:
        await asyncio.sleep(delay)


class WorkQueue:
    def __init__(
        self,
        *,
        max_queue_size: int = 100,
        concurrency: int = 4,
        sensor_policy: Optional[SensorPolicy] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        metrics: Optional[WorkQueueMetrics] = None,
    ) -> None:
        self._queue: asyncio.Queue[Optional[JobRequest]] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._concurrency = concurrency
        self._workers: list[asyncio.Task] = []
        self._stopped = asyncio.Event()
        self._sensor_policy = sensor_policy
        self._loop = loop or asyncio.get_event_loop()
        self._metrics = metrics or WorkQueueMetrics()

    @property
    def metrics(self) -> WorkQueueMetrics:
        return self._metrics

    async def start(self) -> None:
        if self._workers:
            return
        self._stopped.clear()
        for _ in range(self._concurrency):
            self._workers.append(self._loop.create_task(self._worker_loop()))

    async def stop(self) -> None:
        if not self._workers:
            return
        self._stopped.set()
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def enqueue(
        self,
        fn: Callable[[JobContext], Awaitable[Any]],
        *,
        duration_limit: Optional[float] = None,
        heartbeat_interval: Optional[float] = None,
    ) -> asyncio.Future:
        future: asyncio.Future = self._loop.create_future()
        request = JobRequest(
            fn=fn,
            duration_limit=duration_limit,
            heartbeat_interval=heartbeat_interval,
            future=future,
        )
        try:
            self._queue.put_nowait(request)
        except asyncio.QueueFull:
            self._metrics.queue_rejections += 1
            future.set_exception(asyncio.QueueFull("work queue is full"))
        return future

    async def _worker_loop(self) -> None:
        while not self._stopped.is_set():
            request = await self._queue.get()
            if request is None:
                break
            if self._sensor_policy:
                try:
                    await self._sensor_policy.enforce()
                except SensorLimitExceeded as exc:
                    self._metrics.failed += 1
                    request.future.set_exception(exc)
                    self._queue.task_done()
                    continue
            self._metrics.started += 1
            heartbeat = Heartbeat(request.heartbeat_interval) if request.heartbeat_interval else None
            ctx = JobContext(heartbeat)

            job_coro = request.fn(ctx)

            async def run_job() -> Any:
                if request.duration_limit:
                    try:
                        return await asyncio.wait_for(job_coro, timeout=request.duration_limit)
                    except asyncio.TimeoutError as exc:
                        raise asyncio.TimeoutError(
                            f"job exceeded duration limit of {request.duration_limit}s"
                        ) from exc
                return await job_coro

            job_task = self._loop.create_task(run_job())
            monitor_task = self._loop.create_task(heartbeat.monitor()) if heartbeat else None

            try:
                if monitor_task:
                    done, _ = await asyncio.wait(
                        {job_task, monitor_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if monitor_task in done:
                        monitor_exc = monitor_task.exception()
                        if monitor_exc:
                            job_task.cancel()
                            try:
                                await job_task
                            except asyncio.CancelledError:
                                pass
                            raise monitor_exc
                    result = await job_task
                else:
                    result = await job_task
            except asyncio.TimeoutError as exc:
                self._metrics.timed_out += 1
                request.future.set_exception(exc)
            except HeartbeatMissed as exc:
                self._metrics.heartbeat_missed += 1
                request.future.set_exception(exc)
            except Exception as exc:  # pylint: disable=broad-except
                self._metrics.failed += 1
                request.future.set_exception(exc)
            else:
                self._metrics.completed += 1
                if not request.future.done():
                    request.future.set_result(result)
            finally:
                if monitor_task:
                    monitor_task.cancel()
                    try:
                        await monitor_task
                    except (asyncio.CancelledError, HeartbeatMissed):
                        pass
                self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional


logger = logging.getLogger(__name__)

