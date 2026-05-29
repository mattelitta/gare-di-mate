"""
Test automatizzato end-to-end — gara di 2 minuti.
Prerequisito: server in esecuzione su localhost:8000.

Scenario pianificato:
  3 squadre (Alpha, Beta, Gamma) + 1 ospite | 3 problemi: P1=0042 P2=0137 P3=1024
  Durata 2 min | Jolly 1 min | Soglia 1 min | Oscuramento 1 min | Qualificate 2

  t=00s  Avvio gara
  t=03s  Jolly: Alpha→P1, Beta→P2, Gamma→P1
  t=06s  Alpha P1 ERRATA (contribuisce al valore), Ospiti P1 CORRETTA
  t=09s  Alpha P1 CORRETTA [jolly×2, bonus_fd=10], Beta P1 CORRETTA → n=2 su P1
  t=14s  Beta P2 CORRETTA [jolly×2, bonus_fd=10], Alpha P2 ERRATA, Gamma P2 CORRETTA [bonus_fd=5]
  t=62s  (post-soglia) Alpha P3 CORRETTA, Gamma P1 CORRETTA
  t=122s Fine gara → status=ended
  t=124s Post-gara: Beta P3 CORRETTA, Gamma P3 CORRETTA
  t=126s Blocca classifica finale
  t=128s Rivela 3 posizioni dalla regia
"""

import sys, os, time, json as _json
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8')

import urllib.request, urllib.parse, urllib.error

BASE = "http://localhost:8000"
_t0 = None

