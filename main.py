import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import init_db, SessionLocal
from routers import admin, inserimento, regia, display


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(broadcast_loop())
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(admin.router, prefix="/admin")
app.include_router(inserimento.router, prefix="/inserimento")
app.include_router(regia.router, prefix="/regia")
app.include_router(display.router, prefix="/display")


# --- WebSocket connection manager ---
class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, channel: str):
        await ws.accept()
        self._connections.setdefault(channel, []).append(ws)

    def disconnect(self, ws: WebSocket, channel: str):
        if channel in self._connections:
            self._connections[channel] = [c for c in self._connections[channel] if c != ws]

    async def broadcast(self, channel: str, data: dict):
        msg = json.dumps(data)
        dead = []
        for ws in self._connections.get(channel, []):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    async def broadcast_all(self, data: dict):
        for channel in list(self._connections.keys()):
            await self.broadcast(channel, data)


manager = ConnectionManager()


@app.websocket("/ws/{competition_id}/{channel}")
async def websocket_endpoint(ws: WebSocket, competition_id: int, channel: str):
    key = f"{competition_id}:{channel}"
    await manager.connect(ws, key)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(ws, key)


async def broadcast_loop():
    """Push state updates to all connected clients every second."""
    while True:
        await asyncio.sleep(1)
        db = SessionLocal()
        try:
            from models import Competition
            comps = db.query(Competition).filter(Competition.status == "running").all()
            for comp in comps:
                await manager.broadcast(f"{comp.id}:state", {"type": "tick", "comp_id": comp.id})
        finally:
            db.close()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
