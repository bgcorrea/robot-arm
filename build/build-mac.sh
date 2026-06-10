#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "Instalando PyInstaller..."
pip3 install pyinstaller

echo "Compilando robot-agent..."
pyinstaller --onefile \
  --name robot-agent \
  --collect-all bleak \
  --exclude-module megapi \
  --exclude-module cv2 \
  --exclude-module mediapipe \
  agent_ble_entry.py

echo ""
echo "Listo. El ejecutable está en dist/robot-agent"
echo "Compartilo junto con un archivo .env que tenga:"
echo "  RELAY_URL=wss://robot-arm-test.up.railway.app/ws/agent"
echo "  BLE_ADDRESS=70:3E:97:93:29:A5"
