import asyncio
from contextlib import asynccontextmanager
from urllib.parse import quote

import uvicorn
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import auth
from database import get_db, init_db, SessionLocal
from paths import STATIC_DIR, TEMPLATES_DIR
from routers import admin, inserimento, regia, display


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(broadcast_loop())
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

app.include_router(admin.router, prefix="/admin")
app.include_router(inserimento.router, prefix="/inserimento")
app.include_router(regia.router, prefix="/regia")
app.include_router(display.router, prefix="/display")


def _remote_allowed(path: str) -> bool:
    return (path in ("/inserimento", "/display", "/esci")
            or path.startswith("/inserimento/") or path.startswith("/display/"))


@app.middleware("http")
async def access_gate(request: Request, call_next):
    """Dispositivi non locali: password di accesso obbligatoria, poi solo Inserimento e Display."""
    local = auth.is_local(request)
    request.state.is_local = local
    path = request.url.path
    if local or path == "/accesso" or path.startswith("/static/"):
        return await call_next(request)
    if not auth.has_valid_cookie(request):
        if path.startswith("/display/api/"):
            return JSONResponse({"detail": "Accesso richiesto"}, status_code=401)
        target = path + (f"?{request.url.query}" if request.url.query else "")
        nxt = f"?next={quote(target)}" if request.method == "GET" and path != "/" else ""
        return RedirectResponse(f"/accesso{nxt}", status_code=303)
    if _remote_allowed(path):
        return await call_next(request)
    return RedirectResponse("/inserimento/", status_code=303)


def _safe_next(nxt: str) -> str:
    if nxt.startswith("/") and not nxt.startswith("//") and not nxt.startswith("/\\"):
        return nxt
    return "/"


@app.get("/accesso", response_class=HTMLResponse)
async def accesso_form(request: Request, next: str = "/", db: Session = Depends(get_db)):
    return templates.TemplateResponse("accesso.html", {
        "request": request, "next": _safe_next(next), "configured": auth.password_is_set(db),
    })


@app.post("/accesso")
async def accesso(
    request: Request, password: str = Form(""), next: str = Form("/"), db: Session = Depends(get_db)
):
    nxt = _safe_next(next)
    if not auth.check_password(db, password):
        await asyncio.sleep(1)
        return templates.TemplateResponse("accesso.html", {
            "request": request, "next": nxt, "configured": auth.password_is_set(db),
            "error": "Password errata",
        }, status_code=401)
    response = RedirectResponse(nxt, status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME, auth.expected_token(),
        max_age=auth.COOKIE_MAX_AGE, httponly=True, samesite="lax",
    )
    return response


@app.get("/esci")
async def esci():
    response = RedirectResponse("/accesso", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME)
    return response


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
