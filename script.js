const el = (id) => document.getElementById(id);
const formatMb = (bytes) => (bytes / (1024 * 1024)).toFixed(0);

const controls = {
  cpuCount: el('cpu-count'),
  cpuIntensity: el('cpu-intensity'),
  memory: el('memory'),
  gpu: el('gpu'),
  duration: el('duration'),
};

const labels = {
  cpuCount: el('cpu-count-label'),
  cpuIntensity: el('cpu-intensity-label'),
  memory: el('memory-label'),
  gpu: el('gpu-label'),
  duration: el('duration-label'),
};

const outputs = {
  status: el('status'),
  threads: el('threads'),
  ips: el('ips'),
  cpuBusy: el('cpu-busy'),
  memory: el('memory-usage'),
  memoryTouch: el('memory-touch'),
  gpu: el('gpu-activity'),
  gpuFps: el('gpu-fps'),
  elapsed: el('elapsed'),
  countdown: el('countdown'),
  warnings: el('warnings'),
  flags: el('flags'),
};

const presetInfo = {
  light: 'Light Warmth: low CPU threads, minimal memory, and small GPU blips.',
  medium: 'Medium Stress: multi-threaded CPU with moderate intensity and memory pressure.',
  max: 'Maximum Stress Test: saturates CPU threads, heavy memory activity, and aggressive GPU draws.',
};

const presets = {
  light: { cpu: 2, intensity: 25, memory: 256, gpu: 10, duration: 10 },
  medium: { cpu: Math.max(2, Math.min(4, navigator.hardwareConcurrency || 4)), intensity: 55, memory: 768, gpu: 35, duration: 15 },
  max: { cpu: Math.max(4, navigator.hardwareConcurrency || 8), intensity: 95, memory: 1536, gpu: 70, duration: 20 },
};

const state = {
  running: false,
  paused: false,
  workers: [],
  workerStats: [],
  memoryBuffers: [],
  memoryTouchTimer: null,
  memoryTouchRate: 0,
  gpuContext: null,
  gpuLoop: null,
  gpuIntensity: 0,
  gpuFps: 0,
  lastGpuTimestamp: null,
  gpuFrameCounter: 0,
  startTime: null,
  autoStopTimer: null,
  lastHeartbeat: performance.now(),
  chartData: [],
  flags: new Set(),
  targetWorkers: 0,
  lowThroughputCount: 0,
};

function initLabels() {
  labels.cpuCount.textContent = controls.cpuCount.value;
  labels.cpuIntensity.textContent = `${controls.cpuIntensity.value}%`;
  labels.memory.textContent = `${controls.memory.value} MB`;
  labels.gpu.textContent = `${controls.gpu.value}%`;
  labels.duration.textContent = `${controls.duration.value} min`;
}

function setStatus(message) {
  outputs.status.textContent = message;
}

function setWarning(message) {
  outputs.warnings.textContent = message || 'None';
}

function renderFlags() {
  const flagList = el('flag-list');
  flagList.innerHTML = '';
  if (!state.flags.size) {
    flagList.innerHTML = '<li>No issues detected.</li>';
    outputs.flags.textContent = 'None';
    return;
  }
  outputs.flags.textContent = `${state.flags.size} issue${state.flags.size === 1 ? '' : 's'}`;
  [...state.flags].forEach((flag) => {
    const li = document.createElement('li');
    li.textContent = flag;
    flagList.appendChild(li);
  });
}

function addFlag(message) {
  if (!state.flags.has(message)) {
    state.flags.add(message);
    renderFlags();
  }
}

function clearFlags() {
  state.flags.clear();
  renderFlags();
}

function updateTelemetry() {
  const now = performance.now();
  const elapsedSeconds = state.startTime ? ((now - state.startTime) / 1000).toFixed(1) : '0';
  outputs.elapsed.textContent = `${elapsedSeconds}s`;
  outputs.threads.textContent = state.workers.length;

  const ips = state.workerStats.reduce((acc, s) => acc + (s.iterationsPerSecond || 0), 0);
  outputs.ips.textContent = ips.toFixed(0);

  const avgBusy = state.workerStats.length
    ? state.workerStats.reduce((acc, s) => acc + (s.busy || 0), 0) / state.workerStats.length
    : 0;
  const cores = navigator.hardwareConcurrency || Math.max(1, state.workers.length);
  const effectiveBusy = Math.min(1, avgBusy * (state.workers.length / cores));
  outputs.cpuBusy.textContent = `${(effectiveBusy * 100).toFixed(0)}%`;

  const memMb = state.memoryBuffers.reduce((acc, buf) => acc + buf.byteLength, 0);
  outputs.memory.textContent = `${formatMb(memMb)} MB`;
  outputs.memoryTouch.textContent = `${state.memoryTouchRate.toFixed(0)}x/sec`;

  outputs.gpu.textContent = state.gpuIntensity > 0 ? `Active (${state.gpuIntensity}% effort)` : 'Idle';
  outputs.gpuFps.textContent = `${state.gpuFps.toFixed(0)} fps`;
}

