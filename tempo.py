"""Tempo di gara: battito del server, ripresa dopo una chiusura del programma, avanzamento manuale."""
from datetime import datetime

from models import Competition, TimeAdjustment


def heartbeat(db, now: datetime | None = None):
    """Chiamato ogni secondo: registra che il server è attivo per le gare in corso."""
    db.query(Competition).filter(Competition.status == "running").update(
        {Competition.last_alive_at: now or datetime.utcnow()}, synchronize_session=False
    )
    db.commit()


def recover_after_restart(db, now: datetime | None = None) -> int:
    """All'avvio del server: le gare rimaste "in corso" riprendono dal minuto raggiunto.

    Il tempo tra l'ultimo battito e la riapertura viene trattato come una pausa; durata e ora
    della chiusura restano salvate finché l'admin non decide se avanzare il tempo.
    Ritorna il numero di gare riprese.
    """
    now = now or datetime.utcnow()
    recovered = 0
    for comp in db.query(Competition).filter(Competition.status == "running"):
        if comp.last_alive_at is None:
            continue
        downtime = max(0.0, (now - comp.last_alive_at).total_seconds())
        comp.total_paused_seconds += downtime
        # Il battito è al secondo: non ripartire prima dell'ultima consegna o jolly registrati.
        latest = max((x.game_seconds for x in [*comp.submissions, *comp.jolly_choices]), default=0.0)
        behind = latest - comp.elapsed_seconds()
        if behind > 0:
            comp.total_paused_seconds -= behind
        if comp.recovery_crash_at is None:
            comp.recovery_crash_at = comp.last_alive_at
        # Più chiusure prima della risposta dell'admin si sommano.
        comp.recovery_downtime_seconds = (comp.recovery_downtime_seconds or 0.0) + downtime
        comp.last_alive_at = now
        recovered += 1
    db.commit()
    return recovered


def max_advance(comp: Competition) -> float:
    """Il tempo si può avanzare al massimo fino alla fine della gara."""
    return max(0.0, comp.duration_minutes * 60 - comp.elapsed_seconds())


def advance(comp: Competition, seconds: float, reason: str = "manuale") -> float:
    """Fa avanzare il tempo di gara e registra l'avanzamento; ritorna i secondi applicati."""
    applied = max(0.0, min(seconds, max_advance(comp)))
    if applied > 0:
        comp.time_adjustments.append(
            TimeAdjustment(seconds=applied, game_seconds_at=comp.elapsed_seconds(), reason=reason))
        comp.time_offset_seconds = (comp.time_offset_seconds or 0.0) + applied
    return applied


def change_adjustment(comp: Competition, adj: TimeAdjustment, new_seconds: float):
    """Corregge un avanzamento già fatto (0 = annullarlo).

    La differenza si applica al tempo attuale e a consegne, jolly e avanzamenti registrati
    dopo quell'avanzamento, come se fosse stato fatto fin dall'inizio della durata corretta.
    Le consegne post-gara restano alla fine della gara. Solleva ValueError con un messaggio
    per l'utente se la correzione non è possibile.
    """
    if comp.final_locked:
        raise ValueError("La classifica finale è bloccata: gli avanzamenti non si possono più modificare.")
    if new_seconds < 0:
        raise ValueError("Un avanzamento non può essere negativo.")
    delta = new_seconds - adj.seconds
    if delta == 0:
        return
    if comp.elapsed_seconds() + delta > comp.duration_minutes * 60 + 0.5:
        raise ValueError("Con questa modifica il tempo di gara supererebbe la fine della gara.")
    # Tutto ciò che è stato registrato dopo l'avanzamento ha tempo >= game_seconds_at + seconds,
    # tutto ciò che è venuto prima ha tempo <= game_seconds_at: la soglia a metà li separa.
    soglia = adj.game_seconds_at + adj.seconds / 2
    for ev in [*comp.submissions, *comp.jolly_choices]:
        if getattr(ev, "is_post_game", False):
            continue
        if ev.game_seconds > soglia:
            ev.game_seconds = max(adj.game_seconds_at, ev.game_seconds + delta)
    for other in comp.time_adjustments:
        if other is not adj and other.game_seconds_at > soglia:
            other.game_seconds_at += delta
    comp.time_offset_seconds = (comp.time_offset_seconds or 0.0) + delta
    adj.seconds = new_seconds


def remove_adjustment(comp: Competition, adj: TimeAdjustment):
    change_adjustment(comp, adj, 0.0)
    comp.time_adjustments.remove(adj)


def clear_recovery(comp: Competition):
    comp.recovery_crash_at = None
    comp.recovery_downtime_seconds = None
