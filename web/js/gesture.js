/**
 * gesture.js — hand detection + gesture recognition, main thread.
 *
 * Two independent loops keep the UI smooth:
 *   renderLoop   — rAF at ~60 fps, only redraws cached landmarks, never calls MediaPipe.
 *   detectLoop   — async/setTimeout at ≤15 fps, runs MediaPipe then yields via await so
 *                  the browser can paint frames and handle events between detections.
 *
 * Canvas dimensions are only updated when the video resolution actually changes,
 * avoiding the expensive canvas-reset-every-frame that caused the original slowness.
 */

import { HandLandmarker, FilesetResolver } from
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

const WASM_PATH  = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
const MODEL_PATH = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

// ── Gesture enums (port of gesture/recognizer.py) ─────────────────────────────
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
  if (!i && !m && !r && !p) return LocoGesture.STOP;  // fist — thumb ignored (unreliable in fist)
  if (up.every(Boolean))   return LocoGesture.FORWARD;
  if (i && !m && !r && !p) return LocoGesture.TURN_LEFT;
  if (i &&  m && !r && !p) return LocoGesture.TURN_RIGHT;
  if (i &&  m &&  r && !p) return LocoGesture.BACKWARD;
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

// ── Hand drawing (no DrawingUtils dependency — lighter) ───────────────────────
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

// ── MediaPipe — starts loading as soon as this module is imported ─────────────
const PROC_W = 320, PROC_H = 240;
const DETECT_MS = 66;  // ≤15 fps detection rate

let handLandmarker = null;
const _mpReady = (async () => {
  const resolver = await FilesetResolver.forVisionTasks(WASM_PATH);
  handLandmarker = await HandLandmarker.createFromOptions(resolver, {
    baseOptions: { modelAssetPath: MODEL_PATH, delegate: "CPU" },
    runningMode: "VIDEO",
    numHands: 2,
    minHandDetectionConfidence: 0.7,
    minHandPresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });
})();

// ── Public API ────────────────────────────────────────────────────────────────
export async function startCamera(videoEl, canvasEl, onGesture, onReady) {
  // 1. Request camera permission first — prompt appears immediately on click.
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: 640, height: 480, facingMode: "user" },
  });
  videoEl.srcObject = stream;
  await new Promise(r => videoEl.addEventListener("loadeddata", r, { once: true }));
  videoEl.style.display = canvasEl.style.display = "block";
  onReady?.();

  // 2. Wait for MediaPipe — usually already done from preload.
  await _mpReady;

  // Offscreen canvas for flip + downscale (matches Python's cv2.flip + resize).
  const mpCv  = Object.assign(document.createElement("canvas"), { width: PROC_W, height: PROC_H });
  const mpCtx = mpCv.getContext("2d");
  const ctx   = canvasEl.getContext("2d");

  let running = true, animId = null, lastResults = null;

  // ── Render loop: redraws cached landmarks at ~60 fps ─────────────────────
  function renderLoop() {
    const w = videoEl.videoWidth, h = videoEl.videoHeight;
    if (w && h) {
      if (canvasEl.width  !== w) canvasEl.width  = w;  // only on resolution change
      if (canvasEl.height !== h) canvasEl.height = h;
      ctx.clearRect(0, 0, w, h);
      if (lastResults?.landmarks) {
        lastResults.landmarks.forEach((lm, i) => {
          const isRight = lastResults.handednesses[i][0].categoryName === "Right";
          drawHand(ctx, lm, isRight, w, h);
        });
      }
    }
    if (running) animId = requestAnimationFrame(renderLoop);
  }

  // ── Detection loop: runs MediaPipe then yields so the browser can paint ────
  async function detectLoop() {
    while (running) {
      const t0 = performance.now();
      const w  = videoEl.videoWidth, h = videoEl.videoHeight;

      if (w && h) {
        mpCtx.save();
        mpCtx.translate(PROC_W, 0); mpCtx.scale(-1, 1);
        mpCtx.drawImage(videoEl, 0, 0, PROC_W, PROC_H);
        mpCtx.restore();

        lastResults = handLandmarker.detectForVideo(mpCv, performance.now());

        let loco = LocoGesture.UNKNOWN, arm = ArmGesture.UNKNOWN;
        if (lastResults.landmarks) {
          lastResults.landmarks.forEach((lm, i) => {
            const hedness = lastResults.handednesses[i][0].categoryName;
            if (hedness === "Right") loco = recognizeLoco(lm, hedness);
            else                     arm  = recognizeArm(lm, hedness);
          });
        }
        onGesture?.({ loco, arm });
      }

      // Yield to the browser — this is what keeps the render loop smooth.
      await new Promise(r => setTimeout(r, Math.max(16, DETECT_MS - (performance.now() - t0))));
    }
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
