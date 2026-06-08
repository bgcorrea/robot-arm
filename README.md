# robot-arm — Control por gestos de mano

Controla un robot **Makeblock Ultimate 2.0 + MegaPi** con gestos capturados por webcam usando MediaPipe.

- **Mano derecha** → locomoción (orugas)
- **Mano izquierda** → brazo robótico y pinza

---

## Requisitos de sistema

| Requisito | Versión mínima |
|-----------|---------------|
| Python | 3.10 |
| OS | Linux / WSL2 / macOS / Windows |
| Webcam | USB o integrada |
| Robot | Makeblock MegaPi (firmware estándar) |

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/bgcorrea/robot-arm
cd robot-pia

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate        # Linux / macOS / WSL2
# venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
```

---

## Conexión del robot

### Linux / WSL2

El puerto se detecta automáticamente buscando chips CH340/CH341. Si no se detecta, el fallback es `/dev/ttyUSB0`.

```bash
# Verificar que el dispositivo aparece
ls /dev/ttyUSB*

# Dar permisos al puerto (solo la primera vez)
sudo usermod -aG dialout $USER
# Cerrar sesión y volver a entrar para que surta efecto

# En WSL2: adjuntar la webcam Y el robot por USB
usbipd list                              # ver BUS IDs disponibles
usbipd attach --wsl --busid <busid>      # adjuntar robot
usbipd attach --wsl --busid <busid>      # adjuntar webcam (si es USB externa)
```

### macOS

El fallback es `/dev/tty.usbserial-1420`. Ajusta la constante `SERIAL_PORT` en `robot/controller.py` si tu adaptador tiene otro nombre.

### Windows

El fallback es `COM3`. Verifica el puerto real en el Administrador de dispositivos.

---

## Ejecutar

```bash
source venv/bin/activate   # si no está activo

python app.py
```

Al iniciar verás en consola:

```
Calibrando pinza...
Pinza calibrada.
Robot conectado en /dev/ttyUSB0
Cámara iniciada. Presiona 'q' para salir.
Frame #1 OK
```

> Si el robot no está conectado, la app arranca en **modo demo** (solo visión, sin enviar comandos).

Presiona `q` en la ventana de video para salir.

---

## Gestos

### Mano derecha — Locomoción

| Gesto | Acción |
|-------|--------|
| ✊ Puño (0 dedos) | Detener |
| ✋ Mano abierta (5 dedos) | Avanzar |
| ☝️ Solo índice | Girar izquierda |
| ✌️ Índice + medio | Girar derecha |
| Índice + medio + anular | Retroceder |

### Mano izquierda — Brazo

| Gesto | Acción |
|-------|--------|
| ✊ Puño (0 dedos) | Home / parar brazo |
| ☝️ Solo índice | Subir brazo |
| ✌️ Índice + medio | Bajar brazo |
| Índice + medio + anular | Extender codo |
| 🤙 Solo meñique | Retraer codo |
| Solo dedo medio | Rotar base izquierda |
| Solo dedo anular | Rotar base derecha |
| 🖖 4 dedos (sin pulgar) | Abrir pinza |
| 🤏 Pinch (pulgar + índice) | Cerrar pinza |

> La pinza opera con temporizador: al detectar el gesto se mueve durante el tiempo configurado y se detiene sola. Abrir requiere que la pinza esté cerrada (y viceversa).

---

## Estructura del proyecto

```
robot-pia/
├── app.py                  # Bucle principal: cámara → gestos → robot
├── gesture/
│   └── recognizer.py       # Detección de gestos con MediaPipe
├── robot/
│   └── controller.py       # Control del MegaPi por serial
└── requirements.txt
```

---

## Ajuste de parámetros

Los parámetros de movimiento están al inicio de `robot/controller.py`:

```python
TRACK_SPEED         = 150   # Velocidad orugas (-255..255)
ARM_SPEED           = 100   # Velocidad motor de brazo
GRIPPER_OPEN_TIME   = 1.5   # Segundos que tarda en abrir la pinza
GRIPPER_CLOSE_TIME  = 0.6   # Segundos que tarda en cerrar la pinza
```

---

## Solución de problemas

**`ERROR: no se pudo abrir la cámara`**
- En WSL2: adjunta la webcam con `usbipd attach --wsl --busid <id>`.
- Verifica con `ls /dev/video*` que el dispositivo existe.

**`Robot no disponible — modo demo sin hardware`**
- Verifica el puerto: `ls /dev/ttyUSB*` o `ls /dev/ttyACM*`.
- Comprueba permisos: `sudo chmod 666 /dev/ttyUSB0` (temporal) o añade tu usuario al grupo `dialout`.

**La pinza no responde**
- La calibración ocurre automáticamente al conectar; espera ~1 segundo tras el mensaje `Calibrando pinza...`.
- El gesto de apertura solo funciona si la pinza está en estado cerrado (y viceversa).
