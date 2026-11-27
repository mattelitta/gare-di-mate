from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import auth
import firma
from database import get_db
import formato
from models import Competition, Display
from paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
formato.registra(templates)

SCALA_MAX = 7  # scala del testo dei display: 1 (30+ squadre) … 7 (poche squadre)
VIEWS = ["test", "ranking", "team_list", "problem_values", "competition_status", "matrix", "final_ranking"]


@router.get("/", response_class=HTMLResponse)
async def regia_home(request: Request, db: Session = Depends(get_db)):
    comps = db.query(Competition).filter(
        Competition.status.in_(["created", "running", "paused", "ended"])
    ).order_by(Competition.created_at.desc()).all()
    return templates.TemplateResponse("regia/home.html", {
        "request": request, "comps": comps, "firma": firma.elenco(db), "firma_url": "/admin/api/firma",
    })


@router.get("/{comp_id}", response_class=HTMLResponse)
async def regia_main(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    displays = sorted(comp.displays, key=lambda d: d.name)
    return templates.TemplateResponse("regia/main.html", {
        "request": request,
        "comp": comp,
        "displays": displays,
        "views": VIEWS,
        "scala_max": SCALA_MAX,
        "adesso": datetime.utcnow(),  # un display che interroga il server da meno di 15 s è "collegato"
        "local_ip": auth.get_local_ip(),
        "https_port": getattr(request.app.state, "https_port", None) or 8443,
        "firma": firma.gara(comp, regia=True), "firma_url": f"/admin/api/gara/{comp_id}/firma?regia=1",
    })


@router.post("/{comp_id}/display/aggiungi")
async def regia_aggiungi_display(
    request: Request, comp_id: int, name: str = Form(...), db: Session = Depends(get_db)
):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
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
    disp = db.get(Display, display_id)
    if not disp or disp.competition_id != comp_id:
        raise HTTPException(status_code=404)
    db.delete(disp)
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/display/{display_id}/scala")
async def regia_set_scala(
    request: Request,
    comp_id: int,
    display_id: int,
    scale: int = Form(...),
    db: Session = Depends(get_db),
):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    disp = db.get(Display, display_id)
    if not disp or disp.competition_id != comp_id:
        raise HTTPException(status_code=404)
    disp.text_scale = max(1, min(SCALA_MAX, scale))
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/display/{display_id}/interno")
async def regia_set_interno(
    request: Request,
    comp_id: int,
    display_id: int,
    interno: str = Form(""),
    db: Session = Depends(get_db),
):
    """Schermo interno: ignora l'oscuramento (classifica e punteggi sempre visibili)."""
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    disp = db.get(Display, display_id)
    if not disp or disp.competition_id != comp_id:
        raise HTTPException(status_code=404)
    disp.internal = bool(interno)
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/rivela")
async def regia_rivela(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    num_teams = len([t for t in comp.final_ranking or [] if not t["is_guest"]])
    if comp.revealed_positions < num_teams:
        comp.revealed_positions += 1
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/rivela-indietro")
async def regia_rivela_indietro(request: Request, comp_id: int, db: Session = Depends(get_db)):
    """Annulla l'ultima posizione rivelata (la nasconde di nuovo)."""
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    comp.revealed_positions = max(0, comp.revealed_positions - 1)
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)


@router.post("/{comp_id}/rivela-reset")
async def regia_rivela_reset(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status_code=404)
    comp.revealed_positions = 0
    db.commit()
    return RedirectResponse(f"/regia/{comp_id}", status_code=303)
