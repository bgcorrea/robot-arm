import os
import platform
import time
from enum import Enum, auto
from megapi import MegaPi
from gesture.recognizer import LocoGesture, ArmGesture

# ── Auto-detección del puerto serial ─────────────────────────────────────────
# Prioridad: ROBOT_PORT env var > USB > Bluetooth > default de plataforma
_USB_HINTS = ("ch340", "ch341", "megapi", "usb serial", "usb-serial", "cp210", "ftdi")
_BT_HINTS  = ("bluetooth", "rfcomm", "hc-05", "hc-06", "bth", "makeblock bt")

def _find_serial_port() -> str:
    override = os.getenv("ROBOT_PORT", "").strip()
    if override:
        return override

    try:
        import serial.tools.list_ports
        usb, bt = None, None
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            if not usb and any(k in desc for k in _USB_HINTS):
                usb = p.device
            if not bt and any(k in desc for k in _BT_HINTS):
                bt = p.device
        if usb:
            return usb
        if bt:
            return bt
    except Exception:
        pass

    # WSL2: los COM ports de Bluetooth de Windows aparecen como /dev/ttyS<n>.
    # Si ROBOT_PORT no está seteado y no se detectó nada arriba, es necesario
    # setear ROBOT_PORT=COM<n> (Windows) o ROBOT_PORT=/dev/ttyS<n> (WSL2).
    return {"Windows": "COM3", "Darwin": "/dev/tty.usbserial-1420"}.get(
        platform.system(), "/dev/ttyUSB0"
    )

SERIAL_PORT = _find_serial_port()

# ── Slots ─────────────────────────────────────────────────────────────────────
TRACK_LEFT   = 1
TRACK_RIGHT  = 2
ARM_SLOT     = 3
GRIPPER_SLOT = 4

# ── Parámetros ────────────────────────────────────────────────────────────────
TRACK_SPEED         = 150
ARM_SPEED           = 100
GRIPPER_CLOSE_SPEED = 150
GRIPPER_OPEN_SPEED  = 230
GRIPPER_OPEN_TIME   = 1.5   # 1s abre ~2cm; 1.5s abre ~3cm
GRIPPER_CLOSE_TIME  = 0.6   # cierra totalmente en <0.7s
GRIPPER_CALIB_TIME  = 0.8   # margen sobre GRIPPER_CLOSE_TIME


class _GripState(Enum):
    IDLE    = auto()
    OPENING = auto()
    CLOSING = auto()


