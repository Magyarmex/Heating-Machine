# Heating Machine

This tool simulates a heat-inducing workload with guardrails that make it safe to experiment in different environments.

## Features
- **Environment-specific presets**: Configured in `configs/environments.json` with minimal load defaults for development, staging, and production.
- **Canary releases with health gates**: Heat levels rise progressively only when health thresholds stay under control.
- **One-click rollback**: Roll back to the last stable heat level immediately whenever validation or health checks fail.
- **Validation before higher heat**: Pre-flight checks confirm monitoring, capacity, and release hygiene before increasing load.
- **Debug metrics**: Every decision is logged for future debugging and auditing.

## Quick start
1. Install dependencies (PyYAML-free for offline-friendly usage):
   ```bash
   pip install -r requirements.txt
   ```
2. Run a simulated rollout:
   ```bash
   python -m heating_machine.cli development --monitoring --available-capacity 40 \
     --simulate-error-rate 0.01 0.02 0.02 --simulate-cpu-spike 0.1 0.2 0.25
   ```

The CLI prints validation outcomes, health gate decisions, and whether a rollback was needed.