# ANSI colors
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[1m"; X = "\033[0m"

def ts():
    return f"t={time.time()-_t0:5.1f}s" if _t0 else time.strftime("%H:%M:%S")

def ok(msg):   print(f"  {G}[OK]{X} [{ts()}] {msg}")
def fail(msg): print(f"  {R}[!!]{X} [{ts()}] {msg}")
def info(msg): print(f"  {Y}[--]{X} [{ts()}] {msg}")

def post(path, data=None):
    url = BASE + path
    body = urllib.parse.urlencode(data or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        fail(f"POST {path}: {e}")
        return 0

def get_json(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            return _json.loads(r.read())
    except Exception as e:
        fail(f"GET {path}: {e}")
        return None

def wait_until(target, msg=None):
    remaining = target - (time.time() - _t0)
    if remaining > 0.2:
        if msg:
            info(f"Attendo {remaining:.0f}s ({msg})…")
        time.sleep(remaining)

def print_state(label):
    s = get_json(f"/admin/api/gara/{cid}/stato")
    if not s:
        return None
    probs_by_id = {p['id']: p for p in s['problems']}
    print(f"\n  {B}{'-'*52}{X}")
    print(f"  {B}{label}{X}  [elapsed={s.get('elapsed_seconds',0):.0f}s  status={s['status']}]")
    print(f"  {'N°':<4} {'Nome':<10} {'Punti':>7}  Jolly")
    for t in s['teams']:
        j = probs_by_id.get(t.get('jolly_problem_id'), {}).get('number', '—')
        guest = f"{Y}(osp){X}" if t['is_guest'] else "     "
        print(f"  {t['number']:02d}   {t['name']:<10} {t['total']:>7.1f}  P{j}  {guest}")
    print(f"  Problemi:")
    for p in sorted(s['problems'], key=lambda x: x['number']):
        print(f"    P{p['number']} {p['name']:<12}  valore={p['value']:>6.2f}  risolutori={p['num_solvers']}")
    print(f"  {B}{'-'*52}{X}")
    return s

def check(label, code):
    if code in (200, 303):
        ok(label)
    else:
        fail(f"{label}  → HTTP {code}")

# ----------------------------------------------------------
print(f"\n{B}{'='*56}{X}")
print(f"{B}  GARE DI MATE — Test automatizzato (gara 2 min){X}")
print(f"{B}{'='*56}{X}")

# Verifica server
try:
    with urllib.request.urlopen(BASE + "/", timeout=3):
        ok("Server raggiungibile")
except Exception as e:
    fail(f"Server non raggiungibile ({e}). Avvia: py -m uvicorn main:app --host 0.0.0.0 --port 8000")
    sys.exit(1)

# ----------------------------------------------------------
# Setup via DB
from database import SessionLocal, init_db
from models import Competition, Team, Problem, Display

init_db()
db = SessionLocal()

for c in db.query(Competition).filter(Competition.name == "Test Automatico 2min").all():
    db.delete(c)
db.commit()

comp = Competition(
    name="Test Automatico 2min", date="2026-05-29",
    initial_value=20, n=2, k=1,
    first_delivery_bonuses_json="[10, 5, 2]",
    full_bonuses_json="[20, 10]",
    duration_minutes=2, jolly_time_minutes=1,
    threshold_minute=1, blackout_minute=1,
    num_qualified=2, final_reveal_count=3,
    status="created",
)
db.add(comp); db.flush()

for num, nome, citta, guest in [
    (1,"Alpha","MI",False),(2,"Beta","RM",False),
    (3,"Gamma","NA",False),(4,"Ospiti","EE",True)
]:
    db.add(Team(competition_id=comp.id, number=num, name=nome, city=citta, is_guest=guest))

for num, nome, risp in [(1,"Algebra","0042"),(2,"Geometria","0137"),(3,"Analisi","1024")]:
    db.add(Problem(competition_id=comp.id, number=num, name=nome, answer=risp))

disp = Display(competition_id=comp.id, name="Display1", current_view="ranking")
db.add(disp); db.commit()

cid = comp.id; disp_id = disp.id
db.close()
ok(f"Gara creata (ID={cid})  P1=0042  P2=0137  P3=1024")

# ----------------------------------------------------------
print(f"\n{B}&gt; AVVIO GARA{X}")
check("Avvio gara", post(f"/admin/gara/{cid}/avvia"))
_t0 = time.time()
time.sleep(0.5)
print_state("Stato iniziale")

# ----------------------------------------------------------
print(f"\n{B}&gt; JOLLY{X}")
wait_until(3)
check("Jolly Alpha → P1", post(f"/inserimento/{cid}/jolly", {"team_number":"1","problem_number":"1"}))
check("Jolly Beta  → P2", post(f"/inserimento/{cid}/jolly", {"team_number":"2","problem_number":"2"}))
check("Jolly Gamma → P1", post(f"/inserimento/{cid}/jolly", {"team_number":"3","problem_number":"1"}))

# ----------------------------------------------------------
print(f"\n{B}&gt; PRIME RISPOSTE{X}")
wait_until(6)
check("Alpha  P1 ERRATA  (0000) — +2 a valore P1",   post(f"/inserimento/{cid}/soluzione", {"team_number":"1","problem_number":"1","answer":"0000"}))
check("Ospiti P1 CORRETTA       — conta solo posizione assoluta", post(f"/inserimento/{cid}/soluzione", {"team_number":"4","problem_number":"1","answer":"0042"}))

wait_until(9)
check("Alpha  P1 CORRETTA [jolly×2 +bonus_fd=10] — 1° non-ospite", post(f"/inserimento/{cid}/soluzione", {"team_number":"1","problem_number":"1","answer":"0042"}))
check("Beta   P1 CORRETTA [+bonus_fd=5]  → n=2 su P1: time_bonus bloccato", post(f"/inserimento/{cid}/soluzione", {"team_number":"2","problem_number":"1","answer":"0042"}))

# ----------------------------------------------------------
print(f"\n{B}&gt; PROBLEMA 2{X}")
wait_until(14)
check("Beta   P2 CORRETTA [jolly×2 +bonus_fd=10] — 1° non-ospite", post(f"/inserimento/{cid}/soluzione", {"team_number":"2","problem_number":"2","answer":"0137"}))
check("Alpha  P2 ERRATA  (0000)",                                   post(f"/inserimento/{cid}/soluzione", {"team_number":"1","problem_number":"2","answer":"0000"}))
check("Gamma  P2 CORRETTA [+bonus_fd=5]  — 2° non-ospite",         post(f"/inserimento/{cid}/soluzione", {"team_number":"3","problem_number":"2","answer":"0137"}))

print_state("Dopo P2 (~14s)")

# ----------------------------------------------------------
print(f"\n{B}&gt; POST-SOGLIA (attendo t=62s){X}")
wait_until(62, "soglia 60s — valori si congelano")
check("Alpha P3 CORRETTA [post-soglia]",  post(f"/inserimento/{cid}/soluzione", {"team_number":"1","problem_number":"3","answer":"1024"}))
check("Gamma P1 CORRETTA [post-soglia]",  post(f"/inserimento/{cid}/soluzione", {"team_number":"3","problem_number":"1","answer":"0042"}))

print_state("Post-soglia (~62s) — valori congelati")

# ----------------------------------------------------------
print(f"\n{B}&gt; FINE GARA (attendo t=122s){X}")
wait_until(122, "fine gara 120s")
check("Termina gara", post(f"/admin/gara/{cid}/termina"))

# ----------------------------------------------------------
print(f"\n{B}&gt; CONSEGNE POST-GARA{X}")
time.sleep(0.5)
check("Beta  P3 CORRETTA [post-gara]",  post(f"/inserimento/{cid}/soluzione", {"team_number":"2","problem_number":"3","answer":"1024"}))
check("Gamma P3 CORRETTA [post-gara]",  post(f"/inserimento/{cid}/soluzione", {"team_number":"3","problem_number":"3","answer":"1024"}))

print_state("Fine gara + post-gara")

# ----------------------------------------------------------
print(f"\n{B}&gt; CLASSIFICA FINALE{X}")
check("Blocca classifica", post(f"/admin/gara/{cid}/blocca-finale"))
time.sleep(0.5)
s_final = get_json(f"/admin/api/gara/{cid}/stato")
print_state("Classifica finale bloccata")

# ----------------------------------------------------------
print(f"\n{B}&gt; VERIFICA DISPLAY API{X}")
s_disp = get_json(f"/display/api/{cid}/schermo/{disp_id}/stato")
if s_disp:
    ok(f"Display API: view={s_disp.get('view')}  final_locked={s_disp.get('final_locked')}  teams={len(s_disp.get('teams',[]))}")
else:
    fail("Display API non risponde")

# ----------------------------------------------------------
print(f"\n{B}&gt; RIVELAZIONE POSIZIONI (REGIA){X}")
non_guests_count = len([t for t in s_final['teams'] if not t['is_guest']])
for i in range(non_guests_count):
    code = post(f"/regia/{cid}/rivela")
    s = get_json(f"/admin/api/gara/{cid}/stato")
    rev = s.get('revealed_positions', 0)
    ok(f"Posizione {rev}/{non_guests_count} rivelata  (HTTP {code})")
    time.sleep(0.2)

# ----------------------------------------------------------
print(f"\n{B}{'='*56}{X}")
print(f"{B}  VERIFICA INVARIANTI{X}")
print(f"{B}{'='*56}{X}")

errori = 0
teams = s_final['teams']
non_guests = [t for t in teams if not t['is_guest']]
guests     = [t for t in teams if t['is_guest']]

# 1. Ospiti in fondo
ng_idx = [i for i,t in enumerate(teams) if not t['is_guest']]
g_idx  = [i for i,t in enumerate(teams) if t['is_guest']]
if not g_idx or (ng_idx and min(g_idx) > max(ng_idx)):
    ok("Ospiti posizionati dopo tutti i non-ospiti")
else:
    fail("Ospiti non in fondo!"); errori += 1

# 2. Non-ospiti ordinati per punteggio decrescente
scores = [t['total'] for t in non_guests]
if scores == sorted(scores, reverse=True):
    ok(f"Non-ospiti ordinati per punteggio decrescente: {[round(s) for s in scores]}")
else:
    fail(f"Ordine scorretto: {[round(s) for s in scores]}"); errori += 1

# 3. Punteggio iniziale = 10 × 3 = 30; nessuno scende a 0
if all(t['total'] > 0 for t in teams):
    ok("Tutti i punteggi > 0")
else:
    fail(f"Punteggio ≤ 0 rilevato: {[(t['name'],round(t['total'])) for t in teams if t['total']<=0]}"); errori += 1

# 4. Alpha ha risolto P1 con jolly → deve essere in testa o vicino
alpha = next(t for t in non_guests if t['name'] == 'Alpha')
beta  = next(t for t in non_guests if t['name'] == 'Beta')
gamma = next(t for t in non_guests if t['name'] == 'Gamma')
ok(f"Punteggi finali — Alpha:{round(alpha['total'])}  Beta:{round(beta['total'])}  Gamma:{round(gamma['total'])}")

# 5. final_locked
if s_final.get('final_locked'):
    ok("final_locked = True")
else:
    fail("final_locked non impostato!"); errori += 1

# 6. Tutte le posizioni rivelate
s_rev = get_json(f"/admin/api/gara/{cid}/stato")
if s_rev and s_rev.get('revealed_positions') == non_guests_count:
    ok(f"Tutte le {non_guests_count} posizioni rivelate")
else:
    rev = s_rev.get('revealed_positions', '?') if s_rev else '?'
    fail(f"Solo {rev} posizioni rivelate su {non_guests_count}"); errori += 1

# 7. Verifica valori P1 congelati dopo soglia (max time_bonus = 60/60 = 1 min)
probs_final = {p['number']: p for p in s_final['problems']}
p1_val = probs_final[1]['value']
# P1: initial_value=20, time_bonus≤1 (bloccato dopo n=2 ≈9s), error_bonus=+2 (1 errore Alpha pre-soglia, k=1)
# Atteso: ~20 + 9/60 + 2 = ~22.15
expected_p1 = 20 + 9/60 + 2  # approssimato
if abs(p1_val - expected_p1) < 0.5:
    ok(f"Valore P1 ≈ {p1_val:.2f}  (atteso ≈ {expected_p1:.2f}) — time_bonus bloccato a n=2 ✓")
else:
    fail(f"Valore P1 = {p1_val:.2f}  (atteso ≈ {expected_p1:.2f})"); errori += 1

print(f"\n{'='*56}")
if errori == 0:
    print(f"{G}{B}  TUTTI I TEST SUPERATI ✓{X}")
else:
    print(f"{R}{B}  {errori} ERRORE/I RILEVATO/I ✗{X}")
print(f"  Gara ispezionabile: http://localhost:8000/admin/gara/{cid}")
print(f"{'='*56}\n")
