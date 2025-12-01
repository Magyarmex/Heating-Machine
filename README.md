# Heating Machine

Heating Machine is a client-side web application that intentionally drives configurable computational workloads so you can turn your device into a controllable heat source. It runs entirely in the browser (suitable for GitHub Pages hosting) and emphasizes visibility, safety, and instant shutdown controls.

## Features

- **CPU stressors** using Web Workers with adjustable thread count and intensity.
- **Memory pressure** via configurable allocations and active scrubbing to keep data pages hot.
- **GPU activity** through lightweight WebGL draw calls with tunable frame effort.
- **Telemetry dashboard** showing aggregate iterations per second, active threads, memory allocated, GPU activity, elapsed time, and countdown to auto-stop.
- **Live charting** of workload throughput for at-a-glance monitoring.
- **Presets** for quick starts: Light Warmth, Medium Stress, and Maximum Stress Test.
- **Safety rails** including prominent warnings, start/pause/stop controls, auto-stop timers, heartbeat-based stall detection, and error messaging for unsupported APIs.

## Getting Started

1. Open `index.html` directly in a modern browser or host the repository with GitHub Pages.
2. Read the safety warnings. Ensure your device has adequate ventilation and power.
3. Choose a preset or manually adjust sliders for CPU workers, CPU intensity, memory load, GPU load, and auto-stop duration.
4. Click **Start** to begin generating load. Use **Pause** to temporarily halt or **Stop** to end immediately.
5. Watch telemetry and the live chart to verify intensity and device responsiveness.

## Safety Guidance

- This tool **intentionally** increases power draw, heat output, and fan usage. Monitor your device and stop if you observe instability.
- Auto-stop is enabled by default; adjust the duration responsibly.
- Heartbeat monitoring halts the workload if workers stop responding for several seconds.
- GPU load is disabled automatically if WebGL initialization fails.
- Memory allocation is best-effort and may be reduced by the browser or operating system for safety.

## Limitations

- Browser-based telemetry cannot access hardware temperatures; the displayed values are workload estimates and counters only.
- Performance depends on device capabilities and browser API support. Some environments may block workers or WebGL.
- Running in background tabs may throttle timers, reducing the effective load.

## Development Notes

- All logic lives in static assets (`index.html`, `style.css`, `script.js`, and `worker.js`).
- No build step is required; open the HTML file directly.
- The `npm test` script is a placeholder to satisfy automated checks. You can extend it with linters or other tooling as needed.

## Disclaimer

Use at your own risk. The authors are not responsible for damage, data loss, or discomfort arising from misuse. Always maintain supervision while the workload is running and avoid obstructing device cooling.