function attachSliderLabel(slider, label, suffix = '') {
  slider.addEventListener('input', () => {
    label.textContent = `${slider.value}${suffix}`;
    if (state.running && slider === controls.cpuIntensity) {
      state.workers.forEach((worker) => worker.postMessage({ type: 'update', payload: { intensity: slider.value / 100 } }));
    }
    if (state.running && slider === controls.gpu) {
      state.gpuIntensity = Number(slider.value);
    }
  });
}

class LoadChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.points = Array(120).fill(0);
  }

  push(value) {
    this.points.push(value);
    if (this.points.length > 120) this.points.shift();
    this.draw();
  }

  draw() {
    const { ctx, canvas, points } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#0b1221';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const maxValue = Math.max(1, ...points);
    ctx.strokeStyle = '#1f2937';
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i++) {
      const y = (canvas.height / 4) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.stroke();
    }

    ctx.strokeStyle = '#f97316';
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((p, idx) => {
      const x = (idx / (points.length - 1)) * canvas.width;
      const y = canvas.height - (p / maxValue) * canvas.height;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    ctx.fillStyle = '#e5e7eb';
    ctx.font = '12px Inter, sans-serif';
    ctx.fillText(`Iterations/s (aggregate) — peak ${maxValue.toFixed(0)}`, 10, 20);
  }
}

const chart = new LoadChart(document.getElementById('chart'));

function createWorker() {
  try {
    const worker = new Worker('worker.js');
    worker.onmessage = (event) => {
      if (event.data.type === 'stats') {
        const { iterations, elapsed } = event.data;
        const iterationsPerSecond = (iterations / Math.max(1, elapsed)) * 1000;
        const busy = Math.min(1, elapsed / 200);
        state.lastHeartbeat = performance.now();
        state.workerStats.push({ iterationsPerSecond, busy });
      }
    };
    worker.onerror = (err) => {
      setWarning(`Worker error: ${err.message}`);
      stopWorkload();
    };
    return worker;
  } catch (error) {
    setWarning(`Unable to create worker: ${error.message}`);
    setStatus('Unsupported');
    return null;
  }
}

function startWorkers(count, intensity) {
  cleanupWorkers();
  state.workerStats = [];
  state.targetWorkers = count;
  for (let i = 0; i < count; i++) {
    const worker = createWorker();
    if (worker) {
      worker.postMessage({ type: 'start', payload: { intensity } });
      state.workers.push(worker);
    }
  }
  outputs.threads.textContent = state.workers.length;
}

function cleanupWorkers() {
  state.workers.forEach((worker) => worker.postMessage({ type: 'stop' }));
  state.workers = [];
}

function allocateMemory(megabytes) {
  state.memoryBuffers.forEach((buf) => buf.fill(0));
  state.memoryBuffers = [];
  clearInterval(state.memoryTouchTimer);
  state.memoryTouchRate = 0;

  if (megabytes <= 0) {
    outputs.memory.textContent = '0 MB';
    return;
  }

  const bytes = megabytes * 1024 * 1024;
  const chunk = 16 * 1024 * 1024;
  let allocated = 0;
  let touches = 0;
  const intervalMs = 750;

  try {
    while (allocated < bytes) {
      const size = Math.min(chunk, bytes - allocated);
      const buffer = new Float64Array(size / 8);
      state.memoryBuffers.push(buffer);
      allocated += size;
    }
  } catch (error) {
    setWarning(`Memory allocation limited: ${error.message}`);
    addFlag('Memory load reduced by browser/OS limits.');
  }

  state.memoryTouchTimer = setInterval(() => {
    touches = 0;
    state.memoryBuffers.forEach((buf, index) => {
      const step = Math.max(1, Math.floor(buf.length / 64));
      for (let i = 0; i < buf.length; i += step) {
        buf[i] = (buf[i] + Math.random()) % 1;
        touches++;
      }
      if (index % 4 === 0) buf.reverse();
    });
    state.memoryTouchRate = touches / (intervalMs / 1000);
  }, intervalMs);
}

