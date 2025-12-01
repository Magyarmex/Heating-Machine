import json
import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlparse

from .load_engine import LoadEngine
from .logging_utils import configure_logging, recent_logs


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
        if parsed.path == "/":
            self._serve_dashboard()
        elif parsed.path == "/health":
            _write_json(self, self.engine.health())
        elif parsed.path == "/ready":
            readiness = self.engine.ready()
            status = HTTPStatus.OK if readiness["status"] == "ready" else HTTPStatus.SERVICE_UNAVAILABLE
            _write_json(self, readiness, status=status)
        elif parsed.path == "/metrics":
            _write_json(self, self.engine.health()["metrics"])
        elif parsed.path == "/dashboard-data":
            payload = self._build_dashboard_payload()
            _write_json(self, payload)
        else:
            _write_json(self, {"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def _serve_dashboard(self) -> None:
        dashboard_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
        try:
            with open(dashboard_path, "rb") as fp:
                content = fp.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            _write_json(
                self,
                {"error": "dashboard_missing", "message": "Dashboard asset was not found."},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _build_dashboard_payload(self) -> dict:
        health = self.engine.health()
        diagnostics = self.engine.diagnostics()
        instructions = [
            "Apply presets with caution; confirm safety windows before boosting.",
            "Watch queue pressure and throttling counters during intensive runs.",
            "Use the kill switch if guardrails trigger repeatedly or load exceeds policy.",
            "Enable debug mode to capture richer telemetry before making changes.",
            "Review cooldown advice before scheduling back-to-back sessions.",
        ]
        logs = recent_logs()
        return {
            "health": health,
            "ready": self.engine.ready(),
            "diagnostics": diagnostics,
            "instructions": instructions,
            "logs": logs,
        }

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
