import json
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import auth
import formato
import tempo
from cache import state_cache
from database import get_db, load_comp_full
from models import Competition, Display, JollyChoice, Penalty, Problem, Submission, Team, TimeAdjustment
from paths import TEMPLATES_DIR

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


def require_localhost(request: Request):
    if not auth.is_local(request):
        raise HTTPException(status_code=403, detail="Admin accessibile solo in locale")


# --- Competition list ---
@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request, db: Session = Depends(get_db)):
    require_localhost(request)
    comps = db.query(Competition).order_by(Competition.created_at.desc()).all()
    return templates.TemplateResponse("admin/home.html", {
        "request": request, "comps": comps, "local_ip": auth.get_local_ip(),
        "access_password_set": auth.password_is_set(db),
    })


@router.post("/password-accesso")
async def admin_password_accesso(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    require_localhost(request)
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 4 caratteri")
    auth.set_password(db, password)
    return RedirectResponse("/admin/", status_code=303)


# --- Create competition ---
@router.get("/crea", response_class=HTMLResponse)
async def admin_crea_form(request: Request):
    require_localhost(request)
    return templates.TemplateResponse("admin/crea.html", {"request": request})


@router.post("/crea")
async def admin_crea(
    request: Request,
    name: str = Form(...),
    date: str = Form(...),
    initial_value: int = Form(40),
    n: int = Form(2),
    k: int = Form(1),
    first_delivery_bonuses: str = Form("20,15,10,5,3"),
    full_bonuses: str = Form("50,30,20,15,10"),
    duration_minutes: int = Form(90),
    jolly_time_minutes: int = Form(30),
    threshold_minute: int = Form(...),
    blackout_minute: int = Form(...),
    num_qualified: int = Form(0),
    final_reveal_count: int = Form(3),
    display_theme: str = Form("light"),
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
        date=date,
        initial_value=initial_value,
        n=n,
        k=k,
        first_delivery_bonuses_json=json.dumps(fd),
        full_bonuses_json=json.dumps(fb),
        duration_minutes=duration_minutes,
        jolly_time_minutes=jolly_time_minutes,
        threshold_minute=threshold_minute,
        blackout_minute=blackout_minute,
        num_qualified=num_qualified,
        final_reveal_count=final_reveal_count,
        display_theme=display_theme if display_theme in ('dark', 'light') else 'dark',
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
    return templates.TemplateResponse("admin/gara.html", {"request": request, "comp": comp})


# --- Edit competition ---
@router.get("/gara/{comp_id}/modifica", response_class=HTMLResponse)
async def admin_modifica_form(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/modifica.html", {"request": request, "comp": comp})


@router.post("/gara/{comp_id}/modifica")
async def admin_modifica(
    request: Request,
    comp_id: int,
    name: str = Form(...),
    date: str = Form(...),
    initial_value: int = Form(40),
    n: int = Form(2),
    k: int = Form(1),
    first_delivery_bonuses: str = Form("20,15,10,5,3"),
    full_bonuses: str = Form("50,30,20,15,10"),
    duration_minutes: int = Form(90),
    jolly_time_minutes: int = Form(30),
    threshold_minute: int = Form(...),
    blackout_minute: int = Form(...),
    num_qualified: int = Form(0),
    final_reveal_count: int = Form(3),
    display_theme: str = Form("dark"),
    db: Session = Depends(get_db),
):
    require_localhost(request)
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
    comp.date = date
    comp.initial_value = initial_value
    comp.n = n
    comp.k = k
    comp.first_delivery_bonuses_json = json.dumps(fd)
    comp.full_bonuses_json = json.dumps(fb)
    comp.duration_minutes = duration_minutes
    comp.jolly_time_minutes = jolly_time_minutes
    comp.threshold_minute = threshold_minute
    comp.blackout_minute = blackout_minute
    comp.num_qualified = num_qualified
    comp.final_reveal_count = final_reveal_count
    comp.display_theme = display_theme if display_theme in ('dark', 'light') else 'dark'
    db.commit()
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
        n=orig.n,
        k=orig.k,
        first_delivery_bonuses_json=orig.first_delivery_bonuses_json,
        full_bonuses_json=orig.full_bonuses_json,
        duration_minutes=orig.duration_minutes,
        jolly_time_minutes=orig.jolly_time_minutes,
        threshold_minute=orig.threshold_minute,
        blackout_minute=orig.blackout_minute,
        num_qualified=orig.num_qualified,
        final_reveal_count=orig.final_reveal_count,
        display_theme=orig.display_theme,
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
    now = datetime.utcnow()
    if comp.status == "paused" and comp.paused_at:
        comp.total_paused_seconds += (now - comp.paused_at).total_seconds()
    comp.status = "ended"
    comp.ended_at = now
    comp.blackout_manual = None  # a fine gara la classifica si oscura comunque (poi si può mostrare a mano)
    comp.blackout_manual_at = None
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
    from engine import compute_state, rank_teams
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


@router.post("/gara/{comp_id}/blocco-inserimenti")
async def admin_blocco_inserimenti(
    request: Request, comp_id: int, bloccati: str = Form(""), db: Session = Depends(get_db),
):
    """Spunta a gara terminata: blocca (o sblocca) soluzioni, jolly e modifiche dello storico."""
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.status != "ended":
        return _torna_alla_gara(comp_id, errore="Gli inserimenti si possono bloccare a gara terminata.")
    comp.insertions_locked = bloccati == "1"
    db.commit()
    return _torna_alla_gara(comp_id, esito="Inserimenti bloccati." if comp.insertions_locked
                            else "Inserimenti di nuovo aperti.")


# --- API: current state for JS polling ---
@router.get("/api/gara/{comp_id}/stato")
async def api_stato(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    from engine import compute_state, rank_teams
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
