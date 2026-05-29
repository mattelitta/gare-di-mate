import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
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


async def broadcast_loop():
    """Aggiorna la cache ogni secondo per le gare in corso."""
    while True:
        await asyncio.sleep(1)
        db = SessionLocal()
        try:
            from models import Competition
            from database import load_comp_full
            from engine import compute_state
            from cache import state_cache
            comp_ids = [
                c.id for c in db.query(Competition.id)
                .filter(Competition.status == "running").all()
            ]
            for comp_id in comp_ids:
                comp = load_comp_full(comp_id, db)
                if comp:
                    prob_states, team_scores = compute_state(comp)
                    state_cache.set(comp_id, (prob_states, team_scores))
        finally:
            db.close()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
