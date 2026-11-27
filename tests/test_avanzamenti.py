"""Avanzamenti del tempo: storico, correzione/eliminazione con spostamento delle consegne, limiti."""
import json
import re
import time

from _util import REMOTE, check, db, finish, opener, req, start_server, crash_server, skip

db("UPDATE competitions SET duration_minutes=90, threshold_minute=60, blackout_minute=80 WHERE id=1")
srv = start_server()


def elapsed():
    return json.loads(req("/admin/api/gara/1/stato")[2])["elapsed_seconds"]


def gs(answer):
    return db("SELECT game_seconds FROM submissions WHERE answer=?", (answer,))[0][0]


req("/admin/gara/1/avvia", {})
time.sleep(1)
req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "1111"})  # A, prima
time.sleep(1)
req("/admin/gara/1/avanza-tempo", {"minutes": "30", "seconds": "0"})  # "per sbaglio" 30 invece di 3
time.sleep(0.5)
req("/inserimento/1/soluzione", {"team_number": "02", "problem_number": "01", "answer": "2222"})  # B, dopo
a0, b0 = gs("1111"), gs("2222")
check("consegna dopo l'avanzamento registrata al tempo avanzato", b0 > 1800 and a0 < 5, f"A {a0:.1f}s, B {b0:.1f}s")
adj = db("SELECT id, seconds, reason FROM time_adjustments")
check("avanzamento salvato", len(adj) == 1 and adj[0][1] == 1800 and adj[0][2] == "manuale")
adj_id = adj[0][0]

st, _, b = req("/inserimento/1/consegne")
pos = [b.find("2222"), b.find("Tempo di gara avanzato di"), b.find("1111")]
check("storico: B, poi l'avanzamento, poi A (più recenti in alto)", -1 not in pos and pos == sorted(pos))
check("riga avanzamento con durata e 'da → a'", "30 min" in b and re.search(r"00:0\d → 30:0\d", b) is not None)
SOLO_ADMIN = '<span class="text-gray-400">Solo Admin</span>'  # la riga dell'avanzamento vista da un remoto
check("dal computer server: link 'Modifica in Admin'", "Modifica in Admin" in b and SOLO_ADMIN not in b)
team1 = db("SELECT id FROM teams WHERE competition_id=1 AND number=1")[0][0]
check("con un filtro attivo gli avanzamenti non compaiono",
      "Tempo di gara avanzato di" not in req(f"/inserimento/1/consegne?squadra={team1}")[2])
if REMOTE:
    r = opener()
    req("/admin/password-accesso", {"password": "segreta-123"})
    req("/accesso", {"password": "segreta-123", "next": "/"}, op=r, base=REMOTE)
    st, _, b = req("/inserimento/1/consegne", op=r, base=REMOTE)
    check("da un dispositivo in rete: riga visibile ma 'solo Admin'",
          "Tempo di gara avanzato di" in b and SOLO_ADMIN in b and "Modifica in Admin" not in b)
else:
    skip("vista da un dispositivo in rete (nessun indirizzo secondario)")

e1 = elapsed()
st, h, _ = req(f"/admin/gara/1/avanzamenti/{adj_id}/modifica", {"minutes": "3", "seconds": "0"})
check("correzione 30 → 3 min: cronometro indietro di 27 min",
      "errore" not in h["location"] and abs((e1 - elapsed()) - 1620) < 1.5)
check("consegna successiva spostata di -27 min, precedente no", abs((b0 - gs("2222")) - 1620) < 0.01 and gs("1111") == a0)
check("avanzamento ora 3 min, totale 3 min",
      db(f"SELECT seconds FROM time_adjustments WHERE id={adj_id}")[0][0] == 180
      and db("SELECT time_offset_seconds FROM competitions WHERE id=1")[0][0] == 180)
st, h, _ = req(f"/admin/gara/1/avanzamenti/{adj_id}/modifica", {"minutes": "999", "seconds": "0"})
check("correzione oltre la fine rifiutata con avviso nella pagina",
      "errore=" in h["location"] and "supererebbe la fine della gara" in req(h["location"].split("#")[0])[2])
st, h, _ = req(f"/admin/gara/1/avanzamenti/{adj_id}/modifica", {"minutes": "0", "seconds": "0"})
check("correzione a zero rifiutata (si usa Elimina)", "errore=" in h["location"])

b_mid, e1 = gs("2222"), elapsed()
req(f"/admin/gara/1/avanzamenti/{adj_id}/elimina", {})
check("eliminazione: cronometro e consegna successiva indietro di 3 min",
      abs((e1 - elapsed()) - 180) < 1.5 and abs((b_mid - gs("2222")) - 180) < 0.01)
check("eliminazione: nessun avanzamento, totale 0, nessuna consegna 'nel futuro'",
      db("SELECT COUNT(*) FROM time_adjustments")[0][0] == 0 and gs("2222") <= elapsed() + 0.5)

db("UPDATE competitions SET recovery_crash_at=CURRENT_TIMESTAMP, recovery_downtime_seconds=90 WHERE id=1")
req("/admin/gara/1/ripresa", {"azione": "avanza", "minutes": "1", "seconds": "30", "torna": "gara"})
check("avanzamento dal popup registrato 'dopo una chiusura del programma'",
      db("SELECT reason, seconds FROM time_adjustments")[0] == ("ripresa", 90.0)
      and "dopo una chiusura del programma" in req("/inserimento/1/consegne")[2])

req("/admin/gara/1/termina", {})
req("/admin/gara/1/archivio", {"archiviata": "1"})
rid = db("SELECT id FROM time_adjustments")[0][0]
st, h, _ = req(f"/admin/gara/1/avanzamenti/{rid}/modifica", {"minutes": "2", "seconds": "0"})
check("gara archiviata: correzione rifiutata", "errore=" in h["location"])
check("gara archiviata: niente pulsanti modifica/elimina",
      "apriModificaAvanzamento(" not in req("/admin/gara/1")[2].split("<script>")[0])
crash_server(srv)
finish()
