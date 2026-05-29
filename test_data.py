"""
Script di test: crea una gara di prova con dati realistici e verifica i calcoli.
Cancella eventuali dati precedenti di test prima di inserire.

Parametri gara di test:
  - 4 problemi, 5 squadre (+ 1 ospite)
  - valore_iniziale=40, n=2, k=1
  - bonus_prima_consegna=[20,15,10,5,3], bonus_full=[50,30,20]
  - durata=90min, soglia=70min, jolly_time=30min
  - Gara simulata al minuto 45 (2700s)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from database import SessionLocal, init_db
from models import Competition, Team, Problem, Submission, JollyChoice, Penalty
from engine import compute_state, rank_teams

init_db()
db = SessionLocal()

# --- Pulizia dati di test precedenti ---
old = db.query(Competition).filter(Competition.name == "[TEST] Gara di Prova").first()
if old:
    db.delete(old)
    db.commit()
    print("Dati di test precedenti rimossi.")

# --- Crea gara ---
# Simuliamo una gara partita 45 minuti fa
now = datetime.utcnow()
started_at = now - timedelta(minutes=45)

comp = Competition(
    name="[TEST] Gara di Prova",
    date=now.strftime("%Y-%m-%d"),
    initial_value=40,
    n=2,
    k=1,
    first_delivery_bonuses_json="[20, 15, 10, 5, 3]",
    full_bonuses_json="[50, 30, 20]",
    duration_minutes=90,
    jolly_time_minutes=30,
    threshold_minute=70,
    blackout_minute=60,
    num_qualified=3,
    final_reveal_count=3,
    password=None,
    status="running",
    started_at=started_at,
    total_paused_seconds=0.0,
)
db.add(comp)
db.flush()

# --- Squadre ---
teams_data = [
    (1, "Pitagora", "Bologna",  False),
    (2, "Eulero",   "Milano",   False),
    (3, "Gauss",    "Roma",     False),
    (4, "Fermat",   "Napoli",   False),
    (5, "Newton",   "Torino",   False),
    (6, "Ospiti",   "Estero",   True),
]
teams = {}
for number, name, city, is_guest in teams_data:
    t = Team(competition_id=comp.id, number=number, name=name, city=city, is_guest=is_guest)
    db.add(t)
    db.flush()
    teams[number] = t

# --- Problemi ---
# Risposta sempre 4 cifre
problems_data = [
    (1, "Algebra",      "0042"),
    (2, "Geometria",    "0137"),
    (3, "Combinatoria", "1024"),
    (4, "Teoria Num.",  "0007"),
]
problems = {}
for number, name, answer in problems_data:
    p = Problem(competition_id=comp.id, number=number, name=name, answer=answer)
    db.add(p)
    db.flush()
    problems[number] = p

# --- Jolly ---
# Squadra 1 → problema 1 (al minuto 5)
# Squadra 2 → problema 3 (al minuto 8)
# Squadra 3 → problema 2 (al minuto 12)
# Squadra 4 → problema 4 (al minuto 7)
# Squadra 5 → problema 1 (al minuto 10)
# Squadra 6 (ospite) → problema 2 (al minuto 15)
jolly_assignments = [
    (1, 1, 5),
    (2, 3, 8),
    (3, 2, 12),
    (4, 4, 7),
    (5, 1, 10),
    (6, 2, 15),
]
for team_n, prob_n, minute in jolly_assignments:
    db.add(JollyChoice(
        competition_id=comp.id,
        team_id=teams[team_n].id,
        problem_id=problems[prob_n].id,
        game_seconds=minute * 60.0,
        submitted_at=started_at + timedelta(minutes=minute),
    ))

# --- Consegne ---
# Formato: (team_n, prob_n, answer, minute_of_game)
# Le risposte corrette sono: P1=0042, P2=0137, P3=1024, P4=0007
submissions_data = [
    # Problema 1 (Algebra): risolto da sq1(jolly), sq2, sq3. Errore sq4.
    (1, 1, "0099", 10),   # sq1 sbaglia P1 (k=1 → conta per valore)
    (2, 1, "0042", 15),   # sq2 risolve P1 per prima → bonus[0]=20
    (1, 1, "0042", 18),   # sq1 risolve P1 per seconda (jolly!) → bonus[1]=15, x2
    (3, 1, "0042", 22),   # sq3 risolve P1 per terza → bonus[2]=10
    (4, 1, "0099", 30),   # sq4 sbaglia P1 (k=1 → conta per valore, ma dopo soglia no)

    # Problema 2 (Geometria): risolto da sq3(jolly), sq1. Errori sq2, sq5.
    (2, 2, "0000", 5),    # sq2 sbaglia P2
    (5, 2, "0001", 8),    # sq5 sbaglia P2
    (3, 2, "0137", 20),   # sq3 risolve P2 per prima (jolly!) → bonus[0]=20, x2
    (1, 2, "0137", 35),   # sq1 risolve P2 per seconda → bonus[1]=15

    # Problema 3 (Combinatoria): risolto da sq2(jolly). Errore sq1.
    (1, 3, "9999", 12),   # sq1 sbaglia P3
    (2, 3, "1024", 25),   # sq2 risolve P3 per prima (jolly!) → bonus[0]=20, x2

    # Problema 4 (Teoria Num.): nessuno lo risolve ancora. Errori sq3, sq4(jolly).
    (3, 4, "0001", 20),   # sq3 sbaglia P4
    (4, 4, "0001", 25),   # sq4 sbaglia P4 (jolly!) → -10 x2

    # Ospite: risolve P2 (jolly) e sbaglia P1
    (6, 2, "0137", 30),   # ospite risolve P2 (jolly!) → bonus[2]=10, x2
    (6, 1, "0000", 35),   # ospite sbaglia P1
]

for team_n, prob_n, answer, minute in submissions_data:
    is_correct = answer == problems[prob_n].answer
    db.add(Submission(
        competition_id=comp.id,
        team_id=teams[team_n].id,
        problem_id=problems[prob_n].id,
        answer=answer,
        is_correct=is_correct,
        is_post_game=False,
        game_seconds=minute * 60.0,
        submitted_at=started_at + timedelta(minutes=minute),
    ))

# --- Penalizzazione ---
# Squadra 5 penalizzata -30
db.add(Penalty(
    competition_id=comp.id,
    team_id=teams[5].id,
    value=-30,
    note="Comportamento antisportivo (test)",
))

db.commit()
print(f"Gara creata: ID={comp.id}")

# ============================================================
# VERIFICA CALCOLI
# ============================================================
print("\n" + "="*60)
print("VERIFICA CALCOLI (t=45 min = 2700s)")
print("="*60)

# Ricarichiamo la gara tramite load_comp_full per avere eager loading
db.close()
db = SessionLocal()
from database import load_comp_full
comp_full = load_comp_full(comp.id, db)

AT = 45 * 60  # 2700 secondi
prob_states, team_scores = compute_state(comp_full, at_seconds=AT)

# --- Valori problemi attesi ---
print("\n--- Valori problemi (attesi) ---")
# P1: t_stop = min(70min, 45min, t_2°_risolutore=22min) = 22min
#     time_bonus = 22
#     error_bonus: sq1 ha 1 errore pre-soglia → min(1,1)*2=2; sq4 ha 1 errore a 30min (pre-soglia) → 2
#     valore = 40 + 22 + 4 = 66
# P2: t_stop = min(70, 45, t_2°_risolutore=35min) = 35min
#     time_bonus = 35
#     error_bonus: sq2 (1 errore a 5min) → 2; sq5 (1 errore a 8min) → 2
#     valore = 40 + 35 + 4 = 79
# P3: t_stop = min(70, 45, mai 2 risolutori) = 45min
#     time_bonus = 45
#     error_bonus: sq1 (1 errore a 12min) → 2
#     valore = 40 + 45 + 2 = 87
# P4: t_stop = min(70, 45, mai) = 45min
#     time_bonus = 45
#     error_bonus: sq3 (1 err a 20min) → 2; sq4 (1 err a 25min) → 2
#     valore = 40 + 45 + 4 = 89
# Ospiti esclusi da n e da contributo errori al valore
# P1: nth_solver=sq1(min18, non-ospite) → time=18; errori non-ospite: sq1(min10)+sq4(min30)=2 → err=4; 40+18+4=62
# P2: nth_solver=sq1(min35, non-ospite, 2° non-ospite dopo sq3) → time=35; errori non-ospite: sq2+sq5=2 → err=4; 40+35+4=79
# P3: nessun 2° risolutore non-ospite → time=45; errori: sq1(min12)=1 → err=2; 40+45+2=87
# P4: nessun risolutore → time=45; errori: sq3+sq4=2 → err=4; 40+45+4=89
expected_values = {1: 62, 2: 79, 3: 87, 4: 89}

for pid, ps in sorted(prob_states.items(), key=lambda x: x[1].number):
    exp = expected_values[ps.number]
    match = "OK" if abs(ps.value - exp) < 0.1 else f"ERRORE (atteso {exp})"
    print(f"  P{ps.number} {ps.name}: {ps.value:.1f} {match}")

print("\n--- Punteggi squadre ---")
print(f"  Punteggio iniziale: 10 × 4 problemi = 40")
print()

# Calcoli attesi:
# Sq1 (jolly=P1):
#   P1(jolly): (66 + 15 - 10*1) * 2 = (66+15-10)*2 = 71*2 = 142
#   P2: (79 + 15 - 10*0) * 1 = 94
#   P3: (-10*1) * 1 = -10
#   P4: 0
#   total = 40 + 142 + 94 - 10 + 0 = 266
#
# Sq2 (jolly=P3):
#   P1: (66 + 20 - 10*0) = 86
#   P2: (-10*1) = -10
#   P3(jolly): (87 + 20 - 10*0) * 2 = 107*2 = 214
#   P4: 0
#   total = 40 + 86 - 10 + 214 = 330
#
# Sq3 (jolly=P2):
#   P1: (66 + 10) = 76
#   P2(jolly): (79 + 20) * 2 = 99*2 = 198
#   P3: 0
#   P4: (-10) = -10
#   total = 40 + 76 + 198 - 10 = 304
#
# Sq4 (jolly=P4):
#   P1: (-10) = -10
#   P2: 0
#   P3: 0
#   P4(jolly): (-10*1) * 2 = -20
#   total = 40 - 10 - 20 = 10
#
# Sq5 (jolly=P1, penalità=-30):
#   P1(jolly): 0 (non risolto, 0 errori su P1) = 0
#   P2: (-10) = -10  [ha sbagliato P2]
#   penalità: -30
#   total = 40 + 0 - 10 - 30 = 0  (penalità già inclusa)
#   wait: sq5 non ha consegne su P1, solo su P2 (sbagliato)
#   total = 40 + 0(P1 jolly, non risolto, 0 errori) - 10(P2) + 0 + 0 - 30 = 0
#
# Ospite (jolly=P2):
#   P1: (-10) = -10
#   P2(jolly): (79 + 10) * 2 = 89*2 = 178
#   total = 40 - 10 + 178 = 208

# P2 solvers: sq3(min20), ospite(min30), sq1(min35)
#   sq3 non-ospite → non_guest_idx=0 → fd[0]=20
#   ospite → abs_idx=1 → fd[1]=15
#   sq1 non-ospite → non_guest_idx=1 → fd[1]=15  (ospite non occupa il posto)
# Pitagora(jolly=P1): P1(62+15-10)*2=134 + P2(79+15)=94 + P3(-10) = 40+134+94-10 = 258
# Eulero(jolly=P3):   P1(62+20)=82 + P2(-10) + P3(87+20)*2=214 = 40+82-10+214 = 326
# Gauss(jolly=P2):    P1(62+10)=72 + P2(79+20)*2=198 + P4(-10) = 40+72+198-10 = 300
# Fermat(jolly=P4):   P1(-10) + P4(-10)*2=-20 = 40-10-20 = 10
# Newton(jolly=P1):   P2(-10) + penalita(-30) = 40-10-30 = 0
# Ospiti(jolly=P2):   P1(-10) + P2(79+15)*2=188 = 40-10+188 = 218
expected_totals = {
    "Pitagora": 258,
    "Eulero":   326,
    "Gauss":    300,
    "Fermat":   10,
    "Newton":   0,
    "Ospiti":   218,
}

ranked = rank_teams(team_scores, comp_full)
all_ok = True
for ts in ranked:
    exp = expected_totals.get(ts.name, "?")
    if isinstance(exp, int):
        match = "OK" if abs(ts.total - exp) < 0.1 else f"ERRORE (atteso {exp})"
        if "ERRORE" in match:
            all_ok = False
    else:
        match = "?"
    guest_tag = " [ospite]" if ts.is_guest else ""
    print(f"  {ts.name}{guest_tag}: {ts.total:.1f} {match}")
    # Dettaglio contributi
    for pid in sorted(ts.problem_contributions):
        ps = prob_states[pid]
        contrib = ts.problem_contributions[pid]
        jolly = " [jolly]" if ts.jolly_problem_id == pid else ""
        solved = "V" if ts.problem_solved[pid] else " "
        errs = ts.problem_errors[pid]
        print(f"      P{ps.number}{jolly}: {solved} contrib={contrib:+.1f}  errori={errs}")

print()
if all_ok:
    print(">>> Tutti i calcoli sono corretti!")
else:
    print(">>> ATTENZIONE: alcuni calcoli non corrispondono.")

db.close()
print(f"\nGara ID={comp.id} disponibile su http://localhost:8000/admin/gara/{comp.id}")
