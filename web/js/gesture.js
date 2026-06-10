/**
 * gesture.js — adaptive hand detection, no pre-loaded libraries.
 *
 * Backend selection (decided at camera-activation time):
 *   WebGL 2 available → @mediapipe/tasks-vision  (GPU, ~15 fps, any real device)
 *   No WebGL 2        → TF.js WASM/CPU + hand-pose-detection (~8 fps, works in WSL2)
 *
 * Libraries are loaded on demand — nothing is fetched until the user clicks
 * "Activar cámara", so page load stays fast.
 */

// ── Gesture enums (mirrors gesture/recognizer.py) ─────────────────────────────
export const LocoGesture = Object.freeze({
  UNKNOWN: "UNKNOWN", STOP: "STOP", FORWARD: "FORWARD",
  BACKWARD: "BACKWARD", TURN_LEFT: "TURN_LEFT", TURN_RIGHT: "TURN_RIGHT",
});
export const ArmGesture = Object.freeze({
  UNKNOWN: "UNKNOWN", HOME: "HOME", SHOULDER_UP: "SHOULDER_UP",
  SHOULDER_DOWN: "SHOULDER_DOWN", GRIP_CLOSE: "GRIP_CLOSE", GRIP_OPEN: "GRIP_OPEN",
  EXTEND: "EXTEND", RETRACT: "RETRACT", BASE_LEFT: "BASE_LEFT", BASE_RIGHT: "BASE_RIGHT",
});

const PINCH_THRESHOLD = 0.06;

function fingersUp(lm, handedness) {
  const r = handedness === "Right";
  return [
    r ? lm[4].x < lm[3].x : lm[4].x > lm[3].x,
    lm[8].y  < lm[6].y,
    lm[12].y < lm[10].y,
    lm[16].y < lm[14].y,
    lm[20].y < lm[18].y,
  ];
}
function pinchDist(lm) {
  const dx = lm[4].x - lm[8].x, dy = lm[4].y - lm[8].y;
  return Math.sqrt(dx * dx + dy * dy);
}
export function recognizeLoco(lm, h) {
  const up = fingersUp(lm, h);
  const [, i, m, r, p] = up;
  if (!i && !m && !r && !p) return LocoGesture.STOP;
  if (up.every(Boolean))    return LocoGesture.FORWARD;
  if (i && !m && !r && !p)  return LocoGesture.TURN_LEFT;
  if (i &&  m && !r && !p)  return LocoGesture.TURN_RIGHT;
  if (i &&  m &&  r && !p)  return LocoGesture.BACKWARD;
  return LocoGesture.UNKNOWN;
}
export function recognizeArm(lm, h) {
  const up = fingersUp(lm, h);
  const [, i, m, r, p] = up;
  if (i && m && r && p)                return ArmGesture.GRIP_OPEN;
  if (pinchDist(lm) < PINCH_THRESHOLD)  return ArmGesture.GRIP_CLOSE;
  if (!up.some(Boolean))               return ArmGesture.HOME;
  if (i && !m && !r && !p)             return ArmGesture.SHOULDER_UP;
  if (m && !i && !r && !p)             return ArmGesture.BASE_LEFT;
  if (r && !i && !m && !p)             return ArmGesture.BASE_RIGHT;
  if (p && !i && !m && !r)             return ArmGesture.RETRACT;
  if (i &&  m && !r && !p)             return ArmGesture.SHOULDER_DOWN;
  if (i &&  m &&  r && !p)             return ArmGesture.EXTEND;
  return ArmGesture.UNKNOWN;
}

