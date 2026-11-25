"""Valori dei problemi e punteggi sempre interi; il bonus a tempo scatta a ogni minuto intero."""
from datetime import datetime
from types import SimpleNamespace as NS

from _util import check, finish
from engine import compute_state


def comp(submissions=(), threshold_minute=60, n=2):
    return NS(
        threshold_minute=threshold_minute, n=n, k=1, initial_value=40, starting_score=None,
        first_delivery_bonuses=[20, 10], full_bonuses=[50],
        teams=[NS(id=i, number=i, name=f"S{i}", city="", is_guest=False) for i in (1, 2, 3)],
        problems=[NS(id=1, number=1, name="P1")], jolly_choices=[], penalties=[],
        submissions=[NS(team_id=t, problem_id=1, is_correct=ok, game_seconds=s,
                        submitted_at=datetime(2026, 1, 1), is_post_game=False) for t, ok, s in submissions],
        elapsed_seconds=lambda: 0.0,
    )


def value(c, at):
    return compute_state(c, at_seconds=at)[0][1].value


c = comp()
for at, atteso in [(0, 40), (30, 40), (59.9, 40), (60.0, 41), (89.5, 41), (119.99, 41), (120, 42), (599.5, 49)]:
    check(f"a {at:>6} s il valore è {atteso}", value(c, at) == atteso, str(value(c, at)))
check("bloccato all'n-esima soluzione (9:40) → +9",
      value(comp([(1, True, 100), (2, True, 580)]), 900) == 49)
check("bloccato al minuto soglia (5) anche a 10 min → +5", value(comp(threshold_minute=5), 600) == 45)

probs, teams = compute_state(comp([(1, True, 100), (2, False, 130), (2, True, 580), (3, True, 700)]),
                             at_seconds=1234.567)
tipi = {type(probs[1].value)} | {type(t.total) for t in teams.values()} | \
       {type(v) for t in teams.values() for v in t.problem_contributions.values()}
check("valori, contributi e totali sono tutti int", tipi == {int}, str(tipi))
finish()
