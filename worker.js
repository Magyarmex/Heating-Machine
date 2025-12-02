let running = false;
let paused = false;
let intensity = 0.5;

function busyMath(iterationsTarget) {
  let iterations = 0;
  while (iterations < iterationsTarget) {
    // Simple floating point math to keep the ALUs busy.
    // Avoid try/catch around imports per code style guidance.
    const a = Math.sin(iterations) * Math.cos(iterations * 0.5);
    const b = Math.sqrt(Math.abs(a)) * Math.atan2(a, iterations + 1);
    Math.log1p(b + a);
    iterations++;
  }
  return iterations;
}

function cycle() {
  if (!running || paused) return;

  const cycleStart = performance.now();
  const computeWindow = 150 * intensity; // ms of busy time per cycle proportional to intensity
  const targetIterations = Math.max(1, Math.floor(computeWindow * 500));
  const iterations = busyMath(targetIterations);
  const elapsed = performance.now() - cycleStart;

  self.postMessage({ type: 'stats', iterations, elapsed });

  const cycleDuration = 200;
  const delay = Math.max(0, cycleDuration - elapsed);
  setTimeout(cycle, delay);
}

self.onmessage = (event) => {
  const { type, payload } = event.data;
  if (type === 'start') {
    intensity = payload.intensity;
    running = true;
    paused = false;
    cycle();
  } else if (type === 'update') {
    intensity = payload.intensity;
  } else if (type === 'pause') {
    paused = true;
  } else if (type === 'resume') {
    if (running) {
      paused = false;
      cycle();
    }
  } else if (type === 'stop') {
    running = false;
    paused = false;
    close();
  }
};
