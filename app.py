import platform
import traceback
import cv2
import mediapipe as mp

from gesture.recognizer import ArmGesture, LocoGesture, recognize_arm, recognize_loco
from robot.controller import RobotController, SERIAL_PORT

mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils


def main() -> None:
    robot = _connect_robot()

    hands = mp_hands.Hands(
        max_num_hands=2,
        model_complexity=0,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )

    backend = cv2.CAP_V4L2 if platform.system() == "Linux" else cv2.CAP_ANY
    cap = cv2.VideoCapture(0, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("ERROR: no se pudo abrir la cámara.")
        print("  En WSL2: adjunta la webcam con 'usbipd attach --wsl --busid <id>'")
        if robot:
            robot.disconnect()
        return
    print("Cámara iniciada. Presiona 'q' para salir.")

    frame_count = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            frame_count += 1
            if frame_count % 30 == 1:
                print(f"Frame #{frame_count} OK")

            frame = cv2.flip(frame, 1)
            loco, arm = _process_frame(frame, hands)

            if robot:
                if loco is LocoGesture.UNKNOWN:
                    robot.stop()
                else:
                    robot.apply_loco(loco)
                robot.apply_arm(arm)

            _draw_hud(frame, loco, arm, connected=robot is not None)
            cv2.imshow("Robot PIA", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except Exception:
        traceback.print_exc()
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if robot:
            robot.disconnect()


def _connect_robot() -> RobotController | None:
    try:
        robot = RobotController(SERIAL_PORT)
        robot.connect()
        print(f"Robot conectado en {SERIAL_PORT}")
        return robot
    except Exception as exc:
        print(f"Robot no disponible ({exc}) — modo demo sin hardware")
        return None


def _process_frame(frame, hands) -> tuple[LocoGesture, ArmGesture]:
    loco = LocoGesture.UNKNOWN
    arm  = ArmGesture.UNKNOWN

    small   = cv2.resize(frame, (320, 240))
    rgb     = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb)

    if not results.multi_hand_landmarks:
        return loco, arm

    for lm_set, handedness in zip(
        results.multi_hand_landmarks, results.multi_handedness
    ):
        label = handedness.classification[0].label
        lm    = lm_set.landmark

        mp_draw.draw_landmarks(frame, lm_set, mp_hands.HAND_CONNECTIONS)

        if label == "Right":
            loco = recognize_loco(lm, label)
        else:
            arm = recognize_arm(lm, label)

    return loco, arm


def _draw_hud(
    frame, loco: LocoGesture, arm: ArmGesture, *, connected: bool
) -> None:
    h, w = frame.shape[:2]

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 110), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    loco_bg = (0, 180, 0) if loco is not LocoGesture.UNKNOWN else (50, 50, 50)
    cv2.rectangle(frame, (10, h - 105), (w // 2 - 10, h - 60), loco_bg, -1)
    cv2.putText(frame, "DERECHA", (18, h - 87),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    cv2.putText(frame, loco.name, (18, h - 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2)

    arm_bg = (180, 120, 0) if arm is not ArmGesture.UNKNOWN else (50, 50, 50)
    cv2.rectangle(frame, (w // 2 + 10, h - 105), (w - 10, h - 60), arm_bg, -1)
    cv2.putText(frame, "IZQUIERDA", (w // 2 + 18, h - 87),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    cv2.putText(frame, arm.name, (w // 2 + 18, h - 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2)

    conn_color = (0, 255, 80) if connected else (80, 80, 255)
    cv2.putText(frame, "ROBOT OK" if connected else "DEMO",
                (w // 2 - 45, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, conn_color, 2)


if __name__ == "__main__":
    main()
