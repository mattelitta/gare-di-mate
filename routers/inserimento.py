from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from cache import state_cache
from database import get_db
from models import Competition, JollyChoice, Problem, Submission, Team
from paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_comp_or_404(comp_id: int, db: Session) -> Competition:
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    return comp


@router.get("/", response_class=HTMLResponse)
async def inserimento_home(request: Request, db: Session = Depends(get_db)):
    comps = db.query(Competition).filter(
        Competition.status.in_(["created", "running", "paused", "ended"])
    ).order_by(Competition.created_at.desc()).all()
    return templates.TemplateResponse("inserimento/home.html", {"request": request, "comps": comps})


def require_started(comp: Competition):
    if comp.status == "created":
        raise HTTPException(status_code=409, detail="La gara non è ancora iniziata")


@router.get("/{comp_id}/stato")
async def inserimento_stato(comp_id: int, db: Session = Depends(get_db)):
    """Usato dalla pagina di inserimento per attivare l'invio appena la gara parte."""
    return {"status": get_comp_or_404(comp_id, db).status}


@router.get("/{comp_id}", response_class=HTMLResponse)
async def inserimento_main(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = get_comp_or_404(comp_id, db)
    teams = sorted(comp.teams, key=lambda t: t.number)
    problems = sorted(comp.problems, key=lambda p: p.number)
    # Get jolly choices already made
    jolly_map = {jc.team_id: jc.problem_id for jc in comp.jolly_choices}
    elapsed_min = comp.elapsed_minutes()
    jolly_expired = elapsed_min >= comp.jolly_time_minutes
    return templates.TemplateResponse("inserimento/main.html", {
        "request": request,
        "comp": comp,
        "teams": teams,
        "problems": problems,
        "jolly_map": jolly_map,
        "jolly_expired": jolly_expired,
        "elapsed_min": elapsed_min,
        "started": comp.status != "created",
    })


@router.post("/{comp_id}/jolly")
async def inserimento_jolly(
    request: Request,
    comp_id: int,
    team_number: str = Form(...),
    problem_number: str = Form(...),
    db: Session = Depends(get_db),
):
    comp = get_comp_or_404(comp_id, db)
    require_started(comp)
    team = db.query(Team).filter_by(competition_id=comp_id, number=int(team_number)).first()
    problem = db.query(Problem).filter_by(competition_id=comp_id, number=int(problem_number)).first()
    if not team or not problem:
        raise HTTPException(status_code=400, detail="Squadra o problema non trovato")

    # Remove previous jolly for this team if any
    existing = db.query(JollyChoice).filter_by(competition_id=comp_id, team_id=team.id).first()
    if existing:
        db.delete(existing)

    game_sec = comp.elapsed_seconds()
    db.add(JollyChoice(
        competition_id=comp_id,
        team_id=team.id,
        problem_id=problem.id,
        game_seconds=game_sec,
    ))
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/inserimento/{comp_id}", status_code=303)


@router.post("/{comp_id}/soluzione")
async def inserimento_soluzione(
    request: Request,
    comp_id: int,
    team_number: str = Form(...),
    problem_number: str = Form(...),
    answer: str = Form(...),
    db: Session = Depends(get_db),
):
    comp = get_comp_or_404(comp_id, db)
    require_started(comp)
    team = db.query(Team).filter_by(competition_id=comp_id, number=int(team_number)).first()
    problem = db.query(Problem).filter_by(competition_id=comp_id, number=int(problem_number)).first()
    if not team or not problem:
        raise HTTPException(status_code=400, detail="Squadra o problema non trovato")

    answer = answer.strip().zfill(4)[:4]
    is_correct = answer == problem.answer

    is_post_game = comp.status == "ended"
    if is_post_game:
        game_sec = comp.duration_minutes * 60.0
    else:
        game_sec = comp.elapsed_seconds()

    db.add(Submission(
        competition_id=comp_id,
        team_id=team.id,
        problem_id=problem.id,
        answer=answer,
        is_correct=is_correct,
        is_post_game=is_post_game,
        game_seconds=game_sec,
        device_id=request.state.device_id,
    ))
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(f"/inserimento/{comp_id}", status_code=303)


def _consegne_url(comp_id: int, request: Request) -> str:
    """URL dello storico che conserva i filtri attivi (passati come query string)."""
    query = request.url.query
    return f"/inserimento/{comp_id}/consegne" + (f"?{query}" if query else "")


@router.get("/{comp_id}/consegne", response_class=HTMLResponse)
async def inserimento_consegne(
    request: Request,
    comp_id: int,
    squadra: str = "",
    problema: str = "",
    mie: bool = False,
    db: Session = Depends(get_db),
):
    comp = get_comp_or_404(comp_id, db)
    # Le select inviano "" per "tutte": i filtri vuoti o non numerici sono ignorati.
    squadra = int(squadra) if squadra.isdigit() else None
    problema = int(problema) if problema.isdigit() else None
    ordered = sorted(comp.submissions, key=lambda s: (s.game_seconds, s.submitted_at))
    rows = [
        (idx, s) for idx, s in enumerate(ordered, start=1)
        if (squadra is None or s.team_id == squadra)
        and (problema is None or s.problem_id == problema)
        and (not mie or s.device_id == request.state.device_id)
    ]
    return templates.TemplateResponse("inserimento/consegne.html", {
        "request": request,
        "comp": comp,
        "rows": rows,
        "total": len(ordered),
        "teams": {t.id: t for t in comp.teams},
        "problems": {p.id: p for p in comp.problems},
        "teams_sorted": sorted(comp.teams, key=lambda t: t.number),
        "problems_sorted": sorted(comp.problems, key=lambda p: p.number),
        "f_squadra": squadra,
        "f_problema": problema,
        "f_mie": mie,
        "query": request.url.query,
    })


@router.post("/{comp_id}/consegne/{sub_id}/elimina")
async def inserimento_elimina_consegna(
    request: Request, comp_id: int, sub_id: int, db: Session = Depends(get_db)
):
    comp = get_comp_or_404(comp_id, db)
    sub = db.get(Submission, sub_id)
    if not sub or sub.competition_id != comp_id:
        raise HTTPException(status_code=404)
    db.delete(sub)
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(_consegne_url(comp_id, request), status_code=303)


@router.get("/{comp_id}/consegne/{sub_id}/modifica", response_class=HTMLResponse)
async def inserimento_modifica_form(
    request: Request, comp_id: int, sub_id: int, db: Session = Depends(get_db)
):
    comp = get_comp_or_404(comp_id, db)
    sub = db.get(Submission, sub_id)
    if not sub or sub.competition_id != comp_id:
        raise HTTPException(status_code=404)
    teams = sorted(comp.teams, key=lambda t: t.number)
    problems = sorted(comp.problems, key=lambda p: p.number)
    return templates.TemplateResponse("inserimento/modifica_consegna.html", {
        "request": request,
        "comp": comp,
        "sub": sub,
        "teams": teams,
        "problems": problems,
        "query": request.url.query,
    })


@router.post("/{comp_id}/consegne/{sub_id}/modifica")
async def inserimento_modifica_consegna(
    request: Request,
    comp_id: int,
    sub_id: int,
    team_id: int = Form(...),
    problem_id: int = Form(...),
    answer: str = Form(...),
    db: Session = Depends(get_db),
):
    comp = get_comp_or_404(comp_id, db)
    sub = db.get(Submission, sub_id)
    if not sub or sub.competition_id != comp_id:
        raise HTTPException(status_code=404)
    problem = db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(status_code=400)
    answer = answer.strip().zfill(4)[:4]
    sub.team_id = team_id
    sub.problem_id = problem_id
    sub.answer = answer
    sub.is_correct = answer == problem.answer
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(_consegne_url(comp_id, request), status_code=303)
