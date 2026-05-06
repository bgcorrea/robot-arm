import math
from enum import Enum, auto


class LocoGesture(Enum):
    UNKNOWN = auto()
    STOP = auto()        # ✊ puño           — 0 dedos arriba
    FORWARD = auto()     # ✋ mano abierta   — 5 dedos arriba
    BACKWARD = auto()    # 🤚 índice+medio+anular
    TURN_LEFT = auto()   # ☝️ solo índice
    TURN_RIGHT = auto()  # ✌️ índice+medio


class ArmGesture(Enum):
    UNKNOWN = auto()
    HOME = auto()           # ✊ puño
    SHOULDER_UP = auto()    # ☝️ índice apuntando hacia arriba
    SHOULDER_DOWN = auto()  # ☝️ índice apuntando hacia abajo
    GRIP_CLOSE = auto()     # 🤏 pinch (pulgar+índice juntos)
    GRIP_OPEN = auto()      # ✋ mano abierta
    EXTEND = auto()         # 3 dedos arriba


# Distancia normalizada máxima para detectar pinch
_PINCH_THRESHOLD = 0.06


def _fingers_up(lm, handedness: str) -> list[bool]:
    """
    Devuelve [pulgar, índice, medio, anular, meñique] — True si extendido.

    lm          : lista de 21 NormalizedLandmark de MediaPipe
    handedness  : "Right" o "Left" tal como reporta MediaPipe (imagen sin flip)
    """
    # Pulgar: comparación lateral. En imagen sin flip, el pulgar de la mano
    # derecha apunta a la izquierda cuando está extendido (tip.x < IP.x).
    if handedness == "Right":
        thumb = lm[4].x < lm[3].x
    else:
        thumb = lm[4].x > lm[3].x

    # Dedos restantes: la punta está por encima del nudo PIP cuando extendidos
    index  = lm[8].y  < lm[6].y
    middle = lm[12].y < lm[10].y
    ring   = lm[16].y < lm[14].y
    pinky  = lm[20].y < lm[18].y

    return [thumb, index, middle, ring, pinky]


def _pinch_distance(lm) -> float:
    dx = lm[4].x - lm[8].x
    dy = lm[4].y - lm[8].y
    return math.sqrt(dx * dx + dy * dy)


def recognize_loco(lm, handedness: str) -> LocoGesture:
    """Mano derecha → comando de locomoción (orugas)."""
    up = _fingers_up(lm, handedness)
    _, idx, mid, rng, pnk = up

    if not any(up):
        return LocoGesture.STOP

    if all(up):
        return LocoGesture.FORWARD

    if idx and not mid and not rng and not pnk:
        return LocoGesture.TURN_LEFT

    if idx and mid and not rng and not pnk:
        return LocoGesture.TURN_RIGHT

    if idx and mid and rng and not pnk:
        return LocoGesture.BACKWARD

    return LocoGesture.UNKNOWN


def recognize_arm(lm, handedness: str) -> ArmGesture:
    """Mano izquierda → comando del brazo robótico."""
    # Pinch tiene prioridad sobre el conteo de dedos
    if _pinch_distance(lm) < _PINCH_THRESHOLD:
        return ArmGesture.GRIP_CLOSE

    up = _fingers_up(lm, handedness)
    _, idx, mid, rng, pnk = up

    if not any(up):
        return ArmGesture.HOME

    if all(up):
        return ArmGesture.GRIP_OPEN

    if idx and not mid and not rng and not pnk:
        # Índice apunta arriba si la punta está por encima de la muñeca
        if lm[8].y < lm[0].y:
            return ArmGesture.SHOULDER_UP
        return ArmGesture.SHOULDER_DOWN

    if sum(up) >= 3:
        return ArmGesture.EXTEND

    return ArmGesture.UNKNOWN
