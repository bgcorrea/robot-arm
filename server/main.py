"""
Railway relay server — bridge between browser clients and the local robot agent.

Endpoints
---------
WS  /ws/browser  — web UI clients (send commands, receive status)
WS  /ws/agent    — local agent running next to the robot (receive commands, send status)
GET /health      — liveness probe
GET /*           — static frontend (web/)
"""
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Robot Arm Relay")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class _Relay:
    def __init__(self) -> None:
        self.browsers: list[WebSocket] = []
        self.agents: list[WebSocket] = []

    @property
    def agent_online(self) -> bool:
        return bool(self.agents)

    async def _send(self, ws: WebSocket, payload: dict) -> bool:
        try:
            await ws.send_text(json.dumps(payload))
            return True
        except Exception:
            return False

    async def broadcast_browsers(self, payload: dict) -> None:
        dead = [ws for ws in self.browsers if not await self._send(ws, payload)]
        for ws in dead:
            self.browsers.remove(ws)

    async def send_to_agents(self, payload: dict) -> None:
        dead = [ws for ws in self.agents if not await self._send(ws, payload)]
        for ws in dead:
            self.agents.remove(ws)


relay = _Relay()


@app.websocket("/ws/browser")
async def browser_ws(ws: WebSocket) -> None:
    await ws.accept()
    relay.browsers.append(ws)
    await relay._send(ws, {"type": "agent_status", "online": relay.agent_online})
    try:
        while True:
            data = await ws.receive_text()
            await relay.send_to_agents(json.loads(data))
    except WebSocketDisconnect:
        relay.browsers.remove(ws)


@app.websocket("/ws/agent")
async def agent_ws(ws: WebSocket) -> None:
    await ws.accept()
    relay.agents.append(ws)
    await relay.broadcast_browsers({"type": "agent_status", "online": True})
    try:
        while True:
            data = await ws.receive_text()
            await relay.broadcast_browsers(json.loads(data))
    except WebSocketDisconnect:
        relay.agents.remove(ws)
        await relay.broadcast_browsers({"type": "agent_status", "online": False})


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "agents": len(relay.agents),
        "browsers": len(relay.browsers),
    }


# Static files must be mounted last (catch-all)
_WEB_DIR = Path(__file__).parent.parent / "web"
app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="static")
