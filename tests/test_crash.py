"""Crash veri (processo terminato di colpo) e avanzamento manuale del tempo. Lento: suite completa."""
import json
import re
import time

from _util import check, crash_server, db, finish, req, start_server


def elapsed(cid=1):
    return json.loads(req(f"/admin/api/gara/{cid}/stato")[2])["elapsed_seconds"]


def popup(html):
    return "Gara ripresa dopo una chiusura del programma" in html


p = start_server()
req("/admin/gara/1/avvia", {})
time.sleep(2.5)
a1 = db("SELECT last_alive_at FROM competitions WHERE id=1")[0][0]
time.sleep(2)
a2 = db("SELECT last_alive_at FROM competitions WHERE id=1")[0][0]
check("battito aggiornato ogni secondo a gara in corso", a1 and a2 and a2 > a1)

# --- crash 1: consegna subito prima, poi "Avanza il tempo" ---
time.sleep(0.6)
req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"})
e1 = elapsed()
crash_server(p)
time.sleep(8)
p = start_server()
e2 = elapsed()
check("dopo il crash la gara riprende dal minuto raggiunto (gli 8 s da spento non contano)",
      -1.2 <= e2 - e1 < 3, f"prima {e1:.1f}s, dopo {e2:.1f}s")
check("il tempo ripreso non è prima dell'ultima consegna",
      e2 >= db("SELECT MAX(game_seconds) FROM submissions")[0][0] - 0.05)
home = req("/admin/")[2]
check("popup nella home e nella pagina della gara", popup(home) and popup(req("/admin/gara/1")[2]))
m = re.search(r'name="minutes"[^>]*value="(\d+)"', home).group(1)
s = re.search(r'name="seconds"[^>]*value="(\d+)"', home).group(1)
proposta = int(m) * 60 + int(s)
check("proposta pari alla durata della chiusura", 7 <= proposta <= 11, f"{proposta} s")
before = elapsed()
st, h, _ = req("/admin/gara/1/ripresa", {"azione": "avanza", "minutes": m, "seconds": s, "torna": "home"})
check("'Avanza il tempo': avanza della durata proposta e torna alla home",
      h["location"] == "/admin/" and abs((elapsed() - before) - proposta) < 1.5)
check("popup chiuso dopo la risposta", not popup(req("/admin/")[2]))

# --- crash 2: "Riprendi senza avanzare" ---
e1 = elapsed()
crash_server(p)
time.sleep(4)
p = start_server()
check("secondo crash: ripresa dal minuto raggiunto", -1.2 <= elapsed() - e1 < 3)
before = elapsed()
req("/admin/gara/1/ripresa", {"azione": "ignora", "minutes": "", "seconds": "", "torna": "gara"})
check("'Riprendi senza avanzare': nessun salto, popup chiuso",
      elapsed() - before < 1.5 and not popup(req("/admin/gara/1")[2]))

# --- avanzamento manuale ---
before = elapsed()
req("/admin/gara/1/avanza-tempo", {"minutes": "2", "seconds": "30"})
check("avanza 2 min 30 s a gara in corso", abs((elapsed() - before) - 150) < 1.5)
g = req("/admin/gara/1")[2]
check("riquadro tempo con totale avanzato", 'id="tempo-gara"' in g and "Avanzato in totale" in g)
req("/admin/gara/1/pausa", {})
before = elapsed()
req("/admin/gara/1/avanza-tempo", {"minutes": "1", "seconds": ""})
mid = elapsed()
time.sleep(1.5)
check("avanza 1 min in pausa, poi il tempo resta fermo", abs((mid - before) - 60) < 0.5 and abs(elapsed() - mid) < 0.5)

# --- crash in pausa ---
e1 = elapsed()
crash_server(p)
time.sleep(3)
p = start_server()
check("crash in pausa: tempo invariato, nessun popup", abs(elapsed() - e1) < 0.5 and not popup(req("/admin/")[2]))
req("/admin/gara/1/avvia", {})
req("/admin/gara/1/avanza-tempo", {"minutes": "999", "seconds": "0"})
check("avanzare oltre la fine si ferma alla fine della gara", abs(elapsed() - 600) < 1.5)
for dati, nome in (({"minutes": "0", "seconds": "0"}, "zero"), ({"minutes": "-3", "seconds": "0"}, "negativo")):
    st, h, _ = req("/admin/gara/1/avanza-tempo", dati)
    check(f"avanzamento {nome} rifiutato con avviso", st == 303 and "errore=" in h["location"])
st, h, _ = req("/admin/crea", {"name": "Nuova", "date": "2026-12-01", "threshold_minute": "60", "blackout_minute": "80"})
nid = re.search(r"/gara/(\d+)/", h["location"]).group(1)
st, h, _ = req(f"/admin/gara/{nid}/avanza-tempo", {"minutes": "1", "seconds": "0"})
check("gara non iniziata: avanzamento rifiutato, nessun riquadro tempo",
      "errore=" in h["location"] and 'id="tempo-gara"' not in req(f"/admin/gara/{nid}")[2])
req("/inserimento/1/soluzione", {"team_number": "02", "problem_number": "01", "answer": "0042"})
check("le consegne dopo gli avanzamenti usano il tempo avanzato",
      db("SELECT MAX(game_seconds) FROM submissions WHERE competition_id=1")[0][0] >= 599)
crash_server(p)
finish()