function setupGPU(intensity) {
  if (state.gpuContext?.isContextLost?.()) return;

  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 256;
  canvas.style.display = 'none';
  document.body.appendChild(canvas);

  const gl = canvas.getContext('webgl');
  if (!gl) {
    setWarning('WebGL not available; GPU mode disabled.');
    return null;
  }

  const vertexSrc = `
    attribute vec2 position;
    void main() { gl_Position = vec4(position, 0.0, 1.0); }
  `;
  const fragmentSrc = `
    precision mediump float;
    void main() {
      vec2 uv = gl_FragCoord.xy / 256.0;
      float heat = sin(uv.x * 20.0) * cos(uv.y * 20.0);
      gl_FragColor = vec4(vec3(abs(heat)), 1.0);
    }
  `;

  const program = gl.createProgram();
  const vs = gl.createShader(gl.VERTEX_SHADER);
  const fs = gl.createShader(gl.FRAGMENT_SHADER);
  gl.shaderSource(vs, vertexSrc);
  gl.shaderSource(fs, fragmentSrc);
  gl.compileShader(vs);
  gl.compileShader(fs);
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    setWarning('GPU shader compilation failed; disabling GPU load.');
    return null;
  }

  const vertices = new Float32Array([
    -1, -1,
     1, -1,
    -1,  1,
    -1,  1,
     1, -1,
     1,  1,
  ]);

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

  const positionLocation = gl.getAttribLocation(program, 'position');
  gl.enableVertexAttribArray(positionLocation);
  gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);

  state.gpuContext = { gl, program, canvas };
  state.gpuIntensity = intensity;
  return state.gpuContext;
}

function stopGPU() {
  if (state.gpuLoop) cancelAnimationFrame(state.gpuLoop);
  state.gpuLoop = null;
  if (state.gpuContext?.canvas) state.gpuContext.canvas.remove();
  state.gpuContext = null;
  state.gpuFps = 0;
  state.lastGpuTimestamp = null;
  state.gpuFrameCounter = 0;
  outputs.gpu.textContent = 'Idle';
}

function gpuTick() {
  if (!state.running || state.paused || !state.gpuContext) return;
  const { gl, program } = state.gpuContext;
  gl.viewport(0, 0, 256, 256);
  gl.useProgram(program);

  const now = performance.now();
  if (state.lastGpuTimestamp) {
    const delta = now - state.lastGpuTimestamp;
    state.gpuFps = 1000 / Math.max(1, delta);
  }
  state.lastGpuTimestamp = now;
  state.gpuFrameCounter++;

  const draws = Math.max(1, Math.round(state.gpuIntensity / 10));
  for (let i = 0; i < draws; i++) {
    gl.uniform1f(gl.getUniformLocation(program, 'uTime'), performance.now());
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }

  state.gpuLoop = requestAnimationFrame(gpuTick);
}

function startGPU(intensity) {
  stopGPU();
  if (intensity <= 0) return;
  const ctx = setupGPU(intensity);
  if (!ctx) {
    addFlag('GPU load disabled (WebGL unavailable).');
    return;
  }
  gpuTick();
}

function startAutoStop(minutes) {
  clearInterval(state.autoStopTimer);
  const ms = minutes * 60 * 1000;
  const end = performance.now() + ms;
  state.autoStopTimer = setInterval(() => {
    const remaining = Math.max(0, end - performance.now());
    outputs.countdown.textContent = `${(remaining / 1000).toFixed(0)}s`;
    if (remaining <= 0) {
      setWarning('Auto-stop reached. Workload ended.');
      stopWorkload();
    }
  }, 500);
}

function startWorkload() {
  if (!window.Worker) {
    setWarning('Web Workers not supported; CPU load unavailable.');
    addFlag('Not applying load correctly (workers unsupported).');
    return;
  }

  state.running = true;
  state.paused = false;
  state.startTime = performance.now();
  state.workerStats = [];
  state.chartData = [];
  state.lowThroughputCount = 0;
  clearFlags();
  setWarning('None');
  setStatus('Running');

  const cpuThreads = Math.min(Number(controls.cpuCount.value), navigator.hardwareConcurrency || 16);
  const cpuIntensity = Number(controls.cpuIntensity.value) / 100;
  const memoryMb = Number(controls.memory.value);
  const gpuIntensity = Number(controls.gpu.value);
  const durationMinutes = Number(controls.duration.value);

  startWorkers(cpuThreads, cpuIntensity);
  allocateMemory(memoryMb);
  startGPU(gpuIntensity);
  startAutoStop(durationMinutes);
  scheduleHealthCheck();

  outputs.countdown.textContent = `${durationMinutes * 60}s`;
  el('start').disabled = true;
  el('pause').disabled = false;
  el('stop').disabled = false;
}

