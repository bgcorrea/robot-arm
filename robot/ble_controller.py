"""
Controlador BLE para MegaPi — reemplaza robot/controller.py cuando se usa Bluetooth.

Requiere bleak (pip install bleak) y ejecutarse en Windows (no WSL2).

Variables de entorno:
  BLE_DEVICE       Nombre parcial del dispositivo a buscar   (default: "Makeblock")
  BLE_ADDRESS      Dirección MAC BLE (omite el escaneo)      (optional)
  BLE_WRITE_UUID   UUID de la característica de escritura    (default: FFE3 de Makeblock)
"""
import asyncio
import os
import time
from enum import Enum, auto

from bleak import BleakClient, BleakScanner

from gesture.recognizer import ArmGesture, LocoGesture
from robot.protocol import encoder_motor_run, encoder_motor_set_pos_zero

_MAKEBLOCK_WRITE = "0000ffe3-0000-1000-8000-00805f9b34fb"

BLE_DEVICE     = os.getenv("BLE_DEVICE", "Makeblock")
BLE_ADDRESS    = os.getenv("BLE_ADDRESS", "").strip()
BLE_WRITE_UUID = os.getenv("BLE_WRITE_UUID", _MAKEBLOCK_WRITE)

TRACK_LEFT   = 1
TRACK_RIGHT  = 2
ARM_SLOT     = 3
GRIPPER_SLOT = 4

TRACK_SPEED         = 150
ARM_SPEED           = 100
GRIPPER_CLOSE_SPEED = 150
GRIPPER_OPEN_SPEED  = 230
GRIPPER_OPEN_TIME   = 1.5
GRIPPER_CLOSE_TIME  = 0.6
GRIPPER_CALIB_TIME  = 0.8


class _GripState(Enum):
    IDLE    = auto()
    OPENING = auto()
    CLOSING = auto()


