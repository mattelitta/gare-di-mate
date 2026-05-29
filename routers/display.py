from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Competition, Display

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_password(comp: Competition, request: Request) -> bool:
    if not comp.password:
        return True
    return request.cookies.get(f"auth_{comp.id}", "") == comp.password


@router.get("/", response_class=HTMLResponse)
async def display_home(request: Request, db: Session = Depends(get_db)):
    comps = db.query(Competition).filter(
        Competition.status.in_(["running", "paused", "ended"])
    ).order_by(Competition.created_at.desc()).all()
    return templates.TemplateResponse("display/home.html", {"request": request, "comps": comps})


@router.get("/{comp_id}/login", response_class=HTMLResponse)
async def display_login_form(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("display/login.html", {"request": request, "comp": comp})


@router.post("/{comp_id}/login")
async def display_login(
    request: Request, comp_id: int, password: str = Form(""), db: Session = Depends(get_db)
):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.password and password != comp.password:
        return templates.TemplateResponse(
            "display/login.html", {"request": request, "comp": comp, "error": "Password errata"}
        )
    response = RedirectResponse(f"/display/{comp_id}", status_code=303)
    response.set_cookie(f"auth_{comp_id}", password, httponly=True)
    return response


@router.get("/{comp_id}", response_class=HTMLResponse)
async def display_select(request: Request, comp_id: int, db: Session = Depends(get_db)):
    """Display selection: choose which named display this screen is."""
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if not check_password(comp, request):
        return RedirectResponse(f"/display/{comp_id}/login")
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
    if not check_password(comp, request):
        return RedirectResponse(f"/display/{comp_id}/login")

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


@router.get("/api/{comp_id}/schermo/{display_id}/stato")
async def display_api_stato(comp_id: int, display_id: int, db: Session = Depends(get_db)):
    """JSON endpoint polled by display viewer to get current view and data."""
    from engine import compute_state, rank_teams

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
    blackout_active = (
        comp.status in ("running", "paused", "ended")
        and elapsed >= comp.blackout_minute * 60
    )

    prob_states, team_scores = compute_state(comp)
    ranked = rank_teams(team_scores, comp)

    # Serialize team scores
    teams_data = []
    for i, ts in enumerate(ranked):
        teams_data.append({
            "rank": i + 1,
            "team_id": ts.team_id,
            "number": ts.number,
            "name": ts.name,
            "city": ts.city,
            "is_guest": ts.is_guest,
            "total": round(ts.total, 2),
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
            "value": round(ps.value, 2),
            "num_solvers": len(ps.solvers),
        }
        for ps in sorted(prob_states.values(), key=lambda x: x.number)
    ]

    return {
        "view": disp.current_view,
        "comp_name": comp.name,
        "comp_date": comp.date,
        "status": comp.status,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "duration_seconds": comp.duration_minutes * 60,
        "blackout_active": blackout_active,
        "jolly_time_seconds": comp.jolly_time_minutes * 60,
        "n": comp.n,
        "num_qualified": comp.num_qualified,
        "revealed_positions": comp.revealed_positions,
        "final_locked": comp.final_locked,
        "teams": teams_data,
        "problems": problems_data,
    }
