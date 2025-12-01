# Heating Machine

A simple, in-memory controller for starting or stopping a high-load "heating" routine. The project now includes authenticated session management, role-based permissions, and persistent audit logging for every sensitive action.

## Features

- **Session management**: Login creates session tokens that can later be revoked. Sessions are required for all actions.
- **Role-based access control**: Three roles are supported:
  - `viewer`: read-only; cannot start/stop or change configuration.
  - `operator`: can start or stop the heater but cannot change configuration.
  - `admin`: full access, including configuration updates.
- **Audit logging**: Every session start/end, heater start/stop, and configuration change is written to a line-delimited JSON audit log with the user, action, timestamp, parameters, and outcome.
- **Debug metrics**: Counters track start/stop/config attempts, permission denials, and session lifecycle events to aid troubleshooting.

## Quick start

1. Create the components:

```python
from heating_machine import AuditLogger, HeatingMachine, Role, SessionManager

audit = AuditLogger("audit.log")
sessions = SessionManager(audit)
machine = HeatingMachine(sessions, audit)
```

2. Login and act according to role:

```python
operator_token = sessions.login("alice", Role.OPERATOR)
admin_token = sessions.login("bob", Role.ADMIN)

machine.start(operator_token)
machine.update_config(admin_token, target_load=0.9)
machine.stop(operator_token)
```

3. Check status and metrics:

```python
machine.status()
```

4. Inspect audit logs (JSON lines):

```python
print(audit.read_all())
```

Run tests with `pytest` to validate permissions and logging.
