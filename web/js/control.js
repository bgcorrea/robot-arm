/**
 * control.js — WebSocket client + manual controls + keyboard bindings.
 *
 * Connects to /ws/browser on the same host (Railway or localhost).
 * Imports gesture.js dynamically only when the camera is activated.
 */

// Eagerly import gesture.js so MediaPipe starts loading in the background.
// By the time the user clicks "Activar cámara" the WASM + model are ready.
const gestureModPromise = import("./gesture.js");
let gestureMod = null;
gestureModPromise.then((m) => { gestureMod = m; });

// ── WebSocket relay URL (auto-detects host) ───────────────────────────────────
const WS_PROTO = location.protocol === "https:" ? "wss:" : "ws:";
const RELAY_URL = `${WS_PROTO}//${location.host}/ws/browser`;

// ── Gesture label maps ────────────────────────────────────────────────────────
const LOCO_LABELS = {
  UNKNOWN:    ["—",          "Sin gesto"],
  STOP:       ["✊ Stop",    "Detenido"],
  FORWARD:    ["🖐 Adelante","Avanzando"],
  BACKWARD:   ["3↑ Atrás",  "Retrocediendo"],
  TURN_LEFT:  ["☝️ Izq.",   "Girando izquierda"],
  TURN_RIGHT: ["✌️ Der.",   "Girando derecha"],
};
const ARM_LABELS = {
  UNKNOWN:       ["—",              "Sin gesto"],
  HOME:          ["✊ Home",        "Brazo detenido"],
  SHOULDER_UP:   ["☝️ Hombro ↑",   "Hombro arriba"],
  SHOULDER_DOWN: ["✌️ Hombro ↓",   "Hombro abajo"],
  GRIP_CLOSE:    ["🤏 Cerrar",      "Cerrando pinza"],
  GRIP_OPEN:     ["4↑ Abrir",       "Abriendo pinza"],
  EXTEND:        ["3↑ Extender",    "Extendiendo codo"],
  RETRACT:       ["🤙 Retraer",     "Retrayendo codo"],
  BASE_LEFT:     ["🖕 Base ←",      "Rotando base izq."],
  BASE_RIGHT:    ["💍 Base →",      "Rotando base der."],
};

// ── DOM refs ──────────────────────────────────────────────────────────────────
const videoEl    = document.getElementById("video");
const canvasEl   = document.getElementById("canvas");
const noCam      = document.getElementById("no-cam");
const cameraBtn  = document.getElementById("camera-btn");
const robotDot   = document.getElementById("robot-dot");
const robotLabel = document.getElementById("robot-label");
const cameraDot  = document.getElementById("camera-dot");
const cameraLbl  = document.getElementById("camera-label");
const locoCard   = document.getElementById("loco-card");
const armCard    = document.getElementById("arm-card");
const locoName   = document.getElementById("loco-name");
const locoDesc   = document.getElementById("loco-desc");
const armName    = document.getElementById("arm-name");
const armDesc    = document.getElementById("arm-desc");
const camCta     = document.getElementById("cam-cta");
if (camCta) camCta.addEventListener("click", () => cameraBtn.click());

// ── State ─────────────────────────────────────────────────────────────────────
let ws           = null;
let wsReady      = false;
let cameraActive = false;
let stopCamera   = null;
let manualLoco   = "UNKNOWN";
let manualArm    = "UNKNOWN";
// While gesture mode is active, gesture commands take over
let gestureLoco  = "UNKNOWN";
let gestureArm   = "UNKNOWN";

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connect() {
  ws = new WebSocket(RELAY_URL);

  ws.onopen = () => { wsReady = true; };

  ws.onclose = () => {
    wsReady = false;
    setRobotStatus(false);
    setTimeout(connect, 3000);
  };

  ws.onerror = () => { ws.close(); };

  ws.onmessage = ({ data }) => {
    try {
      const msg = JSON.parse(data);
      if (msg.type === "agent_status") setRobotStatus(msg.online);
    } catch (_) {}
  };
}

function send(loco, arm) {
  if (wsReady) {
    ws.send(JSON.stringify({ type: "command", loco, arm }));
  }
}

// ── UI helpers ────────────────────────────────────────────────────────────────
const downloadPanel = document.getElementById("download-panel");
const macHint       = document.getElementById("mac-hint");
if (/mac/i.test(navigator.platform || navigator.userAgent)) {
  macHint.style.display = "block";
}

function setRobotStatus(online) {
  robotDot.className     = `dot ${online ? "online" : ""}`;
  robotLabel.textContent = online ? "Robot conectado" : "Robot offline";
  downloadPanel.style.display = online ? "none" : "flex";
  document.body.classList.toggle("robot-offline", !online);
}

function setCameraStatus(active) {
  cameraDot.className    = `dot ${active ? "online" : ""}`;
  cameraLbl.textContent  = active ? "Cámara activa" : "Cámara inactiva";
}

function updateGestureUI(loco, arm) {
  const [ln, ld] = LOCO_LABELS[loco] ?? LOCO_LABELS.UNKNOWN;
  const [an, ad] = ARM_LABELS[arm]   ?? ARM_LABELS.UNKNOWN;

  locoName.textContent = ln;
  locoDesc.textContent = ld;
  armName.textContent  = an;
  armDesc.textContent  = ad;

  locoCard.classList.toggle("active", loco !== "UNKNOWN");
  armCard.classList.toggle("active",  arm  !== "UNKNOWN");
}

