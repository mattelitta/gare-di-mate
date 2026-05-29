import json
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from cache import state_cache
from database import get_db, load_comp_full
from models import Competition, Display, JollyChoice, Penalty, Problem, Submission, Team

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def require_localhost(request: Request):
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Admin accessibile solo in locale")


# --- Competition list ---
@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request, db: Session = Depends(get_db)):
    require_localhost(request)
    comps = db.query(Competition).order_by(Competition.created_at.desc()).all()
    return templates.TemplateResponse("admin/home.html", {"request": request, "comps": comps})


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
    password: str = Form(""),
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
        password=password if password else None,
        status="created",
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return RedirectResponse(f"/admin/gara/{comp.id}", status_code=303)


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
    password: str = Form(""),
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
    comp.password = password if password else None
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
        password=orig.password,
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
    else:
        # resume from pause
        paused_duration = (now - comp.paused_at).total_seconds()
        comp.total_paused_seconds += paused_duration
        comp.paused_at = None
    comp.status = "running"
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


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
    city: str = Form(...),
    is_guest: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    db.add(Team(competition_id=comp_id, number=number, name=name, city=city, is_guest=is_guest))
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


@router.post("/gara/{comp_id}/squadre/{team_id}/modifica")
async def admin_modifica_squadra(
    request: Request,
    comp_id: int,
    team_id: int,
    number: int = Form(...),
    name: str = Form(...),
    city: str = Form(...),
    is_guest: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_localhost(request)
    team = db.get(Team, team_id)
    if not team or team.competition_id != comp_id:
        raise HTTPException(status_code=404)
    team.number = number
    team.name = name
    team.city = city
    team.is_guest = is_guest
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


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
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


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
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


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
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


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
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


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


# --- Lock final ranking ---
@router.post("/gara/{comp_id}/blocca-finale")
async def admin_blocca_finale(request: Request, comp_id: int, db: Session = Depends(get_db)):
    require_localhost(request)
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    comp.final_locked = True
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/admin/gara/{comp_id}", status_code=303)


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
        "final_locked": comp.final_locked,
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
