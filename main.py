import asyncio
import ipaddress
import logging
import socket
from contextlib import asynccontextmanager
from urllib.parse import quote, urlsplit

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import auth
import tempo
from database import get_db, init_db, SessionLocal
from paths import STATIC_DIR, TEMPLATES_DIR
from routers import admin, inserimento, regia, display

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Prima del ciclo (che riscrive il battito): le gare rimaste in corso riprendono dal minuto raggiunto.
    db = SessionLocal()
    try:
        recovered = tempo.recover_after_restart(db)
        if recovered:
            log.warning("Riprese %s gare rimaste in corso alla chiusura del programma", recovered)
    finally:
        db.close()
    asyncio.create_task(broadcast_loop())
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

app.include_router(admin.router, prefix="/admin")
app.include_router(inserimento.router, prefix="/inserimento")
app.include_router(regia.router, prefix="/regia")
app.include_router(display.router, prefix="/display")


@app.middleware("http")
async def access_gate(request: Request, call_next):
    """Dispositivi non locali: accesso con la password (una sessione per dispositivo), poi solo
    le aree permesse dal ruolo della sessione (vedi auth.session_allows)."""
    local = auth.is_local(request)
    request.state.is_local = local
    request.state.session = None
    path = request.url.path
    if local or path == "/accesso" or path.startswith("/static/"):
        return await call_next(request)
    session = auth.get_session(request)
    if session is None:
        if path.startswith("/display/api/") or path.endswith("/stato"):
            return JSONResponse({"detail": "Accesso richiesto"}, status_code=401)
        target = path + (f"?{request.url.query}" if request.url.query else "")
        nxt = f"?next={quote(target)}" if request.method == "GET" and path not in ("/", "/esci") else ""
        return RedirectResponse(f"/accesso{nxt}", status_code=303)
    request.state.session = session
    if path == "/esci":
        return await call_next(request)
    permission = auth.permission_for_path(path)
    if permission is not None and auth.session_allows(session, permission, path):
        return await call_next(request)
    return RedirectResponse(auth.home_for(session), status_code=303)


@app.middleware("http")
async def device_cookie(request: Request, call_next):
    """Assegna a ogni browser un identificativo stabile (per filtrare le sue consegne)."""
    device = request.cookies.get(auth.DEVICE_COOKIE, "")
    is_new = not auth.valid_device_id(device)
    if is_new:
        device = auth.new_device_id()
    request.state.device_id = device
    response = await call_next(request)
    if is_new:
        response.set_cookie(auth.DEVICE_COOKIE, device, max_age=auth.DEVICE_COOKIE_MAX_AGE,
                            httponly=True, samesite="strict", secure=request.url.scheme == "https")
    return response


def _allowed_host(hostname: str) -> bool:
    """Nomi con cui si può raggiungere il server: un indirizzo IP, localhost o il nome del computer.
    Rifiutare gli altri nomi blocca il "DNS rebinding" (un sito che si spaccia per il server)."""
    if not hostname:
        return False
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        return True
    except ValueError:
        pass
    name = socket.gethostname().lower()
    return hostname.lower() in ("localhost", name, f"{name}.local")


_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",                                  # nessuna pagina dentro un'altra (clickjacking)
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}


@app.middleware("http")
async def security(request: Request, call_next):
    """Primo controllo di ogni richiesta (è il middleware più esterno).

    - Gli altri dispositivi usano solo HTTPS: sulla porta HTTP ricevono soltanto il rimando
      all'indirizzo HTTPS (senza contenuti, e i cookie di accesso lì non vengono inviati).
    - Nome del server ammesso solo se è un indirizzo IP, localhost o il nome del computer.
    - Moduli inviati da un'altra origine rifiutati (protezione CSRF, oltre ai cookie SameSite).
    - Intestazioni di sicurezza e niente cache per pagine e dati.
    """
    url = request.url
    if not _allowed_host(url.hostname or ""):
        return PlainTextResponse("Indirizzo non valido", status_code=400)
    if url.scheme == "http" and not auth.is_local(request):
        https_port = getattr(request.app.state, "https_port", None)
        if https_port is None:
            return PlainTextResponse("Collegarsi con l'indirizzo HTTPS mostrato dal programma.", status_code=403)
        host = url.hostname if ":" not in url.hostname else f"[{url.hostname}]"
        target = f"https://{host}:{https_port}{url.path}" + (f"?{url.query}" if url.query else "")
        return RedirectResponse(target, status_code=301 if request.method == "GET" else 307)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            o = urlsplit(origin)
            if origin != "null" and (o.scheme, o.netloc) != (url.scheme, url.netloc):
                auth.events.add(f"{auth.client_ip(request)}: richiesta da un'altra origine rifiutata ({o.netloc})")
                return PlainTextResponse("Richiesta da un'altra origine rifiutata", status_code=403)
            if origin == "null":
                return PlainTextResponse("Richiesta da un'altra origine rifiutata", status_code=403)
    response = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if not url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


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
    ip = auth.client_ip(request)

    def rifiuta(errore: str, status: int):
        return templates.TemplateResponse("accesso.html", {
            "request": request, "next": nxt, "configured": auth.password_is_set(db), "error": errore,
        }, status_code=status)

    attesa = auth.limiter.wait_seconds(ip)
    if attesa:
        return rifiuta(f"Troppi tentativi errati: riprovare tra {attesa} secondi.", 429)
    if request.url.scheme != "https":  # solo il computer server arriva qui senza HTTPS, e non ne ha bisogno
        return RedirectResponse(nxt, status_code=303)
    if not auth.check_password(db, password):
        auth.limiter.failure(ip)
        auth.events.add(f"{ip}: password errata")
        await asyncio.sleep(1)
        return rifiuta("Password errata", 401)
    auth.limiter.success(ip)
    token = auth.create_session(db, request)
    auth.events.add(f"{ip}: accesso riuscito")
    response = RedirectResponse(nxt, status_code=303)
    response.set_cookie(auth.COOKIE_NAME, token, max_age=auth.COOKIE_MAX_AGE,
                        httponly=True, secure=True, samesite="strict", path="/")
    return response


@app.get("/esci")
async def esci(request: Request):
    auth.logout(request)
    response = RedirectResponse("/accesso", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
    return response


async def broadcast_loop():
    """Ogni secondo: battito del server e aggiornamento della cache per le gare in corso.

    Non deve mai fermarsi: un battito fermo con il server acceso verrebbe scambiato
    per una chiusura al riavvio successivo.
    """
    from models import Competition
    from database import load_comp_full
    from engine import compute_state
    from cache import state_cache
    while True:
        await asyncio.sleep(1)
        db = SessionLocal()
        try:
            tempo.heartbeat(db)
            for comp_id in tempo.end_expired(db):  # allo scadere del tempo la gara termina da sola
                state_cache.invalidate(comp_id)
                log.info("Gara %s terminata allo scadere del tempo", comp_id)
            comp_ids = [
                c.id for c in db.query(Competition.id)
                .filter(Competition.status == "running").all()
            ]
            for comp_id in comp_ids:
                comp = load_comp_full(comp_id, db)
                if comp:
                    prob_states, team_scores = compute_state(comp)
                    state_cache.set(comp_id, (prob_states, team_scores))
        except Exception:
            log.exception("Errore nel ciclo di aggiornamento (si riprova tra un secondo)")
        finally:
            db.close()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    import server
    server.run(server.create_servers(app))
