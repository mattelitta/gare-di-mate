"""
Crea una gara di prova pronta per il test manuale.
Durata 10 min, jolly a 5 min, 3 squadre + 1 ospite, 4 problemi.
La gara è in stato "created" — avviarla dall'interfaccia admin.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, init_db
from models import Competition, Team, Problem

init_db()
db = SessionLocal()

comp = Competition(
    name="Gara di Prova",
    date="2026-05-29",
    initial_value=40,
    n=2,
    k=1,
    first_delivery_bonuses_json="[20, 15, 10, 5]",
    full_bonuses_json="[50, 30, 20]",
    duration_minutes=10,
    jolly_time_minutes=5,
    threshold_minute=8,
    blackout_minute=7,
    num_qualified=2,
    final_reveal_count=3,
    password=None,
    status="created",
)
db.add(comp)
db.flush()

teams = [
    (1, "Pitagora", "Bologna",  False),
    (2, "Eulero",   "Milano",   False),
    (3, "Gauss",    "Roma",     False),
    (4, "Ospiti",   "Estero",   True),
]
for number, name, city, is_guest in teams:
    db.add(Team(competition_id=comp.id, number=number,
                name=name, city=city, is_guest=is_guest))

problems = [
    (1, "Algebra",      "0042"),
    (2, "Geometria",    "0137"),
    (3, "Combinatoria", "1024"),
    (4, "Teoria Num.",  "0007"),
]
for number, name, answer in problems:
    db.add(Problem(competition_id=comp.id, number=number,
                   name=name, answer=answer))

db.commit()
print(f"Gara creata (ID={comp.id}), status=created")
print(f"Risposte: P1=0042  P2=0137  P3=1024  P4=0007")
print(f"Admin: http://localhost:8000/admin/gara/{comp.id}")
db.close()