// ── Hand drawing ──────────────────────────────────────────────────────────────
const CONNECTIONS = [
  [0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20],
];
function drawHand(ctx, lm, isRight, w, h) {
  const pts = lm.map(p => [p.x * w, p.y * h]);
  ctx.strokeStyle = isRight ? "#00ff88" : "#ff9900";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (const [a, b] of CONNECTIONS) {
    ctx.moveTo(pts[a][0], pts[a][1]);
    ctx.lineTo(pts[b][0], pts[b][1]);
  }
  ctx.stroke();
  const fill = isRight ? "#00cc66" : "#cc7700";
  for (const [x, y] of pts) {
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = fill; ctx.strokeStyle = "#fff"; ctx.lineWidth = 1;
    ctx.fill(); ctx.stroke();
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function hasWebGL2() {
  try { return !!document.createElement("canvas").getContext("webgl2"); }
  catch { return false; }
}

function loadScript(src) {
  return new Promise((res, rej) => {
    if (document.querySelector(`script[src="${src}"]`)) return res();
    const s = Object.assign(document.createElement("script"), { src, crossOrigin: "anonymous" });
    s.onload = res; s.onerror = rej;
    document.head.appendChild(s);
  });
}

// ── Backend: GPU via @mediapipe/tasks-vision ──────────────────────────────────
const TV_CDN   = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const TV_MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

async function makeGPUBackend() {
  const { HandLandmarker, FilesetResolver } = await import(TV_CDN);
  const resolver  = await FilesetResolver.forVisionTasks(`${TV_CDN}/wasm`);
  const landmarker = await HandLandmarker.createFromOptions(resolver, {
    baseOptions: { modelAssetPath: TV_MODEL, delegate: "GPU" },
    runningMode: "VIDEO", numHands: 2,
    minHandDetectionConfidence: 0.7,
    minHandPresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });
  return {
    targetMs: 66,  // ~15 fps
    detect(canvas) {
      const r = landmarker.detectForVideo(canvas, performance.now());
      return (r.landmarks ?? []).map((lm, i) => ({
        handedness: r.handednesses[i][0].categoryName,
        landmarks:  lm,  // already normalized 0–1
      }));
    },
    destroy() { landmarker.close(); },
  };
}

// ── Backend: CPU/WASM via TF.js + hand-pose-detection ────────────────────────
const CDN = "https://cdn.jsdelivr.net/npm";

async function makeCPUBackend(PROC_W, PROC_H) {
  await loadScript(`${CDN}/@tensorflow/tfjs@4.20.0/dist/tf.min.js`);
  await loadScript(`${CDN}/@tensorflow/tfjs-backend-wasm@4.20.0/dist/tf-backend-wasm.min.js`);
  await loadScript(`${CDN}/@tensorflow-models/hand-pose-detection@2.0.1/dist/hand-pose-detection.min.js`);

  try { await tf.setBackend("wasm"); }
  catch { await tf.setBackend("cpu"); }
  await tf.ready();
  console.log("TF.js backend:", tf.getBackend());

  const detector = await handPoseDetection.createDetector(
    handPoseDetection.SupportedModels.MediaPipeHands,
    { runtime: "tfjs", modelType: "lite" }
  );
  return {
    targetMs: 120,  // ~8 fps
    async detect(canvas) {
      const hands = await detector.estimateHands(canvas, { flipHorizontal: false });
      return hands.map(h => ({
        handedness: h.handedness,
        landmarks:  h.keypoints.map(kp => ({ x: kp.x / PROC_W, y: kp.y / PROC_H })),
      }));
    },
    destroy() {},
  };
}

// ── Public API ────────────────────────────────────────────────────────────────
export async function startCamera(videoEl, canvasEl, onGesture, onReady) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: 640, height: 480, facingMode: "user" },
  });
  videoEl.srcObject = stream;
  await new Promise(r => videoEl.addEventListener("loadeddata", r, { once: true }));
  videoEl.style.display = canvasEl.style.display = "block";
  onReady?.();

  const PROC_W = 320, PROC_H = 240;
  const ctx   = canvasEl.getContext("2d");
  const mpCv  = Object.assign(document.createElement("canvas"), { width: PROC_W, height: PROC_H });
  const mpCtx = mpCv.getContext("2d");

  // Pick backend: GPU for any real device, CPU/WASM for WSL2/no-GPU environments
  let backend;
  if (hasWebGL2()) {
    try {
      backend = await makeGPUBackend();
      console.log("Using GPU backend (tasks-vision)");
    } catch (e) {
      console.warn("GPU backend failed, falling back to CPU:", e.message);
      backend = await makeCPUBackend(PROC_W, PROC_H);
    }
  } else {
    console.log("WebGL 2 unavailable — using CPU/WASM backend");
    backend = await makeCPUBackend(PROC_W, PROC_H);
  }

  let running = true, animId = null, lastHands = null;

  // Render loop: redraws cached landmarks at ~60 fps (smooth regardless of backend)
  function renderLoop() {
    const w = videoEl.videoWidth, h = videoEl.videoHeight;
    if (w && h) {
      if (canvasEl.width  !== w) canvasEl.width  = w;
      if (canvasEl.height !== h) canvasEl.height = h;
      ctx.clearRect(0, 0, w, h);
      if (lastHands) {
        lastHands.forEach(({ handedness, landmarks: lm }) =>
          drawHand(ctx, lm, handedness === "Right", w, h)
        );
      }
    }
    if (running) animId = requestAnimationFrame(renderLoop);
  }

  // Detection loop: runs at backend's target fps
  async function detectLoop() {
    while (running) {
      const t0 = performance.now();
      const w  = videoEl.videoWidth, h = videoEl.videoHeight;
      if (w && h) {
        mpCtx.save();
        mpCtx.translate(PROC_W, 0); mpCtx.scale(-1, 1);
        mpCtx.drawImage(videoEl, 0, 0, PROC_W, PROC_H);
        mpCtx.restore();

        try {
          const hands = await backend.detect(mpCv);
          lastHands = hands;

          let loco = LocoGesture.UNKNOWN, arm = ArmGesture.UNKNOWN;
          for (const { handedness, landmarks: lm } of hands) {
            if (handedness === "Right") loco = recognizeLoco(lm, handedness);
            else                        arm  = recognizeArm(lm, handedness);
          }
          onGesture?.({ loco, arm });
        } catch (e) {
          console.warn("Detection error, switching to CPU:", e.message);
          // GPU backend crashed at runtime — swap to CPU and continue
          if (backend.targetMs === 66) {
            backend = await makeCPUBackend(PROC_W, PROC_H);
          }
        }
      }
      await new Promise(r => setTimeout(r, Math.max(16, backend.targetMs - (performance.now() - t0))));
    }
    backend.destroy();
  }

  animId = requestAnimationFrame(renderLoop);
  detectLoop();

  return () => {
    running = false;
    cancelAnimationFrame(animId);
    stream.getTracks().forEach(t => t.stop());
    videoEl.srcObject = null;
    videoEl.style.display = canvasEl.style.display = "none";
    ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
  };
}
