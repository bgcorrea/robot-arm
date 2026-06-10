#!/usr/bin/env python3
"""
Ejecutar en Windows (NO en WSL2) para descubrir los servicios BLE del robot.

    pip install bleak
    python scan_ble.py
"""
import asyncio
from bleak import BleakScanner, BleakClient


async def main() -> None:
    print("Escaneando dispositivos BLE... (6 segundos)\n")
    devices = await BleakScanner.discover(timeout=6.0)

    makeblock = None
    for d in sorted(devices, key=lambda x: x.name or ""):
        print(f"  {d.address}  {d.name or '(sin nombre)'}")
        if d.name and "makeblock" in d.name.lower():
            makeblock = d

    if not makeblock:
        print("\nNo se encontró ningún dispositivo Makeblock.")
        print("Asegúrate de que el robot esté encendido y la luz azul parpadee.")
        return

    print(f"\nConectando a {makeblock.name} ({makeblock.address})...")
    async with BleakClient(makeblock.address) as client:
        print(f"Conectado. MTU={client.mtu_size}\n")
        print("Servicios y características:\n")

        write_chars = []
        for service in client.services:
            print(f"Service: {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  Char:  {char.uuid}  [{props}]  — {char.description}")
                if "write" in char.properties or "write-without-response" in char.properties:
                    write_chars.append(char.uuid)

        if write_chars:
            print("\n" + "=" * 60)
            print("Características con permiso de escritura (candidatas a BLE_WRITE_UUID):")
            for u in write_chars:
                print(f"  {u}")
            print("\nCopia el UUID correcto y luego corre el agente con:")
            print(f"  set BLE_WRITE_UUID={write_chars[0]}")
            print(f"  python agent.py --ble")
        else:
            print("\nNinguna característica con permiso de escritura encontrada.")


if __name__ == "__main__":
    asyncio.run(main())
