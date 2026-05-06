import platform
import time
from megapi import MegaPi
from gesture.recognizer import LocoGesture, ArmGesture

# ── Auto-detección del puerto serial ─────────────────────────────────────────
def _find_serial_port() -> str:
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            if any(k in p.description.lower() for k in ("ch340", "ch341", "megapi", "usb serial")):
                return p.device
    except Exception:
        pass
    # Fallback por OS si no se detecta automáticamente
    return {"Windows": "COM3", "Darwin": "/dev/tty.usbserial-1420"}.get(
        platform.system(), "/dev/ttyACM0"
    )

SERIAL_PORT = _find_serial_port()

# Orugas (encoder motor driver): slots 1 y 2 del módulo
TRACK_LEFT  = 1
TRACK_RIGHT = 2

# Servos del brazo (servoRun usa puerto RJ25 + slot 1/2 dentro del adaptador)
SERVO_BASE_PORT,     SERVO_BASE_SLOT     = 1, 1
SERVO_SHOULDER_PORT, SERVO_SHOULDER_SLOT = 1, 2
SERVO_ELBOW_PORT,    SERVO_ELBOW_SLOT    = 2, 1

# Pinza: motor DC (puerto 9 del driver)
GRIPPER_PORT = 9

# ── Parámetros de movimiento ──────────────────────────────────────────────────
TRACK_SPEED   = 150   # rango: -255..255
SERVO_STEP    =   5   # grados por frame durante gestos continuos
SERVO_MIN     =  10
SERVO_MAX     = 170
GRIPPER_SPEED = 200


class RobotController:

    def __init__(self, port: str = SERIAL_PORT):
        self._bot  = MegaPi()
        self._port = port
        self._shoulder = 90
        self._elbow    = 90
        self._base     = 90

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._bot.start(self._port)
        time.sleep(1)  # espera reset del Arduino tras abrir el puerto

    def disconnect(self) -> None:
        self.stop()
        self._bot.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ── Orugas ────────────────────────────────────────────────────────────────

    def apply_loco(self, gesture: LocoGesture) -> None:
        dispatch = {
            LocoGesture.STOP:       self.stop,
            LocoGesture.FORWARD:    self._forward,
            LocoGesture.BACKWARD:   self._backward,
            LocoGesture.TURN_LEFT:  self._turn_left,
            LocoGesture.TURN_RIGHT: self._turn_right,
        }
        fn = dispatch.get(gesture)
        if fn:
            fn()

    def stop(self) -> None:
        self._bot.encoderMotorRun(TRACK_LEFT,  0)
        self._bot.encoderMotorRun(TRACK_RIGHT, 0)

    def _forward(self) -> None:
        # Los motores están montados en espejo; un lado necesita velocidad negativa
        self._bot.encoderMotorRun(TRACK_LEFT,   TRACK_SPEED)
        self._bot.encoderMotorRun(TRACK_RIGHT, -TRACK_SPEED)

    def _backward(self) -> None:
        self._bot.encoderMotorRun(TRACK_LEFT,  -TRACK_SPEED)
        self._bot.encoderMotorRun(TRACK_RIGHT,  TRACK_SPEED)

    def _turn_left(self) -> None:
        self._bot.encoderMotorRun(TRACK_LEFT,  -TRACK_SPEED)
        self._bot.encoderMotorRun(TRACK_RIGHT, -TRACK_SPEED)

    def _turn_right(self) -> None:
        self._bot.encoderMotorRun(TRACK_LEFT,   TRACK_SPEED)
        self._bot.encoderMotorRun(TRACK_RIGHT,  TRACK_SPEED)

    # ── Brazo robótico ────────────────────────────────────────────────────────

    def apply_arm(self, gesture: ArmGesture) -> None:
        if gesture == ArmGesture.HOME:
            self._arm_home()

        elif gesture == ArmGesture.SHOULDER_UP:
            self._shoulder = _clamp(self._shoulder - SERVO_STEP)
            self._bot.servoRun(SERVO_SHOULDER_PORT, SERVO_SHOULDER_SLOT, self._shoulder)

        elif gesture == ArmGesture.SHOULDER_DOWN:
            self._shoulder = _clamp(self._shoulder + SERVO_STEP)
            self._bot.servoRun(SERVO_SHOULDER_PORT, SERVO_SHOULDER_SLOT, self._shoulder)

        elif gesture == ArmGesture.EXTEND:
            self._elbow = _clamp(self._elbow + SERVO_STEP)
            self._bot.servoRun(SERVO_ELBOW_PORT, SERVO_ELBOW_SLOT, self._elbow)

        elif gesture == ArmGesture.GRIP_CLOSE:
            self._bot.dcMotorRun(GRIPPER_PORT,  GRIPPER_SPEED)

        elif gesture == ArmGesture.GRIP_OPEN:
            self._bot.dcMotorRun(GRIPPER_PORT, -GRIPPER_SPEED)

        else:  # UNKNOWN — detener pinza para evitar sobrecargar el motor
            self._bot.dcMotorRun(GRIPPER_PORT, 0)

    def _arm_home(self) -> None:
        self._shoulder = self._elbow = self._base = 90
        self._bot.servoRun(SERVO_SHOULDER_PORT, SERVO_SHOULDER_SLOT, 90)
        self._bot.servoRun(SERVO_ELBOW_PORT,    SERVO_ELBOW_SLOT,    90)
        self._bot.servoRun(SERVO_BASE_PORT,     SERVO_BASE_SLOT,     90)
        self._bot.dcMotorRun(GRIPPER_PORT, 0)


# ── Utilidad ──────────────────────────────────────────────────────────────────

def _clamp(angle: int) -> int:
    return max(SERVO_MIN, min(SERVO_MAX, angle))
