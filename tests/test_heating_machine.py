import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from heating_machine import AuditLogger, HeatingMachine, Role, SessionManager


@pytest.fixture()
def setup_machine(tmp_path):
    audit_path = tmp_path / "audit.log"
    logger = AuditLogger(audit_path)
    sessions = SessionManager(logger)
    machine = HeatingMachine(sessions, logger)
    return audit_path, logger, sessions, machine


def read_log(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_login_logout_records_audit(setup_machine):
    audit_path, logger, sessions, _ = setup_machine

    token = sessions.login("alice", Role.OPERATOR)
    sessions.logout(token)

    records = read_log(audit_path)
    assert [r["action"] for r in records] == ["session_start", "session_end"]
    assert records[0]["user"] == "alice"
    assert records[1]["outcome"] == "ended"


def test_operator_can_start_and_stop(setup_machine):
    audit_path, _, sessions, machine = setup_machine
    token = sessions.login("operator", Role.OPERATOR)

    assert machine.start(token) == "started"
    assert machine.stop(token) == "stopped"

    actions = [entry["action"] for entry in read_log(audit_path)]
    assert actions == ["session_start", "heat_start", "heat_stop"]


def test_viewer_cannot_start(setup_machine):
    audit_path, _, sessions, machine = setup_machine
    token = sessions.login("viewer", Role.VIEWER)

    with pytest.raises(PermissionError):
        machine.start(token)

    outcomes = [entry["outcome"] for entry in read_log(audit_path)]
    assert outcomes[-1] == "permission_denied"
    assert machine.metrics["permission_denied"] == 1


def test_admin_can_change_config_and_logs_parameters(setup_machine):
    audit_path, _, sessions, machine = setup_machine
    token = sessions.login("admin", Role.ADMIN)

    updated = machine.update_config(token, target_load=0.9, cooldown=5)

    assert updated["target_load"] == 0.9
    assert updated["cooldown"] == 5

    last_entry = read_log(audit_path)[-1]
    assert last_entry["action"] == "config_change"
    assert last_entry["parameters"] == {"target_load": 0.9, "cooldown": 5}


def test_metrics_track_attempts(setup_machine):
    _, _, sessions, machine = setup_machine
    admin_token = sessions.login("admin", Role.ADMIN)
    operator_token = sessions.login("operator", Role.OPERATOR)
    viewer_token = sessions.login("viewer", Role.VIEWER)

    machine.start(operator_token)
    with pytest.raises(PermissionError):
        machine.update_config(viewer_token, target_load=0.8)
    machine.update_config(admin_token, target_load=0.95)
    machine.stop(operator_token)

    status = machine.status()
    assert status["metrics"]["start_attempts"] == 1
    assert status["metrics"]["stop_attempts"] == 1
    assert status["metrics"]["config_change_attempts"] == 2
    assert status["metrics"]["permission_denied"] == 1
    assert status["metrics"]["sessions_started"] == 3
