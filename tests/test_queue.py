import asyncio
import time

import pytest

from heating_machine.queue import (
    HeartbeatMissed,
    SensorLimitExceeded,
    SensorPolicy,
    SensorSnapshot,
    WorkQueue,
    WorkQueueMetrics,
)


def test_workqueue_runs_jobs_and_respects_capacity():
    async def scenario():
        metrics = WorkQueueMetrics()
        queue = WorkQueue(max_queue_size=2, concurrency=2, metrics=metrics)
        await queue.start()

        async def job(ctx, value):
            await ctx.sleep(0.05)
            return value * 2

        futures = [
            await queue.enqueue(lambda ctx, i=i: job(ctx, i)) for i in range(2)
        ]
        rejected = await queue.enqueue(lambda ctx: job(ctx, 99))
        await queue.join()
        await queue.stop()

        results = [future.result() for future in futures]
        with pytest.raises(asyncio.QueueFull):
            rejected.result()

        assert sorted(results) == [0, 2]
        assert metrics.snapshot()["queue_rejections"] == 1
        assert metrics.snapshot()["completed"] == 2

    asyncio.run(scenario())


def test_job_respects_duration_limit():
    async def scenario():
        metrics = WorkQueueMetrics()
        queue = WorkQueue(concurrency=1, metrics=metrics)
        await queue.start()

        async def slow_job(ctx):
            await ctx.sleep(0.2)
            return "done"

        future = await queue.enqueue(slow_job, duration_limit=0.05)
        await queue.join()
        await queue.stop()

        with pytest.raises(asyncio.TimeoutError):
            future.result()
        assert metrics.snapshot()["timed_out"] == 1

    asyncio.run(scenario())


def test_missing_heartbeat_cancels_job():
    async def scenario():
        metrics = WorkQueueMetrics()
        queue = WorkQueue(concurrency=1, metrics=metrics)
        await queue.start()

        async def lazy_job(ctx):
            await asyncio.sleep(0.2)
            return "never"

        future = await queue.enqueue(lazy_job, heartbeat_interval=0.05)
        await queue.join()
        await queue.stop()

        with pytest.raises(HeartbeatMissed):
            future.result()
        assert metrics.snapshot()["heartbeat_missed"] == 1

    asyncio.run(scenario())


def test_sensor_policy_throttles_until_safe_then_runs():
    async def scenario():
        metrics = WorkQueueMetrics()

        readings = [
            SensorSnapshot(temperature_c=90),
            SensorSnapshot(temperature_c=85),
            SensorSnapshot(temperature_c=65),
        ]
        read_iter = iter(readings)

        async def reader():
            await asyncio.sleep(0)
            try:
                return next(read_iter)
            except StopIteration:
                return SensorSnapshot(temperature_c=65)

        policy = SensorPolicy(
            reader,
            max_temperature_c=70,
            cooldown_seconds=0.05,
            metrics=metrics,
        )
        queue = WorkQueue(concurrency=1, sensor_policy=policy, metrics=metrics)
        await queue.start()

        async def job(ctx):
            ctx.ping()
            await ctx.sleep(0.01)
            return "ok"

        start = time.perf_counter()
        future = await queue.enqueue(job)
        await queue.join()
        await queue.stop()
        elapsed = time.perf_counter() - start

        assert future.result() == "ok"
        assert metrics.snapshot()["sensor_throttles"] >= 1
        assert elapsed >= 0.1

    asyncio.run(scenario())


def test_sensor_policy_can_abort_when_requested():
    async def scenario():
        metrics = WorkQueueMetrics()
        policy = SensorPolicy(
            lambda: SensorSnapshot(temperature_c=100),
            max_temperature_c=80,
            stop_on_violation=True,
            metrics=metrics,
        )
        queue = WorkQueue(concurrency=1, sensor_policy=policy, metrics=metrics)
        await queue.start()

        async def job(ctx):
            return "should not run"

        future = await queue.enqueue(job)
        await queue.join()
        await queue.stop()

        with pytest.raises(SensorLimitExceeded):
            future.result()
        assert metrics.snapshot()["sensor_aborts"] == 1
        assert metrics.snapshot()["completed"] == 0

    asyncio.run(scenario())
