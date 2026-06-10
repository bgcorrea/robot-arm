#!/usr/bin/env python3
"""
Local robot agent.

Connects to the Railway relay via WebSocket, receives gesture commands from
browser clients and forwards them to the physical robot over serial.

Usage
-----
    export RELAY_URL=wss://your-app.railway.app/ws/agent
    python agent.py
"""
import asyncio
import json
import os
import sys
import traceback

try:
    import websockets
    import websockets.exceptions
except ImportError:
    print("ERROR: websockets not installed — run: pip install websockets")
    sys.exit(1)

from gesture.recognizer import ArmGesture, LocoGesture
from robot.controller import RobotController

RELAY_URL  = os.getenv("RELAY_URL", "").strip()
CONTROL_HZ = 30  # rate at which we tick the robot control loop (keeps gripper state machine alive)

def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Robot agent — conecta al relay y controla el robot.")
    p.add_argument("--port", default=None,
                   help="Puerto serial explícito (ej: /dev/ttyUSB0, /dev/ttyS7, COM5). "
                        "Equivalente a setear ROBOT_PORT.")
    return p.parse_args()


async def _session(relay_url: str, robot: RobotController | None) -> None:
    """Single WebSocket session: exits on disconnect, caller retries."""
    state: dict = {
        "loco": LocoGesture.UNKNOWN,
        "arm":  ArmGesture.UNKNOWN,
    }

    async def control_loop() -> None:
        """Ticks the robot at CONTROL_HZ so the gripper timer fires correctly."""
        while True:
            if robot:
                if state["loco"] is LocoGesture.UNKNOWN:
                    robot.stop()
                else:
                    robot.apply_loco(state["loco"])
                robot.apply_arm(state["arm"])
            await asyncio.sleep(1 / CONTROL_HZ)

    async def ws_loop() -> None:
        print(f"Connecting to relay: {relay_url}")
        async with websockets.connect(relay_url) as ws:
            print("Relay connected — waiting for commands…")
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    if msg.get("type") == "command":
                        state["loco"] = LocoGesture[msg.get("loco", "UNKNOWN")]
                        state["arm"]  = ArmGesture[msg.get("arm",  "UNKNOWN")]
                        await ws.send(json.dumps({
                            "type":  "status",
                            "robot": robot is not None,
                            "loco":  state["loco"].name,
                            "arm":   state["arm"].name,
                        }))
                except Exception:
                    traceback.print_exc()

    await asyncio.gather(control_loop(), ws_loop())


async def _run_forever(relay_url: str, robot: RobotController | None) -> None:
    while True:
        try:
            await _session(relay_url, robot)
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            print(f"Disconnected: {exc}. Retrying in 5 s…")
            await asyncio.sleep(5)
        except Exception:
            traceback.print_exc()
            await asyncio.sleep(5)


def main() -> None:
    args = _parse_args()

    if not RELAY_URL:
        print("ERROR: RELAY_URL not set.")
        print("  export RELAY_URL=wss://your-app.railway.app/ws/agent")
        sys.exit(1)

    # --port flag overrides ROBOT_PORT env var and auto-detection
    if args.port:
        os.environ["ROBOT_PORT"] = args.port

    robot: RobotController | None = None
    try:
        robot = RobotController()
        print(f"Conectando al robot en {robot._port}…")
        robot.connect()
        print("Robot conectado.")
    except Exception as exc:
        print(f"Robot no disponible ({exc}) — modo demo (sin hardware)")

    try:
        asyncio.run(_run_forever(RELAY_URL, robot))
    except KeyboardInterrupt:
        print("\nStopping agent…")
    finally:
        if robot:
            robot.disconnect()


if __name__ == "__main__":
    main()
