#!/bin/bash
# Agente local — Mac o Linux
# Requiere Python 3.10+ y pip install -r requirements-windows.txt

cd "$(dirname "$0")"

if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python 3 no encontrado. Instalalo desde https://python3.org"
  exit 1
fi

if ! python3 -c "import bleak" &>/dev/null 2>&1; then
  echo "Instalando dependencias..."
  pip3 install -r requirements-windows.txt
fi

python3 agent.py --ble
