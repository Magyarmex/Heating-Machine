# Heating Machine Browser UI Design

## Overview
Concept for a browser UI that controls heating loads with guardrails. It prioritizes quick presets, schedulable sessions, and an unmistakable emergency kill switch.

## Primary Navigation
- **Dashboard:** heat level presets, live status, timers.
- **Schedule:** plan timeboxed sessions and recurring windows.
- **Safety Center:** kill switch, confirmations, alerts, and safety logs.
- **Settings:** debug flags, telemetry opt-ins, thresholds for alarms, and maintenance mode.

## Wireframes (Lo-Fi)

### Dashboard
```
+----------------------------------------------------+
| Logo | System Status: Stable | Kill Switch (red)   |
+----------------------------------------------------+
| Presets:  [ Eco ] [ Comfort ] [ Boost ] [ Custom ] |
|                                                ⓘ   |
| Live Temp/Load Gauge      Session Timer           |
|  (dial/thermo)            [ 00:25 remaining ]     |
|                                                    |
| Quick Actions: [Pause] [Extend 10m] [Reduce]      |
+----------------------------------------------------+
| Activity feed (events, warnings, metrics)          |
+----------------------------------------------------+
```

### Schedule
```
+----------------------------------------------+
| Back | Schedule                 | Kill Switch |
+----------------------------------------------+
| New Timebox:                                   |
|  - Preset dropdown (Eco/Comfort/Boost/Custom)  |
|  - Start time | Duration | Recurrence toggle   |
|  - Safety window (max temp/load)               |
|  - Save (requires confirmation if exceeding)   |
|                                                |
| Upcoming sessions list with status chips:      |
|  - Planned / Running / Completed / Blocked     |
+------------------------------------------------+
```

### Safety Center
```
+----------------------------------------------+
| Safety Center                     | Kill Now |
+----------------------------------------------+
| Kill Switch: [Big Red Button] (hold 2s)       |
| Confirmation modal: "Stop all heat?"          |
|                                               |
| Safety Flags & Alerts:                        |
|  - Over-temp threshold reached                |
|  - Long-running session with no user check-in |
|  - Network/connectivity degraded              |
|                                               |
| Log & Metrics: recent triggers, error codes,  |
| context links to debug report.                |
+----------------------------------------------+
```

### Confirmation & Prompts
- **Risky preset or schedule**: modal summarizing preset, duration, estimated peak load, and safety bounds; requires typed confirm (e.g., "STOP" or "BOOST") when exceeding recommended limits.
- **Kill switch**: double-step with hold-to-activate, then post-kill confirmation showing state reset and cooldown timer.
- **Extending session**: shows cumulative runtime and asks for re-acknowledgment of safety bounds.

## User Flows

### Start a Heat Session from Dashboard
1. Click preset (Eco/Comfort/Boost/Custom).
2. Confirmation sheet shows load, timebox default, and safety limit; user confirms.
3. Session begins; timer and gauge animate; activity feed logs start with debug metrics (CPU load, temp sensor readings, fan RPM snapshot).
4. User can pause, reduce, or extend; each action logs an event with before/after state.

### Schedule a Future Session
1. Open **Schedule** > **New Timebox**.
2. Choose preset, start time, duration, recurrence.
3. Set safety window (max temp/load) and fail-safe (auto-kill on threshold breach).
4. Save triggers confirmation if duration or load exceeds policy; else schedules directly.
5. Session transitions through **Planned → Running → Completed**; if blocked by safety limits, move to **Blocked** with reason.

### Use Kill Switch
1. From any page, hit **Kill Switch**.
2. Hold-to-confirm (2 seconds) → modal "Stop all heat?" with summary of currently running sessions.
3. On confirm, all sessions terminate; system enters cooldown. Activity feed logs kill event with sensor snapshot and reason.
4. Post-kill banner offers restart after cooldown and links to safety report.

## Success & Failure States
- **Success states**
  - Preset applied; session timer starts; metrics update (load %, temp °C, fan RPM, power draw if available).
  - Schedule saved; appears in upcoming list with **Planned** status and next start time.
  - Kill switch executed; all sessions halted; system in **Cooldown** with timer.
- **Failure/edge states**
  - Over-threshold temperature or load: session auto-pauses; **Blocked** status with reason and restart button gated by confirmation.
  - Network/control-plane loss: UI shows **Degraded** badge; disables new boosts; kill switch remains local-first.
  - Conflicting schedules: prompt to resolve; keep latest, merge, or cancel; blocked slots shown in red.
  - Sensor mismatch/invalid data: flag in activity feed with error code; fall back to conservative preset.

## Confirmation & Safety Patterns
- Use red accents and uppercase copy for kill-related prompts.
- Require typed confirmation for actions exceeding policy (high temp/load, long duration > 2h).
- Provide undo window (5–10 seconds) for non-kill actions; kill is immediate and irreversible.
- Toasts for success; banners for warnings/errors; modal for destructive actions.

## Debug Metrics, Error Handling, and Flags
- **Metrics surface:** show live CPU/GPU load, temperature, fan RPM, power draw, throttle state, and last-safety-trigger timestamp. Log before/after snapshots on every action (start, pause, extend, kill).
- **Debug toggles:** verbose telemetry mode, mock-sensor mode for testing, safety-threshold preview overlay.
- **Error handling:** standardized error codes (e.g., NET-01 for connectivity loss, TMP-02 for sensor fault) displayed in alerts and stored with timestamps.
- **Flagging:** automatically flag sessions that exceed recommended duty cycle; mark schedules as **At Risk** when approaching limits; include quick link to export debug bundle (events + metrics).

## Open Questions / Next Steps
- Sensor sources and precision requirements.
- Policy for consecutive boosts and minimum cooldown durations.
- Accessibility of hold-to-kill interaction (keyboard and screen readers).
