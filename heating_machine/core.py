import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Optional


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass(frozen=True)
class User:
    username: str
    role: Role


class AuditLogger:
    """Persist structured audit events as line-delimited JSON."""

    def __init__(self, path: Path | str = "audit.log") -> None:
        self.path = Path(path)
        self.path.touch(exist_ok=True)

    def log(self, *, user: Optional[User], action: str, parameters: Dict, outcome: str) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": user.username if user else None,
            "role": user.role.value if user else None,
            "action": action,
            "parameters": parameters,
            "outcome": outcome,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def read_all(self) -> list[dict]:
        """Utility helper for tests to read back stored records."""
        with self.path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


class SessionManager:
    """Manage authenticated sessions and enforce role checks."""

    def __init__(self, audit_logger: AuditLogger) -> None:
        self.audit_logger = audit_logger
        self._sessions: Dict[str, User] = {}
        self.metrics: Dict[str, int] = {
            "sessions_started": 0,
            "sessions_ended": 0,
            "invalid_tokens": 0,
        }

    def login(self, username: str, role: Role) -> str:
        token = uuid.uuid4().hex
        user = User(username=username, role=role)
        self._sessions[token] = user
        self.metrics["sessions_started"] += 1
        self.audit_logger.log(user=user, action="session_start", parameters={"token": token}, outcome="started")
        return token

    def logout(self, token: str) -> None:
        user = self._sessions.pop(token, None)
        if user is None:
            self.metrics["invalid_tokens"] += 1
            self.audit_logger.log(user=None, action="session_end", parameters={"token": token}, outcome="unknown_session")
            raise PermissionError("Session token is invalid or expired.")
        self.metrics["sessions_ended"] += 1
        self.audit_logger.log(user=user, action="session_end", parameters={"token": token}, outcome="ended")

    def require_role(self, token: str, allowed_roles: Iterable[Role]) -> User:
        user = self._sessions.get(token)
        if user is None:
            self.metrics["invalid_tokens"] += 1
            self.audit_logger.log(user=None, action="authorization", parameters={"token": token}, outcome="unknown_session")
            raise PermissionError("Session token is invalid or expired.")
        if user.role not in allowed_roles:
            self.audit_logger.log(
                user=user,
                action="authorization",
                parameters={"token": token, "allowed_roles": [r.value for r in allowed_roles]},
                outcome="permission_denied",
            )
            raise PermissionError(f"User '{user.username}' lacks permission for this action.")
        return user


class HeatingMachine:
    """In-memory heating machine controller with permissioned actions."""

    def __init__(self, session_manager: SessionManager, audit_logger: AuditLogger) -> None:
        self.session_manager = session_manager
        self.audit_logger = audit_logger
        self.running: bool = False
        self.config: Dict[str, int | float] = {"target_load": 0.75}
        self.metrics: Dict[str, int] = {
            "start_attempts": 0,
            "stop_attempts": 0,
            "config_change_attempts": 0,
            "permission_denied": 0,
        }

    def start(self, token: str) -> str:
        self.metrics["start_attempts"] += 1
        try:
            user = self.session_manager.require_role(token, {Role.OPERATOR, Role.ADMIN})
        except PermissionError:
            self.metrics["permission_denied"] += 1
            raise

        if self.running:
            outcome = "already_running"
        else:
            self.running = True
            outcome = "started"
        self.audit_logger.log(user=user, action="heat_start", parameters={"running": self.running}, outcome=outcome)
        return outcome

    def stop(self, token: str) -> str:
        self.metrics["stop_attempts"] += 1
        try:
            user = self.session_manager.require_role(token, {Role.OPERATOR, Role.ADMIN})
        except PermissionError:
            self.metrics["permission_denied"] += 1
            raise

        if not self.running:
            outcome = "already_stopped"
        else:
            self.running = False
            outcome = "stopped"
        self.audit_logger.log(user=user, action="heat_stop", parameters={"running": self.running}, outcome=outcome)
        return outcome

    def update_config(self, token: str, **config_updates: int | float) -> Dict[str, int | float]:
        self.metrics["config_change_attempts"] += 1
        try:
            user = self.session_manager.require_role(token, {Role.ADMIN})
        except PermissionError:
            self.metrics["permission_denied"] += 1
            raise

        self.config.update(config_updates)
        self.audit_logger.log(
            user=user,
            action="config_change",
            parameters=config_updates,
            outcome="updated",
        )
        return dict(self.config)

    def status(self) -> Dict[str, object]:
        return {
            "running": self.running,
            "config": dict(self.config),
            "metrics": {
                **self.metrics,
                **self.session_manager.metrics,
            },
        }
