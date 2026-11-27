from datetime import datetime
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from cache import state_cache
from database import get_db
import firma
import formato
from models import Competition, JollyChoice, Problem, Submission, Team
from paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
formato.registra(templates)


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
    return templates.TemplateResponse("inserimento/home.html", {
        "request": request, "comps": comps, "firma": firma.elenco(db), "firma_url": "/inserimento/api/firma",
    })


@router.get("/api/firma")
async def inserimento_api_firma(db: Session = Depends(get_db)):
    """Firma dell'elenco delle gare, per l'aggiornamento automatico (vedi firma.py)."""
    return PlainTextResponse(firma.elenco(db))


class InputError(ValueError):
    """Dato inserito non valido: il messaggio viene mostrato nella pagina."""


def _torna(url: str, errore: str, ancora: str = "") -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{sep}errore={quote(errore)}{ancora}", status_code=303)


def require_started(comp: Competition):
    if comp.status == "created":
        raise InputError("La gara non è ancora iniziata: l'invio si attiva quando parte.")
    require_open(comp)


def require_open(comp: Competition):
    if comp.insertions_locked:
        raise InputError("Gli inserimenti sono stati bloccati dall'Admin.")


def _numero(valore: str, cosa: str) -> int:
    valore = valore.strip()
    if not valore:
        raise InputError(f"Inserire il numero {cosa}.")
    if not valore.isdigit():
        raise InputError(f"Il numero {cosa} deve contenere solo cifre.")
    return int(valore)


def _team(db: Session, comp_id: int, team_number: str) -> Team:
    n = _numero(team_number, "della squadra")
    team = db.query(Team).filter_by(competition_id=comp_id, number=n).first()
    if not team:
        raise InputError(f"La squadra {n:02d} non esiste in questa gara.")
    return team


def _problem(db: Session, comp_id: int, problem_number: str) -> Problem:
    n = _numero(problem_number, "del problema")
    problem = db.query(Problem).filter_by(competition_id=comp_id, number=n).first()
    if not problem:
        raise InputError(f"Il problema {n:02d} non esiste in questa gara.")
    return problem


def _risposta(answer: str) -> str:
    """Risposta a 4 cifre con zeri iniziali (es. "42" → "0042")."""
    answer = answer.strip()
    if not answer:
        raise InputError("Inserire la risposta.")
    if not answer.isdigit() or len(answer) > 4:
        raise InputError("La risposta deve essere un numero da 0 a 9999 (solo cifre).")
    return answer.zfill(4)


def _stato(comp: Competition) -> dict:
    """Stato della gara per la pagina di inserimento (aggiornata ogni 2 s)."""
    teams = {t.id: t.number for t in comp.teams}
    problems = {p.id: p.number for p in comp.problems}
    return {
        "status": comp.status,
        "locked": comp.insertions_locked,
        "elapsed": comp.elapsed_seconds(),
        "duration": comp.duration_minutes * 60,
        "jolly_seconds": comp.jolly_time_minutes * 60,
        # numero squadra -> numero problema scelto come jolly
        "jolly": {str(teams[jc.team_id]): problems[jc.problem_id]
                  for jc in comp.jolly_choices if jc.team_id in teams and jc.problem_id in problems},
    }


def _problema_jolly_predefinito(comp: Competition) -> Problem | None:
    """Il problema 01, o quello con il numero più basso se il problema 01 non esiste."""
    return min(comp.problems, key=lambda p: (p.number != 1, p.number), default=None)


@router.get("/{comp_id}/stato")
async def inserimento_stato(comp_id: int, db: Session = Depends(get_db)):
    return _stato(get_comp_or_404(comp_id, db))


@router.get("/{comp_id}", response_class=HTMLResponse)
async def inserimento_main(request: Request, comp_id: int, db: Session = Depends(get_db)):
    comp = get_comp_or_404(comp_id, db)
    teams = sorted(comp.teams, key=lambda t: t.number)
    problems = sorted(comp.problems, key=lambda p: p.number)
    default = _problema_jolly_predefinito(comp)
    return templates.TemplateResponse("inserimento/main.html", {
        "request": request,
        "comp": comp,
        "teams": teams,
        "problems": problems,
        "stato": _stato(comp),
        "squadre": [{"n": t.number, "nome": t.name} for t in teams],
        "jolly_predefinito": default.number if default else None,
        "started": comp.status != "created",
    })