function setButtonActive(selector, active) {
  document.querySelectorAll(selector).forEach((el) =>
    el.classList.toggle("active", active)
  );
}

// ── Camera toggle ─────────────────────────────────────────────────────────────
cameraBtn.addEventListener("click", async () => {
  if (cameraActive) {
    stopCamera?.();
    stopCamera   = null;
    cameraActive = false;
    gestureLoco  = "UNKNOWN";
    gestureArm   = "UNKNOWN";
    noCam.style.display = "flex";
    cameraBtn.textContent = "Activar cámara";
    if (camCta) camCta.style.display = "";
    setCameraStatus(false);
    send("UNKNOWN", "UNKNOWN");
    updateGestureUI("UNKNOWN", "UNKNOWN");
    return;
  }

  cameraBtn.textContent = "Cargando MediaPipe…";
  cameraBtn.disabled    = true;
  if (camCta) camCta.style.display = "none";

  try {
    if (!gestureMod) gestureMod = await gestureModPromise;
    stopCamera = await gestureMod.startCamera(
      videoEl,
      canvasEl,
      ({ loco, arm }) => {
        gestureLoco = loco;
        gestureArm  = arm;
        send(loco, arm);
        updateGestureUI(loco, arm);
      },
      () => {
        noCam.style.display   = "none";
        cameraActive          = true;
        cameraBtn.textContent = "Desactivar cámara";
        cameraBtn.disabled    = false;
        setCameraStatus(true);
      }
    );
  } catch (err) {
    console.error("Camera error:", err);
    cameraBtn.textContent = "Error — reintentar";
    cameraBtn.disabled    = false;
    if (camCta) camCta.style.display = "";
  }
});

// ── Manual controls (buttons) ─────────────────────────────────────────────────
document.querySelectorAll("[data-loco]").forEach((btn) => {
  const loco = btn.dataset.loco;

  btn.addEventListener("pointerdown", () => {
    if (cameraActive) return;
    manualLoco = loco;
    btn.classList.add("active");
    send(manualLoco, manualArm);
    updateGestureUI(manualLoco, manualArm);
  });

  const release = () => {
    if (cameraActive) return;
    if (manualLoco === loco) {
      manualLoco = "UNKNOWN";
      btn.classList.remove("active");
      send(manualLoco, manualArm);
      updateGestureUI(manualLoco, manualArm);
    }
  };
  btn.addEventListener("pointerup",    release);
  btn.addEventListener("pointerleave", release);
});

document.querySelectorAll("[data-arm]").forEach((btn) => {
  const arm = btn.dataset.arm;

  btn.addEventListener("pointerdown", () => {
    if (cameraActive) return;
    manualArm = arm;
    btn.classList.add("active");
    send(manualLoco, manualArm);
    updateGestureUI(manualLoco, manualArm);
  });

  const release = () => {
    if (cameraActive) return;
    if (manualArm === arm) {
      manualArm = "UNKNOWN";
      btn.classList.remove("active");
      send(manualLoco, manualArm);
      updateGestureUI(manualLoco, manualArm);
    }
  };
  btn.addEventListener("pointerup",    release);
  btn.addEventListener("pointerleave", release);
});

// ── Keyboard controls ─────────────────────────────────────────────────────────
const KEY_LOCO = { w: "FORWARD", s: "BACKWARD", a: "TURN_LEFT", d: "TURN_RIGHT" };
const KEY_ARM  = { r: "SHOULDER_UP", f: "SHOULDER_DOWN", q: "GRIP_OPEN", e: "GRIP_CLOSE" };
const held = new Set();

document.addEventListener("keydown", (ev) => {
  if (cameraActive) return;
  const k = ev.key.toLowerCase();
  if (held.has(k)) return;
  held.add(k);

  if (KEY_LOCO[k]) {
    manualLoco = KEY_LOCO[k];
    send(manualLoco, manualArm);
    updateGestureUI(manualLoco, manualArm);
    // highlight matching dpad button
    document.querySelector(`[data-loco="${manualLoco}"]`)?.classList.add("active");
  }
  if (KEY_ARM[k]) {
    manualArm = KEY_ARM[k];
    send(manualLoco, manualArm);
    updateGestureUI(manualLoco, manualArm);
    document.querySelector(`[data-arm="${manualArm}"]`)?.classList.add("active");
  }
});

document.addEventListener("keyup", (ev) => {
  if (cameraActive) return;
  const k = ev.key.toLowerCase();
  held.delete(k);

  if (KEY_LOCO[k] && manualLoco === KEY_LOCO[k]) {
    document.querySelector(`[data-loco="${manualLoco}"]`)?.classList.remove("active");
    manualLoco = "UNKNOWN";
    send(manualLoco, manualArm);
    updateGestureUI(manualLoco, manualArm);
  }
  if (KEY_ARM[k] && manualArm === KEY_ARM[k]) {
    document.querySelector(`[data-arm="${manualArm}"]`)?.classList.remove("active");
    manualArm = "UNKNOWN";
    send(manualLoco, manualArm);
    updateGestureUI(manualLoco, manualArm);
  }
});

// ── Start ─────────────────────────────────────────────────────────────────────
connect();
