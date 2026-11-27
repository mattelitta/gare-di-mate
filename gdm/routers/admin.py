import json
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from gdm import auth
from gdm import formato
from gdm import firma
from gdm import tempo
from gdm.cache import state_cache
from gdm.database import get_db, load_comp_full
from gdm.models import Competition, Display, JollyChoice, Penalty, Problem, Submission, Team, TimeAdjustment
from gdm.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


formato.registra(templates)
templates.env.globals["avanzamento_massimo"] = tempo.max_advance


def _secondi(minutes: str, seconds: str) -> int:
    """Minuti e secondi dai form; campi vuoti = 0. ValueError con messaggio se non validi."""
    try:
        m = int(minutes or 0)
        s = int(seconds or 0)
    except ValueError:
        raise ValueError("Minuti e secondi devono essere numeri interi.")
    if m < 0 or s < 0:
        raise ValueError("Minuti e secondi non possono essere negativi.")
    return m * 60 + s


def _torna_al_tempo(comp_id: int, errore: str | None = None) -> RedirectResponse:
    """Torna al riquadro del tempo nella pagina della gara, con l'eventuale errore da mostrare."""
    query = f"?errore={quote(errore)}" if errore else ""
    return RedirectResponse(f"/admin/gara/{comp_id}{query}#tempo", status_code=303)


def _se_archiviata(comp_id: int, db: Session) -> RedirectResponse | None:
    """Una gara archiviata è in sola lettura: parametri, squadre, problemi, bonus e classifica finale
    non si toccano finché non la si de-archivia."""
    comp = db.get(Competition, comp_id)
    if comp is not None and comp.is_archived():
        return _torna_alla_gara(comp_id, errore="La gara è archiviata: per modificarla bisogna prima de-archiviarla.")
    return None


def require_localhost(request: Request):
    if not auth.is_local(request):
        raise HTTPException(status_code=403, detail="Admin accessibile solo in locale")


def _descrivi_browser(ua: str) -> str:
    """Descrizione breve del dispositivo dal suo user-agent (solo per riconoscerlo nell'elenco)."""
    ua_l = ua.lower()
    sistema = next((nome for chiave, nome in [("ipad", "iPad"), ("iphone", "iPhone"), ("android", "Android"),
                                              ("windows", "Windows"), ("mac os", "Mac"), ("cros", "ChromeOS"),
                                              ("linux", "Linux")] if chiave in ua_l), "")
    browser = next((nome for chiave, nome in [("edg/", "Edge"), ("firefox", "Firefox"), ("samsungbrowser", "Samsung Internet"),
                                              ("chrome", "Chrome"), ("safari", "Safari")] if chiave in ua_l), "")
    if not (sistema or browser):
        return ua[:40] or "sconosciuto"
    return f"{browser or 'Browser'}{' su ' + sistema if sistema else ''}"


def _torna_alla_home(esito: str | None = None, errore: str | None = None) -> RedirectResponse:
    query = f"?esito={quote(esito)}" if esito else (f"?errore={quote(errore)}" if errore else "")
    return RedirectResponse(f"/admin/{query}#sicurezza" if query else "/admin/", status_code=303)


# --- Competition list ---
@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request, db: Session = Depends(get_db)):
    require_localhost(request)
    from gdm import tls
    from gdm.models import AccessSession
    tutte = db.query(Competition).order_by(Competition.created_at.desc()).all()
    comps = [c for c in tutte if not c.is_archived()]  # le archiviate stanno nella pagina dell'archivio
    sessioni = db.query(AccessSession).order_by(AccessSession.last_seen.desc()).all()
    return templates.TemplateResponse("admin/home.html", {
        "request": request, "comps": comps, "archiviate": len(tutte) - len(comps), "local_ip": auth.get_local_ip(),
        "https_port": getattr(request.app.state, "https_port", None) or 8443,
        "impronta": tls.fingerprint(),
        "access_password_set": auth.password_is_set(db),
        "min_password": auth.MIN_PASSWORD,
        "sessioni": [{"s": s, "browser": _descrivi_browser(s.user_agent),
                      "ruolo": auth.ROLE_LABELS.get(s.role, s.role)} for s in sessioni],
        "eventi": auth.events.recent(15),
        "blocchi": auth.limiter.active_locks(),
        "firma": firma.elenco(db, sessioni=True), "firma_url": "/admin/api/firma?sessioni=1",
    })


