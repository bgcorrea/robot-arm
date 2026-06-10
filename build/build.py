#!/usr/bin/env python3
"""
Genera el ejecutable robot-agent para la plataforma actual.

Windows:  python build/build.py
Mac/Linux: python3 build/build.py

Resultado: dist/robot-agent.exe  (Windows)
           dist/robot-agent      (Mac/Linux)
"""
import subprocess
import sys
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "agent_ble_entry.py"
DIST  = ROOT / "dist"
WORK  = ROOT / "build" / "_work"
SPEC  = ROOT / "build"

def run(*args, **kwargs):
    result = subprocess.run(list(args), **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)

print("Instalando dependencias...")
run(sys.executable, "-m", "pip", "install", "bleak", "websockets", "pyinstaller", "--quiet")

extra = ["--collect-all", "winrt"] if sys.platform == "win32" else []

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--name", "robot-agent",
    "--collect-all", "bleak",
    *extra,
    "--exclude-module", "megapi",
    "--exclude-module", "cv2",
    "--exclude-module", "mediapipe",
    "--distpath", str(DIST),
    "--workpath", str(WORK),
    "--specpath", str(SPEC),
    str(ENTRY),
]

print(f"Compilando para {sys.platform}...")
run(*cmd)

exe = DIST / ("robot-agent.exe" if sys.platform == "win32" else "robot-agent")
print("\n" + "=" * 50)
print(f"Listo: {exe}")
print("\nCompartí ese archivo junto con un .env que tenga:")
print("  RELAY_URL=wss://robot-arm-test.up.railway.app/ws/agent")
print("  BLE_ADDRESS=70:3E:97:93:29:A5")
