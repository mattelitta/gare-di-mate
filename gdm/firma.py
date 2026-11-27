"""Firma dello stato mostrato da una pagina, per l'aggiornamento automatico.

Le pagine di Admin, Regia e l'elenco delle gare dell'Inserimento conoscono la firma dello stato con
cui sono state disegnate; ogni 2 secondi la richiedono di nuovo al server (base.html) e, se è
cambiata (gara avviata, messa in pausa, oscurata allo scattare del minuto, terminata allo scadere,
classifica finale calcolata, cambiamenti fatti da un'altra finestra...), si ricaricano da sole.
La firma contiene solo ciò che cambia l'aspetto della pagina: non il tempo che scorre (ci pensa
il cronometro nella pagina) né l'ultimo contatto dei display, ma sì chi è collegato a ciascuno.
"""
import hashlib

from gdm import collegamenti
from gdm.models import AccessSession, Competition


def _h(*parti) -> str:
    return hashlib.sha1("|".join(map(str, parti)).encode()).hexdigest()[:16]


def gara(comp: Competition, regia: bool = False) -> str:
    """Pagina di una gara (Admin; con regia=True anche i display della Regia)."""
    parti = [comp.name, comp.date, comp.status, comp.blackout_active(), comp.blackout_manual,
             comp.is_archived(), comp.archived_manual, comp.final_computed_at, comp.revealed_positions, comp.recovery_crash_at,
             round(comp.time_offset_seconds or 0.0, 3), len(comp.time_adjustments), len(comp.penalties),
             len(comp.teams), len(comp.problems)]
    if regia:
        # anche chi è collegato a ogni display: la regia si aggiorna quando un dispositivo si collega o va via
        parti += [(d.id, d.name, d.current_view, d.text_scale, d.internal,
                   d.rotation_enabled, d.rotation_views_json, d.rotation_seconds, tuple(collegamenti.collegati(d.id)))
                  for d in sorted(comp.displays, key=lambda d: d.id)]
    return _h(*parti)


def elenco(db, sessioni: bool = False) -> str:
    """Elenco delle gare (home di Admin, Regia, Inserimento); per l'Admin anche i dispositivi collegati."""
    parti = [(c.id, c.name, c.date, c.status, c.recovery_crash_at is not None, c.is_archived())
             for c in db.query(Competition).order_by(Competition.id)]
    if sessioni:
        parti.append(db.query(AccessSession).count())
    return _h(*parti)