@router.get("/api/firma")
async def admin_api_firma(request: Request, sessioni: int = 0, db: Session = Depends(get_db)):
    """Firma dell'elenco delle gare, per l'aggiornamento automatico delle pagine (vedi firma.py)."""
    require_localhost(request)
    return PlainTextResponse(firma.elenco(db, sessioni=bool(sessioni)))


@router.get("/api/gara/{comp_id}/firma")
async def admin_api_firma_gara(request: Request, comp_id: int, regia: int = 0, db: Session = Depends(get_db)):
    """Firma dello stato di una gara (pagina Admin, o Regia con regia=1)."""
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    return PlainTextResponse(firma.gara(comp, regia=bool(regia)))


@router.get("/archivio", response_class=HTMLResponse)
async def admin_archivio_pagina(request: Request, db: Session = Depends(get_db)):
    """Gare archiviate (linkate in fondo alla home Admin)."""
    require_localhost(request)
    comps = [c for c in db.query(Competition).order_by(Competition.created_at.desc()) if c.is_archived()]
    return templates.TemplateResponse("admin/archivio.html", {
        "request": request, "comps": comps,
        "firma": firma.elenco(db), "firma_url": "/admin/api/firma",
    })


@router.post("/password-accesso")
async def admin_password_accesso(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    require_localhost(request)
    if len(password) < auth.MIN_PASSWORD:
        return _torna_alla_home(errore=f"La password deve avere almeno {auth.MIN_PASSWORD} caratteri.")
    gia = auth.password_is_set(db)
    auth.set_password(db, password)
    return _torna_alla_home(esito="Password cambiata: tutti i dispositivi devono rifare l'accesso." if gia
                            else "Password impostata.")


@router.post("/dispositivi/{session_id}/scollega")
async def admin_scollega(request: Request, session_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    from gdm.models import AccessSession
    s = db.get(AccessSession, session_id)
    if s is None:
        return _torna_alla_home(errore="Dispositivo già scollegato.")
    descr = f"{s.ip} ({_descrivi_browser(s.user_agent)})"
    auth.revoke_session(db, session_id)
    auth.events.add(f"{descr}: scollegato dall'Admin")
    return _torna_alla_home(esito=f"Dispositivo {descr} scollegato: per rientrare deve rifare l'accesso.")


@router.post("/dispositivi/scollega-tutti")
async def admin_scollega_tutti(request: Request, db: Session = Depends(get_db)):
    require_localhost(request)
    auth.revoke_all(db)
    auth.events.add("Tutti i dispositivi scollegati dall'Admin")
    return _torna_alla_home(esito="Tutti i dispositivi sono stati scollegati.")


@router.post("/sicurezza/sblocca")
async def admin_sblocca(request: Request):
    require_localhost(request)
    auth.limiter.reset()
    auth.events.add("Blocchi dei tentativi di accesso tolti dall'Admin")
    return _torna_alla_home(esito="Blocchi tolti: tutti possono riprovare ad accedere.")


# --- Create competition ---
@router.get("/crea", response_class=HTMLResponse)
async def admin_crea_form(request: Request):
    require_localhost(request)
    return templates.TemplateResponse("admin/crea.html", {"request": request})


def _qualificate(qualificazione: str, num_qualified: str) -> int:
    """Squadre qualificate: 0 se la gara non è a qualificazione, altrimenti almeno 1."""
    if not qualificazione:
        return 0
    valore = num_qualified.strip()
    if not valore.isdigit() or int(valore) < 1:
        raise HTTPException(status_code=400, detail="Gara a qualificazione: indicare quante squadre si qualificano (almeno 1)")
    return int(valore)


def _minuti_domande(valore: str, durata: int) -> int | None:
    """Tempo per le domande sul testo: vuoto = non previsto, altrimenti da 1 alla durata della gara."""
    valore = valore.strip()
    if not valore:
        return None
    if not valore.isdigit() or not 1 <= int(valore) <= durata:
        raise HTTPException(status_code=400,
                            detail=f"Tempo per le domande sul testo: da 1 a {durata} minuti, oppure vuoto se non previsto")
    return int(valore)


def _punteggio_iniziale(valore: str) -> int | None:
    """Campo facoltativo: vuoto = automatico (10 × numero di problemi)."""
    valore = valore.strip()
    if not valore:
        return None
    try:
        return int(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail="Il punteggio iniziale deve essere un numero intero (o vuoto)")


@router.post("/crea")
async def admin_crea(
    request: Request,
    name: str = Form(...),
    date: str = Form(""),
    initial_value: int = Form(40),
    starting_score: str = Form(""),
    n: int = Form(2),
    k: int = Form(1),
    first_delivery_bonuses: str = Form("20,15,10,5,3"),
    full_bonuses: str = Form("50,30,20,15,10"),
    duration_minutes: int = Form(90),
    jolly_time_minutes: int = Form(30),
    questions_minutes: str = Form(""),
    threshold_minute: int = Form(...),
    blackout_minute: int = Form(...),
    qualificazione: str = Form(""),
    num_qualified: str = Form(""),
    final_reveal_count: int = Form(3),
    display_theme: str = Form("light"),
    jolly_reveal: str = Form("immediate"),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    try:
        fd = [int(x.strip()) for x in first_delivery_bonuses.split(",") if x.strip()]
        fb = [int(x.strip()) for x in full_bonuses.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato bonus non valido")
    if threshold_minute > duration_minutes:
        raise HTTPException(status_code=400, detail=f"Minuto soglia ({threshold_minute}) superiore alla durata ({duration_minutes} min)")
    if blackout_minute > duration_minutes:
        raise HTTPException(status_code=400, detail=f"Minuto oscuramento ({blackout_minute}) superiore alla durata ({duration_minutes} min)")

    comp = Competition(
        name=name,
        date=date.strip(),
        initial_value=initial_value,
        starting_score=_punteggio_iniziale(starting_score),
        n=n,
        k=k,
        first_delivery_bonuses_json=json.dumps(fd),
        full_bonuses_json=json.dumps(fb),
        duration_minutes=duration_minutes,
        jolly_time_minutes=jolly_time_minutes,
        questions_minutes=_minuti_domande(questions_minutes, duration_minutes),
        threshold_minute=threshold_minute,
        blackout_minute=blackout_minute,
        num_qualified=_qualificate(qualificazione, num_qualified),
        final_reveal_count=final_reveal_count,
        display_theme=display_theme if display_theme in ('dark', 'light') else 'dark',
        jolly_reveal=jolly_reveal if jolly_reveal in ('immediate', 'deadline') else 'immediate',
        status="created",
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return RedirectResponse(f"/admin/gara/{comp.id}/modifica#squadre", status_code=303)


# --- Competition detail / management ---
@router.get("/gara/{comp_id}", response_class=HTMLResponse)
async def admin_gara(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/gara.html", {
        "request": request, "comp": comp,
        "firma": firma.gara(comp), "firma_url": f"/admin/api/gara/{comp_id}/firma",
    })


# --- Edit competition ---
@router.get("/gara/{comp_id}/modifica", response_class=HTMLResponse)
async def admin_modifica_form(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/modifica.html", {"request": request, "comp": comp})


@router.post("/gara/{comp_id}/modifica")
async def admin_modifica(
    request: Request,
    comp_id: int,
    name: str = Form(...),
    date: str = Form(""),
    initial_value: int = Form(40),
    starting_score: str = Form(""),
    n: int = Form(2),
    k: int = Form(1),
    first_delivery_bonuses: str = Form("20,15,10,5,3"),
    full_bonuses: str = Form("50,30,20,15,10"),
    duration_minutes: int = Form(90),
    jolly_time_minutes: int = Form(30),
    questions_minutes: str = Form(""),
    threshold_minute: int = Form(...),
    blackout_minute: int = Form(...),
    qualificazione: str = Form(""),
    num_qualified: str = Form(""),
    final_reveal_count: int = Form(3),
    display_theme: str = Form("dark"),
    jolly_reveal: str = Form("immediate"),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    try:
        fd = [int(x.strip()) for x in first_delivery_bonuses.split(",") if x.strip()]
        fb = [int(x.strip()) for x in full_bonuses.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato bonus non valido")
    if threshold_minute > duration_minutes:
        raise HTTPException(status_code=400, detail=f"Minuto soglia ({threshold_minute}) superiore alla durata ({duration_minutes} min)")
    if blackout_minute > duration_minutes:
        raise HTTPException(status_code=400, detail=f"Minuto oscuramento ({blackout_minute}) superiore alla durata ({duration_minutes} min)")
    comp.name = name
    comp.date = date.strip()
    comp.initial_value = initial_value
    comp.starting_score = _punteggio_iniziale(starting_score)
    comp.n = n
    comp.k = k
    comp.first_delivery_bonuses_json = json.dumps(fd)
    comp.full_bonuses_json = json.dumps(fb)
    comp.duration_minutes = duration_minutes
    comp.jolly_time_minutes = jolly_time_minutes
    comp.questions_minutes = _minuti_domande(questions_minutes, duration_minutes)
    comp.threshold_minute = threshold_minute
    comp.blackout_minute = blackout_minute
    comp.num_qualified = _qualificate(qualificazione, num_qualified)
    comp.final_reveal_count = final_reveal_count
    comp.display_theme = display_theme if display_theme in ('dark', 'light') else 'dark'
    comp.jolly_reveal = jolly_reveal if jolly_reveal in ('immediate', 'deadline') else 'immediate'
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


# --- Delete competition ---
@router.post("/gara/{comp_id}/elimina")
async def admin_elimina(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    db.delete(comp)
    db.commit()
    return RedirectResponse("/admin/", status_code=303)


# --- Copy competition ---
@router.post("/gara/{comp_id}/copia")
async def admin_copia(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    orig = db.get(Competition, comp_id)
    if not orig:
        raise HTTPException(status_code=404)
    new_comp = Competition(
        name=f"{orig.name} (copia)",
        date=orig.date,
        initial_value=orig.initial_value,
        starting_score=orig.starting_score,
        n=orig.n,
        k=orig.k,
        first_delivery_bonuses_json=orig.first_delivery_bonuses_json,
        full_bonuses_json=orig.full_bonuses_json,
        duration_minutes=orig.duration_minutes,
        jolly_time_minutes=orig.jolly_time_minutes,
        questions_minutes=orig.questions_minutes,
        threshold_minute=orig.threshold_minute,
        blackout_minute=orig.blackout_minute,
        num_qualified=orig.num_qualified,
        final_reveal_count=orig.final_reveal_count,
        display_theme=orig.display_theme,
        jolly_reveal=orig.jolly_reveal,
        status="created",
    )
    db.add(new_comp)
    db.flush()
    for t in orig.teams:
        db.add(Team(competition_id=new_comp.id, number=t.number, name=t.name, city=t.city, is_guest=t.is_guest))
    for p in orig.problems:
        db.add(Problem(competition_id=new_comp.id, number=p.number, name=p.name, answer=p.answer))
    db.commit()
    return RedirectResponse(f"/admin/gara/{new_comp.id}", status_code=303)


# --- State management ---
@router.post("/gara/{comp_id}/avvia")
async def admin_avvia(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp or comp.status not in ("created", "paused"):
        raise HTTPException(status_code=400)
    now = datetime.utcnow()
    if comp.status == "created":
        comp.started_at = now
        comp.total_paused_seconds = 0.0
        comp.time_offset_seconds = 0.0
    else:
        # resume from pause
        paused_duration = (now - comp.paused_at).total_seconds()
        comp.total_paused_seconds += paused_duration
        comp.paused_at = None
    comp.status = "running"
    comp.last_alive_at = now
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


@router.post("/gara/{comp_id}/avanza-tempo")
async def admin_avanza_tempo(
    request: Request, comp_id: int, minutes: str = Form(""), seconds: str = Form(""),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.status not in ("running", "paused"):
        return _torna_al_tempo(comp_id, "Il tempo si può avanzare solo a gara in corso o in pausa.")
    try:
        delta = _secondi(minutes, seconds)
    except ValueError as e:
        return _torna_al_tempo(comp_id, str(e))
    if delta <= 0:
        return _torna_al_tempo(comp_id, "Indicare di quanti minuti e secondi avanzare.")
    tempo.advance(comp, delta)
    db.commit()
    state_cache.invalidate(comp_id)
    return _torna_al_tempo(comp_id)


@router.post("/gara/{comp_id}/ripresa")
async def admin_ripresa(
    request: Request, comp_id: int, azione: str = Form(...),
    minutes: str = Form(""), seconds: str = Form(""), torna: str = Form("gara"),
    db: Session = Depends(get_db),
):
    """Risposta al popup mostrato dopo una chiusura del programma a gara in corso."""
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if azione == "avanza" and comp.status in ("running", "paused"):
        try:
            tempo.advance(comp, _secondi(minutes, seconds), reason="ripresa")
        except ValueError as e:
            return _torna_al_tempo(comp_id, str(e))  # il popup resta: si può riprovare
    tempo.clear_recovery(comp)
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse("/admin/" if torna == "home" else f"/admin/gara/{comp_id}", status_code=303)


def _get_adjustment(db: Session, comp_id: int, adj_id: int) -> tuple[Competition, TimeAdjustment]:
    comp = db.get(Competition, comp_id)
    adj = db.get(TimeAdjustment, adj_id)
    if not comp or not adj or adj.competition_id != comp_id:
        raise HTTPException(status_code=404)
    return comp, adj


@router.post("/gara/{comp_id}/avanzamenti/{adj_id}/modifica")
async def admin_modifica_avanzamento(
    request: Request, comp_id: int, adj_id: int, minutes: str = Form(""), seconds: str = Form(""),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    comp, adj = _get_adjustment(db, comp_id, adj_id)
    try:
        new_seconds = _secondi(minutes, seconds)
        if new_seconds <= 0:
            raise ValueError("Per annullare un avanzamento usare \"Elimina\".")
        tempo.change_adjustment(comp, adj, new_seconds)
    except ValueError as e:
        return _torna_al_tempo(comp_id, str(e))
    db.commit()
    state_cache.invalidate(comp_id)
    return _torna_al_tempo(comp_id)


@router.post("/gara/{comp_id}/avanzamenti/{adj_id}/elimina")
async def admin_elimina_avanzamento(
    request: Request, comp_id: int, adj_id: int, db: Session = Depends(get_db),
):
    require_localhost(request)
    comp, adj = _get_adjustment(db, comp_id, adj_id)
    try:
        tempo.remove_adjustment(comp, adj)
    except ValueError as e:
        return _torna_al_tempo(comp_id, str(e))
    db.commit()
    state_cache.invalidate(comp_id)
    return _torna_al_tempo(comp_id)


@router.post("/gara/{comp_id}/pausa")
async def admin_pausa(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp or comp.status != "running":
        raise HTTPException(status_code=400)
    comp.status = "paused"
    comp.paused_at = datetime.utcnow()
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


@router.post("/gara/{comp_id}/termina")
async def admin_termina(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp or comp.status not in ("running", "paused"):
        raise HTTPException(status_code=400)
    tempo.end(comp)  # anche la classifica si oscura (poi si può mostrare a mano)
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


# --- Teams CRUD ---
@router.post("/gara/{comp_id}/squadre/aggiungi")
async def admin_aggiungi_squadra(
    request: Request,
    comp_id: int,
    number: int = Form(...),
    name: str = Form(...),
    city: str = Form(""),
    is_guest: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    db.add(Team(competition_id=comp_id, number=number, name=name, city=city.strip(), is_guest=is_guest))
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}/modifica#squadre", status_code=303)


@router.post("/gara/{comp_id}/squadre/{team_id}/modifica")
async def admin_modifica_squadra(
    request: Request,
    comp_id: int,
    team_id: int,
    number: int = Form(...),
    name: str = Form(...),
    city: str = Form(""),
    is_guest: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    team = db.get(Team, team_id)
    if not team or team.competition_id != comp_id:
        raise HTTPException(status_code=404)
    team.number = number
    team.name = name
    team.city = city.strip()
    team.is_guest = is_guest
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}/modifica#squadre", status_code=303)


@router.post("/gara/{comp_id}/squadre/{team_id}/elimina")
async def admin_elimina_squadra(
    request: Request, comp_id: int, team_id: int, db: Session = Depends(get_db)
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    team = db.get(Team, team_id)
    if not team or team.competition_id != comp_id:
        raise HTTPException(status_code=404)
    db.delete(team)
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}/modifica#squadre", status_code=303)


# --- Problems CRUD ---
@router.post("/gara/{comp_id}/problemi/aggiungi")
async def admin_aggiungi_problema(
    request: Request,
    comp_id: int,
    number: int = Form(...),
    name: str = Form(...),
    answer: str = Form(...),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    answer = answer.strip().zfill(4)[:4]
    db.add(Problem(competition_id=comp_id, number=number, name=name, answer=answer))
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}/modifica#problemi", status_code=303)


@router.post("/gara/{comp_id}/problemi/{prob_id}/modifica")
async def admin_modifica_problema(
    request: Request,
    comp_id: int,
    prob_id: int,
    number: int = Form(...),
    name: str = Form(...),
    answer: str = Form(...),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    prob = db.get(Problem, prob_id)
    if not prob or prob.competition_id != comp_id:
        raise HTTPException(status_code=404)
    prob.number = number
    prob.name = name
    prob.answer = answer.strip().zfill(4)[:4]
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}/modifica#problemi", status_code=303)


@router.post("/gara/{comp_id}/problemi/{prob_id}/elimina")
async def admin_elimina_problema(
    request: Request, comp_id: int, prob_id: int, db: Session = Depends(get_db)
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    prob = db.get(Problem, prob_id)
    if not prob or prob.competition_id != comp_id:
        raise HTTPException(status_code=404)
    db.delete(prob)
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}/modifica#problemi", status_code=303)


# --- Penalties ---
@router.post("/gara/{comp_id}/penalizzazioni/aggiungi")
async def admin_aggiungi_penalizzazione(
    request: Request,
    comp_id: int,
    team_id: int = Form(...),
    value: int = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    db.add(Penalty(competition_id=comp_id, team_id=team_id, value=value, note=note))
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


@router.post("/gara/{comp_id}/penalizzazioni/{pen_id}/elimina")
async def admin_elimina_penalizzazione(
    request: Request, comp_id: int, pen_id: int, db: Session = Depends(get_db)
):
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    pen = db.get(Penalty, pen_id)
    if not pen or pen.competition_id != comp_id:
        raise HTTPException(status_code=404)
    db.delete(pen)
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


# --- Fine gara: classifica finale (ricalcolabile) e blocco degli inserimenti ---
def _torna_alla_gara(comp_id: int, errore: str | None = None, esito: str | None = None) -> RedirectResponse:
    query = f"?errore={quote(errore)}" if errore else (f"?esito={quote(esito)}" if esito else "")
    return RedirectResponse(f"/admin/gara/{comp_id}{query}", status_code=303)


@router.post("/gara/{comp_id}/calcola-finale")
async def admin_calcola_finale(request: Request, comp_id: int, db: Session = Depends(get_db)):
    """Salva la classifica di questo momento come classifica finale (si può ripetere)."""
    require_localhost(request)
    if (bloccata := _se_archiviata(comp_id, db)) is not None:
        return bloccata
    from gdm.engine import compute_state, rank_teams
    comp = load_comp_full(comp_id, db)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.status != "ended":
        return _torna_alla_gara(comp_id, errore="La classifica finale si calcola a gara terminata.")
    _, team_scores = compute_state(comp)
    comp.final_ranking_json = json.dumps([
        {"id": ts.team_id, "number": ts.number, "name": ts.name, "city": ts.city,
         "is_guest": ts.is_guest, "total": ts.total}
        for ts in rank_teams(team_scores, comp)
    ])
    ricalcolo = comp.final_computed_at is not None
    comp.final_computed_at = datetime.utcnow()
    rivelazione_azzerata = comp.revealed_positions > 0
    comp.revealed_positions = 0  # l'ordine può essere cambiato: la rivelazione riparte da capo
    db.commit()
    state_cache.invalidate(comp_id)
    esito = "Classifica finale ricalcolata." if ricalcolo else "Classifica finale calcolata."
    if rivelazione_azzerata:
        esito += " La rivelazione ripartirà dall'inizio."
    return _torna_alla_gara(comp_id, esito=esito)


@router.post("/gara/{comp_id}/oscuramento")
async def admin_oscuramento(
    request: Request, comp_id: int, oscurata: str = Form(""), db: Session = Depends(get_db),
):
    """Oscura o mostra a mano la classifica dei display (gli scatti automatici successivi prevalgono)."""
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    comp.blackout_manual = oscurata == "1"
    comp.blackout_manual_at = comp.elapsed_seconds()
    db.commit()
    return _torna_alla_gara(comp_id, esito="Classifica oscurata nei display." if comp.blackout_manual
                            else "Classifica di nuovo visibile nei display.")


@router.post("/gara/{comp_id}/archivio")
async def admin_archivio(
    request: Request, comp_id: int, archiviata: str = Form(""), torna: str = Form("gara"),
    db: Session = Depends(get_db),
):
    """Archivia (o de-archivia) una gara terminata: archiviata non accetta inserimenti e non compare
    agli inseritori e ai display. La scelta dell'Admin prevale sull'archiviazione automatica."""
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.status != "ended":
        return _torna_alla_gara(comp_id, errore="Si possono archiviare solo le gare terminate.")
    comp.archived_manual = archiviata == "1"
    db.commit()
    state_cache.invalidate(comp_id)
    if torna == "archivio":
        return RedirectResponse("/admin/archivio", status_code=303)
    return _torna_alla_gara(comp_id, esito=(
        "Gara archiviata: non accetta più inserimenti e non compare più agli inseritori e ai display."
        if comp.archived_manual else
        "Gara de-archiviata: accetta di nuovo gli inserimenti e compare agli inseritori e ai display."))


# Viste dei display che l'Admin apre in finestre proprie: non sono display della regia (non compaiono
# lì), sono sempre interne (ignorano l'oscuramento, vedono i jolly) e funzionano anche per le archiviate.
VISTE_ADMIN = {"ranking": "Classifica", "problem_values": "Valori problemi",
               "competition_status": "Stato gara", "matrix": "Matrice"}


def _scala(scala: int) -> int:
    return max(1, min(7, scala))


@router.get("/gara/{comp_id}/vista/{view}", response_class=HTMLResponse)
async def admin_vista(request: Request, comp_id: int, view: str, scala: int = 3, db: Session = Depends(get_db)):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp or view not in VISTE_ADMIN:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("display/viewer.html", {
        "request": request, "comp": comp, "titolo": f"{VISTE_ADMIN[view]} (Admin)",
        "api_url": f"/admin/api/gara/{comp_id}/vista/{view}/stato?scala={_scala(scala)}",
    })


@router.get("/api/gara/{comp_id}/vista/{view}/stato")
async def admin_vista_stato(request: Request, comp_id: int, view: str, scala: int = 3, db: Session = Depends(get_db)):
    require_localhost(request)
    from gdm.routers.display import stato_viewer
    comp = db.get(Competition, comp_id)
    if not comp or view not in VISTE_ADMIN:
        raise HTTPException(status_code=404)
    return stato_viewer(comp, db, view=view, internal=True, text_scale=_scala(scala))


@router.get("/gara/{comp_id}/esporta-pdf")
async def admin_esporta_pdf(request: Request, comp_id: int, db: Session = Depends(get_db)):
    """PDF con classifica finale, valori dei problemi e stato della gara (gara terminata)."""
    require_localhost(request)
    from gdm import esporta_pdf
    comp = load_comp_full(comp_id, db)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.status != "ended" or comp.final_ranking_json is None:
        return _torna_alla_gara(comp_id, errore="Il PDF si esporta a gara terminata, dopo aver calcolato la classifica finale.")
    try:
        contenuto = esporta_pdf.crea_pdf(comp)
    except esporta_pdf.ClassificaNonAggiornata as e:
        return _torna_alla_gara(comp_id, errore=str(e))
    nome = "".join(c if c.isalnum() or c in " -_" else "_" for c in comp.name).strip() or "gara"
    nome = f"Risultati {nome}{' ' + comp.date if comp.date else ''}.pdf"
    return Response(contenuto, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"})


# --- API: current state for JS polling ---
@router.get("/api/gara/{comp_id}/stato")
async def api_stato(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    from gdm.engine import compute_state, rank_teams
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    cached = state_cache.get(comp_id)
    if cached is None:
        comp_full = load_comp_full(comp_id, db)
        prob_states, team_scores = compute_state(comp_full)
        state_cache.set(comp_id, (prob_states, team_scores))
    else:
        prob_states, team_scores = cached
    ranked = rank_teams(team_scores, comp)
    return {
        "status": comp.status,
        "elapsed_seconds": comp.elapsed_seconds(),
        "duration_seconds": comp.duration_minutes * 60,
        "insertions_locked": comp.insertions_locked,
        "archived": comp.is_archived(),
        "final_ready": comp.final_ranking_json is not None,
        "revealed_positions": comp.revealed_positions,
        "teams": [
            {
                "id": ts.team_id,
                "number": ts.number,
                "name": ts.name,
                "city": ts.city,
                "is_guest": ts.is_guest,
                "total": ts.total,
                "jolly_problem_id": ts.jolly_problem_id,
            }
            for ts in ranked
        ],
        "problems": [
            {
                "id": ps.problem_id,
                "number": ps.number,
                "name": ps.name,
                "value": ps.value,
                "num_solvers": len(ps.solvers),
            }
            for ps in sorted(prob_states.values(), key=lambda x: x.number)
        ],
    }