class BleRobotController:

    def __init__(self, address: str = BLE_ADDRESS, write_uuid: str = BLE_WRITE_UUID):
        self._address      = address or None
        self._write_uuid   = write_uuid
        self._client: BleakClient | None = None
        self._reconnecting = False
        self._grip_state   = _GripState.IDLE
        self._grip_start   = 0.0
        self._grip_armed   = True
        # Deduplication: last sent gesture — evita writes repetidos al módulo BLE
        self._last_loco: LocoGesture | None = None
        self._last_arm:  ArmGesture  | None = None
        self._loco_dispatch = {
            LocoGesture.STOP:       self.stop,
            LocoGesture.FORWARD:    self._forward,
            LocoGesture.BACKWARD:   self._backward,
            LocoGesture.TURN_LEFT:  self._turn_left,
            LocoGesture.TURN_RIGHT: self._turn_right,
        }

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    async def connect(self) -> None:
        if not self._address:
            self._address = await self._scan_for_device()
        print(f"Conectando a {self._address} via BLE...")
        self._client = BleakClient(self._address, disconnected_callback=self._on_disconnected)
        await self._client.connect()
        print(f"BLE conectado. UUID escritura: {self._write_uuid}")
        await self._calibrate_gripper()

    def _on_disconnected(self, client: BleakClient) -> None:
        print("BLE desconectado — se intentará reconectar en el próximo comando.")
        self._last_loco = None
        self._last_arm  = None

    async def _try_reconnect(self) -> None:
        if self._reconnecting:
            return
        self._reconnecting = True
        print("Reconectando BLE...")
        try:
            self._client = BleakClient(self._address, disconnected_callback=self._on_disconnected)
            await self._client.connect()
            print("BLE reconectado.")
        except Exception as exc:
            print(f"Error reconectando: {exc}")
            self._client = None
        finally:
            self._reconnecting = False

    async def _scan_for_device(self) -> str:
        print(f"Escaneando BLE para '{BLE_DEVICE}'...")
        devices = await BleakScanner.discover(timeout=6.0)
        hint = BLE_DEVICE.lower()
        for d in devices:
            if d.name and hint in d.name.lower():
                print(f"Encontrado: {d.name} ({d.address})")
                return d.address
        raise RuntimeError(
            f"No se encontró dispositivo BLE con '{BLE_DEVICE}'. "
            "Ejecuta scan_ble.py para diagnosticar."
        )

    async def _write(self, data: bytes) -> None:
        if not self._client or not self._client.is_connected:
            await self._try_reconnect()
        if self._client and self._client.is_connected:
            try:
                await self._client.write_gatt_char(self._write_uuid, data, response=False)
            except Exception as exc:
                print(f"Error escribiendo BLE: {exc}")
                self._client = None  # fuerza reconexión en el próximo write

    async def _calibrate_gripper(self) -> None:
        print("Calibrando pinza...")
        await self._write(encoder_motor_run(GRIPPER_SLOT, -GRIPPER_CLOSE_SPEED))
        await asyncio.sleep(GRIPPER_CALIB_TIME)
        await self._write(encoder_motor_run(GRIPPER_SLOT, 0))
        await asyncio.sleep(0.2)
        await self._write(encoder_motor_set_pos_zero(GRIPPER_SLOT))
        self._grip_state = _GripState.IDLE
        self._grip_armed = True
        print("Pinza calibrada.")

    async def disconnect(self) -> None:
        await self.stop()
        await self._write(encoder_motor_run(ARM_SLOT, 0))
        await self._write(encoder_motor_run(GRIPPER_SLOT, 0))
        if self._client:
            await self._client.disconnect()

    # ── Orugas ────────────────────────────────────────────────────────────────

    async def apply_loco(self, gesture: LocoGesture) -> None:
        if gesture == self._last_loco:
            return  # sin cambio, no escribe
        self._last_loco = gesture
        fn = self._loco_dispatch.get(gesture)
        if fn:
            await fn()

    async def stop(self) -> None:
        await self._write(encoder_motor_run(TRACK_LEFT,  0))
        await self._write(encoder_motor_run(TRACK_RIGHT, 0))

    async def _forward(self):
        await self._write(encoder_motor_run(TRACK_LEFT,   TRACK_SPEED))
        await self._write(encoder_motor_run(TRACK_RIGHT, -TRACK_SPEED))

    async def _backward(self):
        await self._write(encoder_motor_run(TRACK_LEFT,  -TRACK_SPEED))
        await self._write(encoder_motor_run(TRACK_RIGHT,  TRACK_SPEED))

    async def _turn_left(self):
        await self._write(encoder_motor_run(TRACK_LEFT,  -TRACK_SPEED))
        await self._write(encoder_motor_run(TRACK_RIGHT, -TRACK_SPEED))

    async def _turn_right(self):
        await self._write(encoder_motor_run(TRACK_LEFT,   TRACK_SPEED))
        await self._write(encoder_motor_run(TRACK_RIGHT,  TRACK_SPEED))

    # ── Brazo robótico ────────────────────────────────────────────────────────

    async def _update_gripper(self) -> None:
        if self._grip_state == _GripState.IDLE:
            return
        elapsed = time.monotonic() - self._grip_start
        if self._grip_state == _GripState.OPENING and elapsed >= GRIPPER_OPEN_TIME:
            await self._write(encoder_motor_run(GRIPPER_SLOT, 0))
            await self._write(encoder_motor_set_pos_zero(GRIPPER_SLOT))
            self._grip_state = _GripState.IDLE
            self._last_arm   = None  # fuerza reenvío del siguiente gesto
            print("Pinza abierta.")
        elif self._grip_state == _GripState.CLOSING and elapsed >= GRIPPER_CLOSE_TIME:
            await self._write(encoder_motor_run(GRIPPER_SLOT, 0))
            await self._write(encoder_motor_set_pos_zero(GRIPPER_SLOT))
            self._grip_state = _GripState.IDLE
            self._grip_armed = True
            self._last_arm   = None
            print("Pinza cerrada — lista para abrir.")

    async def apply_arm(self, gesture: ArmGesture) -> None:
        await self._update_gripper()

        if gesture == self._last_arm:
            return  # sin cambio, no escribe
        self._last_arm = gesture
        active = self._grip_state != _GripState.IDLE

        if gesture == ArmGesture.SHOULDER_UP:
            await self._write(encoder_motor_run(ARM_SLOT, -ARM_SPEED))
            if not active:
                await self._write(encoder_motor_run(GRIPPER_SLOT, 0))

        elif gesture == ArmGesture.SHOULDER_DOWN:
            await self._write(encoder_motor_run(ARM_SLOT, ARM_SPEED))
            if not active:
                await self._write(encoder_motor_run(GRIPPER_SLOT, 0))

        elif gesture == ArmGesture.GRIP_CLOSE:
            await self._write(encoder_motor_run(ARM_SLOT, 0))
            if not self._grip_armed and self._grip_state == _GripState.IDLE:
                self._grip_state = _GripState.CLOSING
                self._grip_start = time.monotonic()
                await self._write(encoder_motor_run(GRIPPER_SLOT, -GRIPPER_CLOSE_SPEED))

        elif gesture == ArmGesture.GRIP_OPEN:
            await self._write(encoder_motor_run(ARM_SLOT, 0))
            if self._grip_armed and self._grip_state == _GripState.IDLE:
                self._grip_armed = False
                self._grip_state = _GripState.OPENING
                self._grip_start = time.monotonic()
                await self._write(encoder_motor_run(GRIPPER_SLOT, GRIPPER_OPEN_SPEED))
                print("Pinza abriendo...")

        else:
            await self._write(encoder_motor_run(ARM_SLOT, 0))
            if not active:
                await self._write(encoder_motor_run(GRIPPER_SLOT, 0))
