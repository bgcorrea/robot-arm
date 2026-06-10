#!/usr/bin/env python3
from __future__ import annotations
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
import inspect
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

RELAY_URL  = os.getenv("RELAY_URL", "").strip()
CONTROL_HZ = 30  # rate at which we tick the robot control loop (keeps gripper state machine alive)

def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Robot agent — conecta al relay y controla el robot.")
    p.add_argument("--port", default=None,
                   help="Puerto serial explícito (ej: /dev/ttyUSB0, /dev/ttyS7, COM5). "
                        "Equivalente a setear ROBOT_PORT.")
    p.add_argument("--ble", action="store_true",
                   help="Conectar via Bluetooth BLE en lugar de serial. "
                        "Requiere bleak (pip install bleak) y ejecutarse en Windows. "
                        "Usa BLE_WRITE_UUID y BLE_ADDRESS para configurar el dispositivo.")
    return p.parse_args()


async def _session(relay_url: str, robot: RobotController | None) -> None:
    """Single WebSocket session: exits on disconnect, caller retries."""
    state: dict = {
        "loco": LocoGesture.UNKNOWN,
        "arm":  ArmGesture.UNKNOWN,
    }

    async def _rcall(fn, *args) -> None:
        """Llama fn(*args); si devuelve una coroutine la awaita (soporta serial y BLE)."""
        result = fn(*args)
        if inspect.isawaitable(result):
            await result

    async def control_loop() -> None:
        """Ticks the robot at CONTROL_HZ so the gripper timer fires correctly."""
        while True:
            if robot:
                if state["loco"] is LocoGesture.UNKNOWN:
                    await _rcall(robot.stop)
                else:
                    await _rcall(robot.apply_loco, state["loco"])
                await _rcall(robot.apply_arm, state["arm"])
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


async def _async_main(args) -> None:
    robot = None
    try:
        if args.ble:
            from robot.ble_controller import BleRobotController
            robot = BleRobotController()
            await robot.connect()
        else:
            from robot.controller import RobotController
            robot = RobotController()
            print(f"Conectando al robot en {robot._port}…")
            robot.connect()
        print("Robot conectado.")
    except Exception as exc:
        print(f"Robot no disponible ({exc}) — modo demo (sin hardware)")

    try:
        await _run_forever(RELAY_URL, robot)
    finally:
        if robot:
            result = robot.disconnect()
            if inspect.isawaitable(result):
                await result


def main() -> None:
    args = _parse_args()

    if not RELAY_URL:
        print("ERROR: RELAY_URL not set.")
        print("  export RELAY_URL=wss://your-app.railway.app/ws/agent")
        sys.exit(1)

    if args.port:
        os.environ["ROBOT_PORT"] = args.port

    try:
        asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        print("\nStopping agent…")


if __name__ == "__main__":
    main()
