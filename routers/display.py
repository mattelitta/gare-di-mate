from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import auth
from cache import state_cache
from database import get_db, load_comp_full
from engine import compute_state, rank_teams
from models import Competition, Display
from paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_client_ip(request: Request) -> str:
    return auth.client_ip(request) or "unknown"


@router.get("/", response_class=HTMLResponse)
async def display_home(request: Request, db: Session = Depends(get_db)):
    comps = db.query(Competition).filter(
        Competition.status.in_(["created", "running", "paused", "ended"])
    ).order_by(Competition.created_at.desc()).all()
    return templates.TemplateResponse("display/home.html", {"request": request, "comps": comps})


@router.get("/{comp_id}", response_class=HTMLResponse)
async def display_select(request: Request, comp_id: int, db: Session = Depends(get_db)):
    """Display selection: choose which named display this screen is."""
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    displays = sorted(comp.displays, key=lambda d: d.name)
    return templates.TemplateResponse("display/select.html", {
        "request": request,
        "comp": comp,
        "displays": displays,
        "client_ip": get_client_ip(request),
    })


@router.get("/{comp_id}/schermo/{display_id}", response_class=HTMLResponse)
async def display_view(
    request: Request, comp_id: int, display_id: int, db: Session = Depends(get_db)
):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    disp = db.get(Display, display_id)
    if not disp or disp.competition_id != comp_id:
        raise HTTPException(status_code=404)

    # Update IP and last_seen
    disp.ip_address = get_client_ip(request)
    disp.last_seen = datetime.utcnow()
    db.commit()

    return templates.TemplateResponse("display/viewer.html", {
        "request": request,
        "comp": comp,
        "disp": disp,
    })


def _final_svelata(comp: Competition) -> list[dict]:
    """Classifica finale come la vedono i display: le squadre non ancora svelate sono solo segnaposto
    (posizione occupata, senza nome né punti); le ospiti compaiono dalla prima posizione svelata."""
    teams = comp.final_ranking or []
    in_gara = [t for t in teams if not t.get("is_guest")]
    svelate = max(0, min(comp.revealed_positions or 0, len(in_gara)))
    da = len(in_gara) - svelate
    out = [t if i >= da else {"is_guest": False, "hidden": True} for i, t in enumerate(in_gara)]
    if svelate:
        out += [t for t in teams if t.get("is_guest")]
    return out


@router.get("/api/{comp_id}/schermo/{display_id}/stato")
async def display_api_stato(comp_id: int, display_id: int, db: Session = Depends(get_db)):
    """JSON endpoint polled by display viewer to get current view and data."""

    # Carica display e metadati gara (query leggera, senza relazioni pesanti)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)

    disp = db.get(Display, display_id)
    if not disp or disp.competition_id != comp_id:
        raise HTTPException(status_code=404)

    disp.last_seen = datetime.utcnow()
    db.commit()

    elapsed = comp.elapsed_seconds()
    remaining = max(0, comp.duration_minutes * 60 - elapsed)
    # Da lì classifica, elenco squadre e stato gara restano nascosti; la classifica si vede solo
    # con la rivelazione della classifica finale dalla regia.
    # Gli schermi interni (scelti dalla regia) ignorano l'oscuramento.
    blackout_ignored = comp.blackout_active() and disp.internal
    blackout_active = comp.blackout_active() and not disp.internal

    # Controlla cache — se presente evita di ricaricare tutto dal DB
    # Con i jolly nascosti fino alla chiusura, i display li ignorano del tutto (anche il raddoppio
    # dei punti, che altrimenti li rivelerebbe).
    jolly_public = comp.jolly_public() or disp.internal  # gli schermi interni vedono sempre i jolly
    variant = "full" if jolly_public else "public"
    cached = state_cache.get(comp_id, variant)
    if cached is None:
        comp_full = load_comp_full(comp_id, db)
        prob_states, team_scores = compute_state(comp_full, include_jolly=jolly_public)
        state_cache.set(comp_id, (prob_states, team_scores), variant)
    else:
        prob_states, team_scores = cached

    ranked = rank_teams(team_scores, comp) if not blackout_active else []

    # Serialize team scores (con l'oscuramento nessuna: le viste che le usano sono oscurate)
    teams_data = []
    for i, ts in enumerate(ranked):
        teams_data.append({
            "rank": i + 1,
            "team_id": ts.team_id,
            "number": ts.number,
            "name": ts.name,
            "city": ts.city,
            "is_guest": ts.is_guest,
            "total": ts.total,
            "jolly_problem_id": ts.jolly_problem_id,
            "problem_contributions": {str(k): round(v, 2) for k, v in ts.problem_contributions.items()},
            "problem_errors": ts.problem_errors,
            "problem_solved": ts.problem_solved,
            "full_bonus_earned": ts.full_bonus_earned,
            "penalty_total": ts.penalty_total,
        })

    problems_data = [
        {
            "id": ps.problem_id,
            "number": ps.number,
            "name": ps.name,
            "value": ps.value,
            "num_solvers": None if blackout_active else len(ps.solvers),
        }
        for ps in sorted(prob_states.values(), key=lambda x: x.number)
    ]

    return {
        "view": disp.current_view,
        "text_scale": disp.text_scale if disp.text_scale else 3,
        "display_theme": comp.display_theme or 'dark',
        "comp_name": comp.name,
        "comp_date": comp.date,
        "status": comp.status,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "duration_seconds": comp.duration_minutes * 60,
        "blackout_active": blackout_active,
        "internal": disp.internal,
        "blackout_ignored": blackout_ignored,  # per l'avviso "schermo interno" nell'intestazione
        "jolly_time_seconds": comp.jolly_time_minutes * 60,
        "jolly_public": jolly_public,
        "n": comp.n,
        "num_qualified": comp.num_qualified,
        "revealed_positions": comp.revealed_positions,
        "final_ready": comp.final_ranking_json is not None,
        "final_ranking": _final_svelata(comp),  # fotografia calcolata dall'Admin, solo la parte svelata
        "teams": teams_data,
        "problems": problems_data,
    }
