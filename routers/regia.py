from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Competition, Display

router = APIRouter()
templates = Jinja2Templates(directory="templates")

VIEWS = ["test", "ranking", "team_list", "problem_values", "competition_status", "final_ranking"]


def check_password(comp: Competition, request: Request):
    if not comp.password:
        return True
    return request.cookies.get(f"auth_{comp.id}", "") == comp.password


@router.get("/", response_class=HTMLResponse)
async def regia_home(request: Request, db: Session = Depends(get_db)):
    comps = db.query(Competition).filter(
        Competition.status.in_(["created", "running", "paused", "ended"])
    ).order_by(Competition.created_at.desc()).all()
    return templates.TemplateResponse("regia/home.html", {"request": request, "comps": comps})


@router.get("/{comp_id}/login", response_class=HTMLResponse)
async def regia_login_form(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("regia/login.html", {"request": request, "comp": comp})


@router.post("/{comp_id}/login")
async def regia_login(
    request: Request, comp_id: int, password: str = Form(""), db: Session = Depends(get_db)
):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.password and password != comp.password:
        return templates.TemplateResponse(
            "regia/login.html", {"request": request, "comp": comp, "error": "Password errata"}
        )
    response = RedirectResponse(f"/regia/{comp_id}", status_code=303)
    response.set_cookie(f"auth_{comp_id}", password, httponly=True)
    return response


@router.get("/{comp_id}", response_class=HTMLResponse)
async def regia_main(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.password and not check_password(comp, request):
        return RedirectResponse(f"/regia/{comp_id}/login")
    displays = sorted(comp.displays, key=lambda d: d.name)
    return templates.TemplateResponse("regia/main.html", {
        "request": request,
        "comp": comp,
        "displays": displays,
        "views": VIEWS,
    })


@router.post("/{comp_id}/display/aggiungi")
async def regia_aggiungi_display(
    request: Request, comp_id: int, name: str = Form(...), db: Session = Depends(get_db)
):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.password and not check_password(comp, request):
        raise HTTPException(status_code=403)
    db.add(Display(competition_id=comp_id, name=name, current_view="test"))
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/display/{display_id}/vista")
async def regia_set_vista(
    request: Request,
    comp_id: int,
    display_id: int,
    view: str = Form(...),
    db: Session = Depends(get_db),
):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.password and not check_password(comp, request):
        raise HTTPException(status_code=403)
    disp = db.get(Display, display_id)
    if not disp or disp.competition_id != comp_id:
        raise HTTPException(status_code=404)
    if view not in VIEWS:
        raise HTTPException(status_code=400)
    disp.current_view = view
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/display/{display_id}/elimina")
async def regia_elimina_display(
    request: Request, comp_id: int, display_id: int, db: Session = Depends(get_db)
):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.password and not check_password(comp, request):
        raise HTTPException(status_code=403)
    disp = db.get(Display, display_id)
    if not disp or disp.competition_id != comp_id:
        raise HTTPException(status_code=404)
    db.delete(disp)
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/rivela")
async def regia_rivela(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.password and not check_password(comp, request):
        raise HTTPException(status_code=403)
    num_teams = len([t for t in comp.teams if not t.is_guest])
    if comp.revealed_positions < num_teams:
        comp.revealed_positions += 1
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/rivela-reset")
async def regia_rivela_reset(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    if comp.password and not check_password(comp, request):
        raise HTTPException(status_code=403)
    comp.revealed_positions = 0
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)
