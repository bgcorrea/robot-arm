@echo off
cd /d "%~dp0\.."

echo Instalando PyInstaller...
pip install pyinstaller

echo Compilando robot-agent.exe...
pyinstaller --onefile ^
  --name robot-agent ^
  --collect-all bleak ^
  --collect-all winrt ^
  --exclude-module megapi ^
  --exclude-module cv2 ^
  --exclude-module mediapipe ^
  agent_ble_entry.py

echo.
echo Listo. El ejecutable esta en dist\robot-agent.exe
echo Compartilo junto con un archivo .env que tenga:
echo   RELAY_URL=wss://robot-arm-test.up.railway.app/ws/agent
echo   BLE_ADDRESS=70:3E:97:93:29:A5
pause
