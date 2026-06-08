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
    HOME = auto()            # ✊ puño
    SHOULDER_UP = auto()     # ☝️ solo índice
    SHOULDER_DOWN = auto()   # ✌️ índice+medio
    GRIP_CLOSE = auto()      # 🤏 pinch (pulgar+índice juntos)
    GRIP_OPEN = auto()       # 🖖 4 dedos (índice+medio+anular+meñique, pulgar libre)
    EXTEND = auto()          # índice+medio+anular — extiende codo
    RETRACT = auto()         # 🤙 solo meñique     — retrae codo
    BASE_LEFT = auto()       # 🖕 solo medio       — rota base izquierda
    BASE_RIGHT = auto()      # 💍 solo anular      — rota base derecha


# Distancia normalizada máxima para detectar pinch
_PINCH_THRESHOLD = 0.06


def _fingers_up(lm, handedness: str) -> list[bool]:
    """
    Devuelve [pulgar, índice, medio, anular, meñique] — True si extendido.

    lm          : lista de 21 NormalizedLandmark de MediaPipe
    handedness  : "Right" o "Left" tal como reporta MediaPipe sobre imagen ya
                  volteada (cv2.flip). En ese modo MediaPipe asume selfie, por
                  lo que "Right" corresponde a la mano derecha del usuario.
    """
    # Pulgar: comparación lateral. En imagen selfie (flip horizontal), el
    # pulgar de la mano derecha tiene tip.x < IP.x cuando está extendido.
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
    up = _fingers_up(lm, handedness)
    _, idx, mid, rng, pnk = up

    # 4 dedos arriba tiene prioridad sobre pinch (pulgar puede quedar cerca del índice)
    if idx and mid and rng and pnk:
        return ArmGesture.GRIP_OPEN

    if _pinch_distance(lm) < _PINCH_THRESHOLD:
        return ArmGesture.GRIP_CLOSE

    if not any(up):
        return ArmGesture.HOME

    # Gestos de un solo dedo
    if idx and not mid and not rng and not pnk:
        return ArmGesture.SHOULDER_UP

    if mid and not idx and not rng and not pnk:
        return ArmGesture.BASE_LEFT

    if rng and not idx and not mid and not pnk:
        return ArmGesture.BASE_RIGHT

    if pnk and not idx and not mid and not rng:
        return ArmGesture.RETRACT

    # ✌️ índice+medio → bajar brazo
    if idx and mid and not rng and not pnk:
        return ArmGesture.SHOULDER_DOWN

    # índice+medio+anular → extender codo
    if idx and mid and rng and not pnk:
        return ArmGesture.EXTEND

    return ArmGesture.UNKNOWN
