"""Fine automatica: allo scadere del tempo la gara termina da sola, con la fine esattamente allo scadere."""
import json
import re
import time

from _util import check, db, finish, req


def stato(cid):
    return db(f"SELECT status FROM competitions WHERE id={cid}")[0][0]


def display(cid, disp):
    return json.loads(req(f"/display/api/{cid}/schermo/{disp}/stato")[2])


def aspetta_fine(cid, secondi=5):
    for _ in range(secondi * 4):
        if stato(cid) == "ended":
            return True
        time.sleep(0.25)
    return False


risposte = {n: a for n, a in db("SELECT number, answer FROM problems WHERE competition_id=1")}
req("/regia/1/display/aggiungi", {"name": "Schermo"})
disp = db("SELECT id FROM displays WHERE competition_id=1")[0][0]
durata = db("SELECT duration_minutes FROM competitions WHERE id=1")[0][0] * 60

req("/admin/gara/1/avvia", {})
req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": risposte[1]})
# una consegna rimasta registrata oltre la fine (es. inserita nell'ultimo istante prima del controllo)
team2, prob2 = db("SELECT id FROM teams WHERE competition_id=1 AND number=2")[0][0], \
    db("SELECT id FROM problems WHERE competition_id=1 AND number=2")[0][0]
db("INSERT INTO submissions (competition_id, team_id, problem_id, answer, is_correct, is_post_game, game_seconds, "
   f"submitted_at) VALUES (1, {team2}, {prob2}, '{risposte[2]}', 1, 0, {durata + 3}, CURRENT_TIMESTAMP)")

g = req("/admin/gara/1")[2]
check("pagina gara: allo scadere il cronometro si ferma e la pagina si aggiorna da sola",
      "Math.min(TEMPO_GARA.base + trascorso, TEMPO_GARA.durata)" in g and "const URL_FIRMA" in g)

st, h, _ = req("/admin/gara/1/avanza-tempo", {"minutes": str(durata // 60), "seconds": "0"})
check("avanzando fino alla fine la gara termina da sola entro un paio di secondi", aspetta_fine(1))
d = display(1, disp)
check("fine registrata esattamente allo scadere (tempo di gara = durata)",
      abs(d["elapsed_seconds"] - durata) < 0.01 and d["remaining_seconds"] == 0, str(d["elapsed_seconds"]))
check("come con 'Termina': classifica oscurata nei display", d["status"] == "ended" and d["blackout_active"])
check("la consegna registrata oltre la fine diventa una consegna in ritardo, alla fine della gara",
      db(f"SELECT is_post_game, game_seconds FROM submissions WHERE team_id={team2}") == [(1, float(durata))])
adm = json.loads(req("/admin/api/gara/1/stato")[2])
check("...e conta nel punteggio", next(t for t in adm["teams"] if t["number"] == 2)["total"] > 40)
time.sleep(1.2)
check("il tempo di gara resta fermo alla fine", abs(display(1, disp)["elapsed_seconds"] - durata) < 0.01)

req("/inserimento/1/soluzione", {"team_number": "03", "problem_number": "03", "answer": risposte[3]})
check("consegna inserita dopo la fine: in ritardo, alla fine della gara",
      db("SELECT is_post_game, game_seconds FROM submissions ORDER BY id DESC LIMIT 1")[0] == (1, float(durata)))
g = req("/admin/gara/1")[2]
check("pagina gara: tasti di fine gara (classifica finale), niente più 'Termina'",
      "Calcola classifica finale" in g and "/termina" not in g)
st, _, _ = req("/admin/gara/1/termina", {})
check("'Termina' su una gara già terminata viene rifiutato", st == 400)

# --- gara in pausa alla fine: termina appena riprende ---
st, h, _ = req("/admin/gara/1/copia", {})
cid = int(re.search(r"/gara/(\d+)", h["location"]).group(1))
req(f"/admin/gara/{cid}/avvia", {})
req(f"/admin/gara/{cid}/pausa", {})
req(f"/admin/gara/{cid}/avanza-tempo", {"minutes": str(durata // 60), "seconds": "0"})
time.sleep(1.5)
check("in pausa, anche con il tempo esaurito, la gara resta in pausa", stato(cid) == "paused")
req(f"/admin/gara/{cid}/avvia", {})
check("alla ripresa termina subito", aspetta_fine(cid))

# --- 'Termina' prima della fine continua a funzionare ---
st, h, _ = req("/admin/gara/1/copia", {})
cid2 = int(re.search(r"/gara/(\d+)", h["location"]).group(1))
req(f"/admin/gara/{cid2}/avvia", {})
req(f"/admin/gara/{cid2}/termina", {})
check("'Termina' in anticipo continua a funzionare", stato(cid2) == "ended")
finish()
