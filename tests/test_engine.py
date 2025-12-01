import json
import threading
import urllib.request
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from heating_machine.load_engine import EngineJob, LoadEngine  # noqa: E402
from heating_machine.server import EngineRequestHandler, ThreadingHTTPServer  # noqa: E402


def test_safety_trip_caps_target():
    engine = LoadEngine(max_safe_load=0.5)
    adjusted = engine.set_target_load(0.9)
    assert adjusted == 0.5
    assert engine.metrics.safety_trip_counts["max_safe_load"] == 1


def test_throttling_when_queue_full():
    engine = LoadEngine(queue_limit=1)
    # Fill queue to force throttle
    engine._job_queue.put_nowait(EngineJob(duration=0.1))
    engine._increment_throttling()
    assert engine.metrics.throttling_events == 1


def test_readiness_reflects_guardrails():
    engine = LoadEngine()
    engine._record_safety_trip("max_safe_load", 1.0)
    readiness = engine.ready()
    assert readiness["status"] == "degraded"
    assert readiness["reason"] == "safety_trip"


def test_health_endpoint_serves_metrics():
    engine = LoadEngine()
    engine.start_session(duration=0.1)
    engine.set_target_load(0.2)
    server = ThreadingHTTPServer(("localhost", 0), EngineRequestHandler)
    EngineRequestHandler.engine = engine
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        url = f"http://{server.server_address[0]}:{server.server_address[1]}/health"
        with urllib.request.urlopen(url) as response:  # noqa: S310
            body = response.read().decode()
            payload = json.loads(body)
            assert payload["status"] == "ok"
            assert "metrics" in payload
    finally:
        server.shutdown()
        thread.join()
