"""
Makeblock MegaPi serial protocol — packet builders.

Bytes extraídos del fuente oficial megapi_python3.py:
  encoderMotorRun:         [0xFF,0x55,0x07,0x00,0x02,0x3E,0x02,slot,speed_lo,speed_hi]
  encoderMotorSetPosZero:  [0xFF,0x55,0x05,0x00,0x02,0x3E,0x04,slot]
"""
import struct

_DEVICE_ENCODER = 0x3E  # 62


def encoder_motor_run(slot: int, speed: int) -> bytes:
    speed_bytes = struct.pack("<h", speed)
    return bytes([0xFF, 0x55, 0x07, 0x00, 0x02, _DEVICE_ENCODER, 0x02, slot]) + speed_bytes


def encoder_motor_set_pos_zero(slot: int) -> bytes:
    return bytes([0xFF, 0x55, 0x05, 0x00, 0x02, _DEVICE_ENCODER, 0x04, slot])