class RobotController:

    def __init__(self, port: str = SERIAL_PORT):
        self._bot  = MegaPi()
        self._port = port
        self._grip_state = _GripState.IDLE
        self._grip_start = 0.0
        self._grip_armed = True
        self._loco_dispatch = {
            LocoGesture.STOP:       self.stop,
            LocoGesture.FORWARD:    self._forward,
            LocoGesture.BACKWARD:   self._backward,
            LocoGesture.TURN_LEFT:  self._turn_left,
            LocoGesture.TURN_RIGHT: self._turn_right,
        }

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._bot.start(self._port)
        time.sleep(1)
        self._calibrate_gripper()

    def _calibrate_gripper(self) -> None:
        print("Calibrando pinza...")
        self._bot.encoderMotorRun(GRIPPER_SLOT, -GRIPPER_CLOSE_SPEED)
        time.sleep(GRIPPER_CALIB_TIME)
        self._bot.encoderMotorRun(GRIPPER_SLOT, 0)
        time.sleep(0.2)
        self._bot.encoderMotorSetCurPosZero(GRIPPER_SLOT)
        self._grip_state = _GripState.IDLE
        self._grip_armed = True
        print("Pinza calibrada.")

    def disconnect(self) -> None:
        self.stop()
        self._bot.encoderMotorRun(ARM_SLOT,     0)
        self._bot.encoderMotorRun(GRIPPER_SLOT, 0)
        self._bot.close()

    def __enter__(self): self.connect(); return self
    def __exit__(self, *_): self.disconnect()

    # ── Orugas ────────────────────────────────────────────────────────────────

    def apply_loco(self, gesture: LocoGesture) -> None:
        fn = self._loco_dispatch.get(gesture)
        if fn: fn()

    def stop(self) -> None:
        self._bot.encoderMotorRun(TRACK_LEFT,  0)
        self._bot.encoderMotorRun(TRACK_RIGHT, 0)

    def _forward(self):
        self._bot.encoderMotorRun(TRACK_LEFT,   TRACK_SPEED)
        self._bot.encoderMotorRun(TRACK_RIGHT, -TRACK_SPEED)

    def _backward(self):
        self._bot.encoderMotorRun(TRACK_LEFT,  -TRACK_SPEED)
        self._bot.encoderMotorRun(TRACK_RIGHT,  TRACK_SPEED)

    def _turn_left(self):
        self._bot.encoderMotorRun(TRACK_LEFT,  -TRACK_SPEED)
        self._bot.encoderMotorRun(TRACK_RIGHT, -TRACK_SPEED)

    def _turn_right(self):
        self._bot.encoderMotorRun(TRACK_LEFT,   TRACK_SPEED)
        self._bot.encoderMotorRun(TRACK_RIGHT,  TRACK_SPEED)

    # ── Brazo robótico ────────────────────────────────────────────────────────

    def _update_gripper(self) -> None:
        """Verifica si el temporizador de la pinza expiró. Se llama cada frame."""
        if self._grip_state == _GripState.IDLE:
            return
        elapsed = time.monotonic() - self._grip_start
        if self._grip_state == _GripState.OPENING and elapsed >= GRIPPER_OPEN_TIME:
            self._bot.encoderMotorRun(GRIPPER_SLOT, 0)
            self._bot.encoderMotorSetCurPosZero(GRIPPER_SLOT)
            self._grip_state = _GripState.IDLE
            print("Pinza abierta.")
        elif self._grip_state == _GripState.CLOSING and elapsed >= GRIPPER_CLOSE_TIME:
            self._bot.encoderMotorRun(GRIPPER_SLOT, 0)
            self._bot.encoderMotorSetCurPosZero(GRIPPER_SLOT)
            self._grip_state = _GripState.IDLE
            self._grip_armed = True
            print("Pinza cerrada — lista para abrir.")

    def apply_arm(self, gesture: ArmGesture) -> None:
        # Primero chequear si el temporizador de la pinza expiró
        self._update_gripper()
        active = self._grip_state != _GripState.IDLE

        if gesture == ArmGesture.SHOULDER_UP:
            self._bot.encoderMotorRun(ARM_SLOT, -ARM_SPEED)
            if not active:
                self._bot.encoderMotorRun(GRIPPER_SLOT, 0)

        elif gesture == ArmGesture.SHOULDER_DOWN:
            self._bot.encoderMotorRun(ARM_SLOT, ARM_SPEED)
            if not active:
                self._bot.encoderMotorRun(GRIPPER_SLOT, 0)

        elif gesture == ArmGesture.GRIP_CLOSE:
            self._bot.encoderMotorRun(ARM_SLOT, 0)
            if not self._grip_armed and self._grip_state == _GripState.IDLE:
                self._grip_state = _GripState.CLOSING
                self._grip_start = time.monotonic()
                self._bot.encoderMotorRun(GRIPPER_SLOT, -GRIPPER_CLOSE_SPEED)

        elif gesture == ArmGesture.GRIP_OPEN:
            self._bot.encoderMotorRun(ARM_SLOT, 0)
            if self._grip_armed and self._grip_state == _GripState.IDLE:
                self._grip_armed = False
                self._grip_state = _GripState.OPENING
                self._grip_start = time.monotonic()
                self._bot.encoderMotorRun(GRIPPER_SLOT, GRIPPER_OPEN_SPEED)
                print("Pinza abriendo...")

        else:
            self._bot.encoderMotorRun(ARM_SLOT, 0)
            if not active:
                self._bot.encoderMotorRun(GRIPPER_SLOT, 0)