@router.post("/{comp_id}/jolly-mancanti")
async def inserimento_jolly_mancanti(request: Request, comp_id: int, db: Session = Depends(get_db)):
    """Allo scadere del tempo dei jolly: assegna il problema predefinito a chi non ha scelto."""
    comp = get_comp_or_404(comp_id, db)
    problem = _problema_jolly_predefinito(comp)
    try:
        require_started(comp)
        if comp.status != "ended" and comp.elapsed_seconds() < comp.jolly_time_minutes * 60:
            raise InputError("Il tempo per scegliere i jolly non è ancora scaduto.")
        if problem is None:
            raise InputError("La gara non ha problemi.")
    except InputError as e:
        return _torna(f"/inserimento/{comp_id}", f"Jolly non assegnati. {e}")
    con_jolly = {jc.team_id for jc in comp.jolly_choices}
    mancanti = [t for t in comp.teams if t.id not in con_jolly]
    for team in mancanti:
        db.add(JollyChoice(competition_id=comp_id, team_id=team.id, problem_id=problem.id,
                           game_seconds=comp.elapsed_seconds()))
    db.commit()
    state_cache.invalidate(comp_id)
    esito = (f"Jolly sul problema {problem.number:02d} assegnato a {len(mancanti)} "
             f"{'squadra' if len(mancanti) == 1 else 'squadre'}." if mancanti
             else "Tutte le squadre avevano già un jolly.")
    return RedirectResponse(f"/inserimento/{comp_id}?esito={quote(esito)}", status_code=303)


@router.post("/{comp_id}/jolly")
async def inserimento_jolly(
    request: Request,
    comp_id: int,
    team_number: str = Form(...),
    problem_number: str = Form(...),
    db: Session = Depends(get_db),
):
    comp = get_comp_or_404(comp_id, db)
    try:
        require_started(comp)
        team = _team(db, comp_id, team_number)
        problem = _problem(db, comp_id, problem_number)
    except InputError as e:
        return _torna(f"/inserimento/{comp_id}", f"Jolly non registrato. {e}")

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
    try:
        require_started(comp)
        team = _team(db, comp_id, team_number)
        problem = _problem(db, comp_id, problem_number)
        answer = _risposta(answer)
    except InputError as e:
        return _torna(f"/inserimento/{comp_id}", f"Consegna non registrata. {e}", ancora="#risposte")
    is_correct = answer == problem.answer

    is_post_game = comp.status == "ended" or comp.elapsed_seconds() >= comp.duration_minutes * 60
    if is_post_game:
        # Il momento in cui la gara è finita: la fine teorica, o prima se è stata terminata in anticipo.
        game_sec = min(comp.duration_minutes * 60.0, comp.elapsed_seconds())
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
    return RedirectResponse(f"/inserimento/{comp_id}#risposte", status_code=303)


def _consegne_url(comp_id: int, request: Request) -> str:
    """URL dello storico che conserva i filtri attivi (passati come query string)."""
    query = _filtri(request)
    return f"/inserimento/{comp_id}/consegne" + (f"?{query}" if query else "")


@router.get("/{comp_id}/consegne", response_class=HTMLResponse)
async def inserimento_consegne(
    request: Request,
    comp_id: int,
    squadra: str = "",
    problema: str = "",
    mie: bool = False,
    ordine: str = "",
    db: Session = Depends(get_db),
):
    comp = get_comp_or_404(comp_id, db)
    # Le select inviano "" per "tutte": i filtri vuoti o non numerici sono ignorati.
    squadra = int(squadra) if squadra.isdigit() else None
    problema = int(problema) if problema.isdigit() else None
    filtri_attivi = squadra is not None or problema is not None or mie
    ordered = sorted(comp.submissions, key=lambda s: (s.game_seconds, s.submitted_at))
    # Voci: (chiave di ordinamento, tipo, numero cronologico, oggetto). A parità di tempo di gara
    # le consegne vengono prima dell'avanzamento fatto in quello stesso istante.
    voci = [
        ((s.game_seconds, 0, s.submitted_at), "consegna", idx, s)
        for idx, s in enumerate(ordered, start=1)
        if (squadra is None or s.team_id == squadra)
        and (problema is None or s.problem_id == problema)
        and (not mie or s.device_id == request.state.device_id)
    ]
    shown = len(voci)
    if not filtri_attivi:  # gli avanzamenti non riguardano una squadra, un problema o un dispositivo
        voci += [((a.game_seconds_at, 1, a.created_at), "avanzamento", None, a) for a in comp.time_adjustments]
    crescente = ordine == "crescente"
    voci.sort(key=lambda v: v[0], reverse=not crescente)
    return templates.TemplateResponse("inserimento/consegne.html", {
        "request": request,
        "comp": comp,
        "voci": [v[1:] for v in voci],
        "shown": shown,
        "crescente": crescente,
        "filtri_attivi": filtri_attivi,
        "total": len(ordered),
        "teams": {t.id: t for t in comp.teams},
        "problems": {p.id: p for p in comp.problems},
        "teams_sorted": sorted(comp.teams, key=lambda t: t.number),
        "problems_sorted": sorted(comp.problems, key=lambda p: p.number),
        "f_squadra": squadra,
        "f_problema": problema,
        "f_mie": mie,
        "query": _filtri(request),
    })


