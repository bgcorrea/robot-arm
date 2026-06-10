#!/usr/bin/env python3
"""
Entry point para el ejecutable empaquetado con PyInstaller.

El usuario hace doble click en robot-agent.exe / robot-agent.
En la primera ejecución pide la URL del relay y la guarda en .env.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Cuando corre como ejecutable PyInstaller, .env vive al lado del .exe
_BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def _setup() -> None:
    env_file = _BASE / ".env"

    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    if not os.environ.get("RELAY_URL"):
        print("=" * 50)
        print("  Primera configuración del agente Robot Arm")
        print("=" * 50)
        url = input("\nURL del relay (ej: wss://robot-arm-test.up.railway.app/ws/agent)\n> ").strip()
        if not url:
            print("URL requerida. Saliendo.")
            sys.exit(1)
        os.environ["RELAY_URL"] = url
        with open(env_file, "a", encoding="utf-8") as f:
            f.write(f"RELAY_URL={url}\n")
        print(f"\nGuardado en {env_file}. No se te pedirá de nuevo.\n")

    # Forzar modo BLE
    sys.argv = [sys.argv[0], "--ble"]


_setup()

from agent import main  # noqa: E402
main()