function pauseWorkload() {
  state.paused = true;
  setStatus('Paused');
  state.workers.forEach((worker) => worker.postMessage({ type: 'pause' }));
  stopGPU();
  clearInterval(state.memoryTouchTimer);
}

function resumeWorkload() {
  state.paused = false;
  setStatus('Running');
  state.workers.forEach((worker) => worker.postMessage({ type: 'resume' }));
  allocateMemory(Number(controls.memory.value));
  startGPU(Number(controls.gpu.value));
}

function stopWorkload() {
  state.running = false;
  state.paused = false;
  cleanupWorkers();
  stopGPU();
  clearInterval(state.memoryTouchTimer);
  clearInterval(state.autoStopTimer);
  state.memoryTouchRate = 0;
  setStatus('Idle');
  outputs.countdown.textContent = '-';
  outputs.gpu.textContent = 'Idle';
  el('start').disabled = false;
  el('pause').disabled = true;
  el('stop').disabled = true;
}

function scheduleHealthCheck() {
  const watchdog = setInterval(() => {
    if (!state.running) {
      clearInterval(watchdog);
      return;
    }
    const delta = performance.now() - state.lastHeartbeat;
    if (delta > 4000) {
      setWarning('Heartbeat stalled. Load stopped for safety.');
      addFlag('Not applying load correctly (workers stalled).');
      stopWorkload();
      clearInterval(watchdog);
    }
  }, 2000);
}

function applyPreset(key) {
  const preset = presets[key];
  if (!preset) return;
  controls.cpuCount.value = preset.cpu;
  controls.cpuIntensity.value = preset.intensity;
  controls.memory.value = preset.memory;
  controls.gpu.value = preset.gpu;
  controls.duration.value = preset.duration;
  initLabels();
  el('preset-info').textContent = presetInfo[key];
}

function updateChart() {
  if (!state.running) return;
  const ips = state.workerStats.reduce((acc, s) => acc + (s.iterationsPerSecond || 0), 0);
  chart.push(ips);
  state.workerStats = [];
  updateTelemetry();

  if (state.running) {
    if (state.workers.length < state.targetWorkers) {
      addFlag('CPU workers below requested count — browser may cap worker creation.');
    }
    const busyPercent = parseInt(outputs.cpuBusy.textContent, 10) || 0;
    if (busyPercent < 5 && !state.paused && Number(controls.cpuIntensity.value) > 20) {
      state.lowThroughputCount += 1;
      if (state.lowThroughputCount > 3) {
        addFlag('Not applying load correctly (CPU throughput extremely low).');
      }
    } else {
      state.lowThroughputCount = 0;
    }

    if (Number(controls.gpu.value) > 0 && !state.gpuContext) {
      addFlag('GPU load disabled (missing WebGL support).');
    }
  }
}

function bindEvents() {
  attachSliderLabel(controls.cpuCount, labels.cpuCount);
  attachSliderLabel(controls.cpuIntensity, labels.cpuIntensity, '%');
  attachSliderLabel(controls.memory, labels.memory, ' MB');
  attachSliderLabel(controls.gpu, labels.gpu, '%');
  attachSliderLabel(controls.duration, labels.duration, ' min');

  document.querySelectorAll('[data-preset]').forEach((btn) => {
    btn.addEventListener('click', () => applyPreset(btn.dataset.preset));
  });

  el('start').addEventListener('click', () => {
    try {
      startWorkload();
    } catch (error) {
      setWarning(`Failed to start workload: ${error.message}`);
      stopWorkload();
    }
  });

  el('pause').addEventListener('click', () => {
    if (!state.running) return;
    if (!state.paused) {
      pauseWorkload();
      el('pause').textContent = 'Resume';
    } else {
      resumeWorkload();
      el('pause').textContent = 'Pause';
    }
  });

  el('stop').addEventListener('click', () => {
    stopWorkload();
    el('pause').textContent = 'Pause';
  });

  window.addEventListener('beforeunload', stopWorkload);
}

function init() {
  const cores = navigator.hardwareConcurrency || 4;
  controls.cpuCount.max = Math.max(cores, 4);
  controls.cpuCount.value = Math.min(cores, 8);
  controls.cpuIntensity.value = 40;
  controls.memory.value = 512;
  controls.gpu.value = 20;
  controls.duration.value = 10;
  initLabels();
  bindEvents();
  setStatus('Idle');
  setWarning('None');
  renderFlags();
  setInterval(updateChart, 500);
}

init();