@router.post("/{comp_id}/consegne/{sub_id}/elimina")
async def inserimento_elimina_consegna(
    request: Request, comp_id: int, sub_id: int, db: Session = Depends(get_db)
):
    comp = get_comp_or_404(comp_id, db)
    sub = db.get(Submission, sub_id)
    if not sub or sub.competition_id != comp_id:
        raise HTTPException(status_code=404)
    try:
        require_open(comp)
    except InputError as e:
        return _torna(_consegne_url(comp_id, request), f"Consegna non eliminata. {e}")
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
        "query": _filtri(request),
    })


def _filtri(request: Request) -> str:
    """Query string dei filtri dello storico, senza l'eventuale messaggio d'errore.
    Usata anche per lo storico stesso, così l'errore non resta nei link di modifica ed eliminazione."""
    return urlencode([(k, v) for k, v in request.query_params.multi_items() if k not in ("errore", "esito")])


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
    team = db.get(Team, team_id)
    problem = db.get(Problem, problem_id)
    try:
        require_open(comp)
        if not team or team.competition_id != comp_id:
            raise InputError("La squadra scelta non esiste in questa gara.")
        if not problem or problem.competition_id != comp_id:
            raise InputError("Il problema scelto non esiste in questa gara.")
        answer = _risposta(answer)
    except InputError as e:
        filtri = _filtri(request)
        url = f"/inserimento/{comp_id}/consegne/{sub_id}/modifica" + (f"?{filtri}" if filtri else "")
        return _torna(url, f"Modifica non salvata. {e}")
    sub.team_id = team_id
    sub.problem_id = problem_id
    sub.answer = answer
    sub.is_correct = answer == problem.answer
    db.commit()
    state_cache.invalidate(comp_id)
    return RedirectResponse(_consegne_url(comp_id, request), status_code=303)


@router.post("/{comp_id}/consegne/aggiungi")
async def inserimento_aggiungi_consegna(
    request: Request,
    comp_id: int,
    team_id: int = Form(...),
    problem_id: int = Form(...),
    answer: str = Form(...),
    minutes: str = Form(""),
    seconds: str = Form(""),
    db: Session = Depends(get_db),
):
    """Solo Admin: aggiunge una consegna dimenticata con il suo tempo di gara.

    I punteggi si ricalcolano sempre da capo in ordine di tempo, quindi una consegna inserita nel
    passato cambia correttamente valori e bonus da quel momento in poi."""
    if not request.state.is_local:
        raise HTTPException(status_code=403, detail="Solo l'Admin può aggiungere consegne con il tempo")
    comp = get_comp_or_404(comp_id, db)
    team = db.get(Team, team_id)
    problem = db.get(Problem, problem_id)
    try:
        require_started(comp)
        if not team or team.competition_id != comp_id:
            raise InputError("La squadra scelta non esiste in questa gara.")
        if not problem or problem.competition_id != comp_id:
            raise InputError("Il problema scelto non esiste in questa gara.")
        answer = _risposta(answer)
        m, s = minutes.strip() or "0", seconds.strip() or "0"
        if not (m.isdigit() and s.isdigit()):
            raise InputError("Il tempo di gara va indicato in minuti e secondi (solo cifre).")
        if int(s) > 59:
            raise InputError("I secondi devono essere da 0 a 59.")
        game_sec = int(m) * 60 + int(s)
        limite = min(comp.duration_minutes * 60.0, comp.elapsed_seconds())
        if game_sec > limite:
            raise InputError(f"Il tempo indicato ({formato.mmss(game_sec)}) è oltre il tempo di gara attuale "
                             f"({formato.mmss(limite)}).")
    except InputError as e:
        return _torna(_consegne_url(comp_id, request), f"Consegna non aggiunta. {e}")

    db.add(Submission(
        competition_id=comp_id,
        team_id=team.id,
        problem_id=problem.id,
        answer=answer,
        is_correct=answer == problem.answer,
        is_post_game=False,
        game_seconds=float(game_sec),
        device_id=request.state.device_id,
        added_by_admin=True,
    ))
    db.commit()
    state_cache.invalidate(comp_id)
    esito = (f"Consegna aggiunta: squadra {team.number:02d}, problema {problem.number:02d}, "
             f"risposta {answer} ({'corretta' if answer == problem.answer else 'errata'}) al minuto {formato.mmss(game_sec)}.")
    url = _consegne_url(comp_id, request)
    return RedirectResponse(f"{url}{'&' if '?' in url else '?'}esito={quote(esito)}", status_code=303)
