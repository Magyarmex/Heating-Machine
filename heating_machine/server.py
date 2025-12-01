import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlparse

from .load_engine import LoadEngine
from .logging_utils import configure_logging


def _write_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class EngineRequestHandler(BaseHTTPRequestHandler):
    server_version = "HeatingMachine/1.0"
    engine: LoadEngine

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            _write_json(self, self.engine.health())
        elif parsed.path == "/ready":
            readiness = self.engine.ready()
            status = HTTPStatus.OK if readiness["status"] == "ready" else HTTPStatus.SERVICE_UNAVAILABLE
            _write_json(self, readiness, status=status)
        elif parsed.path == "/metrics":
            _write_json(self, self.engine.health()["metrics"])
        else:
            _write_json(self, {"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        logger = logging.getLogger("heating_machine.http")
        logger.info(
            "http_request",
            extra={"extra_data": {"event": "http_request", "message": format % args}},
        )


def serve(engine: Optional[LoadEngine] = None, host: str = "0.0.0.0", port: int = 8080) -> None:
    configure_logging()
    engine = engine or LoadEngine()
    engine.start()
    engine.start_session()
    EngineRequestHandler.engine = engine
    with ThreadingHTTPServer((host, port), EngineRequestHandler) as httpd:
        engine.logger.info(
            "http_server_started",
            extra={"extra_data": {"event": "server_start", "host": host, "port": port}},
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            engine.stop()
            engine.logger.info("http_server_stopped", extra={"extra_data": {"event": "server_stop"}})


if __name__ == "__main__":
    serve()
