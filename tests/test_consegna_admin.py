"""Storico consegne: l'Admin aggiunge una consegna indicandone il tempo di gara."""
import json
from urllib.parse import parse_qs, urlsplit

from _util import REMOTE, check, db, finish, opener, req

team = {n: i for i, n in db("SELECT id, number FROM teams WHERE competition_id=1")}
prob = {n: i for i, n in db("SELECT id, number FROM problems WHERE competition_id=1")}
risposta = {n: a for n, a in db("SELECT number, answer FROM problems WHERE competition_id=1")}
C = "/inserimento/1/consegne"
PANNELLO = "Aggiungi una consegna con il suo tempo di gara"


def aggiungi(t, p, answer, minutes, seconds, **kw):
    st, h, _ = req(f"{C}/aggiungi", {"team_id": team.get(t, t), "problem_id": prob.get(p, p), "answer": answer,
                                     "minutes": str(minutes), "seconds": str(seconds)}, **kw)
    q = parse_qs(urlsplit(h.get("location", "")).query) if h else {}
    return st, q.get("esito", [""])[0], q.get("errore", [""])[0]


def totali():
    return {t["number"]: t["total"] for t in json.loads(req("/admin/api/gara/1/stato")[2])["teams"]}


check("gara non iniziata: nessun pannello", PANNELLO not in req(C)[2])
st, esito, errore = aggiungi(1, 1, risposta[1], 0, 30)
check("gara non iniziata: rifiutata", "non è ancora iniziata" in errore, errore)

req("/admin/gara/1/avvia", {})
req("/admin/gara/1/avanza-tempo", {"minutes": "3", "seconds": "0"})
b = req(C)[2]
check("Admin: pannello presente, tempo proposto = tempo attuale (3 min)",
      PANNELLO in b and 'name="minutes" type="number" min="0" value="3"' in b)

if REMOTE:
    remoto = opener()
    req("/admin/password-accesso", {"password": "segreta-123"})
    req("/accesso", {"password": "segreta-123", "next": "/inserimento/"}, op=remoto, base=REMOTE)
    st, _, b = req(C, op=remoto, base=REMOTE)
    check("dispositivo in rete: storico sì, pannello no", st == 200 and PANNELLO not in b)
    st, _, _ = aggiungi(1, 1, risposta[1], 1, 0, op=remoto, base=REMOTE)
    check("dispositivo in rete: aggiunta rifiutata (403)", st == 403)
    check("nessuna consegna registrata dal remoto", db("SELECT COUNT(*) FROM submissions")[0][0] == 0)

prima = totali()
st, esito, errore = aggiungi(1, 1, risposta[1], 1, 30)
riga = db("SELECT game_seconds, is_post_game, is_correct, answer FROM submissions")
check("consegna aggiunta al minuto 01:30, corretta, non post-gara",
      st == 303 and riga == [(90.0, 0, 1, risposta[1])], riga)
check("messaggio verde con squadra, problema, esito e minuto",
      esito == f"Consegna aggiunta: squadra 01, problema 01, risposta {risposta[1]} (corretta) al minuto 01:30.", esito)
check("il punteggio della squadra 01 cambia subito", totali()[1] > prima[1])
b = req(C + "?esito=x")[2]
check("storico: consegna al minuto 01:30, link senza il messaggio", "01:30" in b and "esito=" not in b.split("Ordine")[1])
ETICHETTA = ">Aggiunta da Admin</span>"
check("storico dell'Admin: consegna segnata come aggiunta da Admin",
      db("SELECT added_by_admin FROM submissions")[0][0] == 1 and b.count(ETICHETTA) == 1)
req("/inserimento/1/soluzione", {"team_number": "04", "problem_number": "03", "answer": "0000"})
check("consegna normale: non segnata", db("SELECT added_by_admin FROM submissions ORDER BY id DESC")[0][0] == 0
      and req(C)[2].count(ETICHETTA) == 1)
if REMOTE:
    st, _, b = req(C, op=remoto, base=REMOTE)
    check("dispositivo in rete: vede le consegne ma non l'etichetta", st == 200 and "01:30" in b and ETICHETTA not in b)

# Consegna nel passato: il bonus di prima consegna passa a chi ha risolto prima
req("/inserimento/1/soluzione", {"team_number": "02", "problem_number": "02", "answer": risposta[2]})
prima = totali()
aggiungi(3, 2, risposta[2], 0, 30)
dopo = totali()
check("consegna retroattiva: la squadra 03 prende il bonus del primo (20), la 02 scende al secondo (15)",
      dopo[2] == prima[2] - 5 and dopo[3] - dopo[2] == 5, f"prima {prima}, dopo {dopo}")

for nome, args, attesa in [
    ("oltre il tempo attuale", (1, 2, "1", 50, 0), "oltre il tempo di gara attuale"),
    ("secondi oltre 59", (1, 2, "1", 1, 75), "da 0 a 59"),
    ("tempo non numerico", (1, 2, "1", "x", 0), "solo cifre"),
    ("risposta non valida", (1, 2, "abc", 1, 0), "da 0 a 9999"),
    ("squadra di un'altra gara", (999999, 2, "1", 1, 0), "squadra scelta non esiste"),
]:
    n = db("SELECT COUNT(*) FROM submissions")[0][0]
    st, esito, errore = aggiungi(*args)
    check(f"rifiutata: {nome}", attesa in errore and db("SELECT COUNT(*) FROM submissions")[0][0] == n, errore)
st, _, b = req(C + "?errore=" + "Consegna%20non%20aggiunta.%20x")
check("dopo un errore il pannello resta aperto", '<details class="bg-white rounded-lg shadow mb-3" open>' in b)

req("/admin/gara/1/termina", {})
st, esito, errore = aggiungi(4, 1, "0000", 2, 0)
check("a gara terminata si può ancora aggiungere (entro la fine)", "Consegna aggiunta" in esito, errore)
req("/admin/gara/1/archivio", {"archiviata": "1"})
st, esito, errore = aggiungi(4, 1, "0000", 2, 0)
check("gara archiviata: rifiutata e pannello nascosto", "archiviata" in errore and PANNELLO not in req(C)[2])
finish()
