"""Inserimenti non validi (squadra/problema inesistenti, risposte non numeriche...): il server non
registra nulla e torna alla pagina con un avviso leggibile, mai una pagina d'errore tecnica."""
import re
from urllib.parse import parse_qs, urlsplit

from _util import check, db, finish, req

req("/admin/gara/1/avvia", {})


def errore(location):
    return parse_qs(urlsplit(location).query).get("errore", [""])[0]


def conta():
    return db("SELECT COUNT(*) FROM submissions")[0][0], db("SELECT COUNT(*) FROM jolly_choices")[0][0]


casi_soluzione = [
    ({"team_number": "07", "problem_number": "01", "answer": "0042"}, "squadra 07 non esiste"),
    ({"team_number": "01", "problem_number": "09", "answer": "0042"}, "problema 09 non esiste"),
    ({"team_number": "", "problem_number": "01", "answer": "0042"}, "Inserire il numero della squadra"),
    ({"team_number": "a1", "problem_number": "01", "answer": "0042"}, "solo cifre"),
    ({"team_number": "01", "problem_number": "x", "answer": "0042"}, "solo cifre"),
    ({"team_number": "01", "problem_number": "01", "answer": ""}, "Inserire la risposta"),
    ({"team_number": "01", "problem_number": "01", "answer": "ab"}, "da 0 a 9999"),
    ({"team_number": "01", "problem_number": "01", "answer": "12345"}, "da 0 a 9999"),
    ({"team_number": "01", "problem_number": "01", "answer": "-5"}, "da 0 a 9999"),
]
for dati, atteso in casi_soluzione:
    st, h, _ = req("/inserimento/1/soluzione", dati)
    msg = errore(h.get("location", ""))
    check(f"soluzione {dati} -> avviso '{atteso}'",
          st == 303 and h["location"].startswith("/inserimento/1?") and atteso in msg and "Consegna non registrata" in msg, msg)

casi_jolly = [
    ({"team_number": "99", "problem_number": "01"}, "squadra 99 non esiste"),
    ({"team_number": "01", "problem_number": "0"}, "problema 00 non esiste"),
    ({"team_number": "01", "problem_number": ""}, "Inserire il numero del problema"),
]
for dati, atteso in casi_jolly:
    st, h, _ = req("/inserimento/1/jolly", dati)
    msg = errore(h.get("location", ""))
    check(f"jolly {dati} -> avviso '{atteso}'", st == 303 and atteso in msg and "Jolly non registrato" in msg, msg)

check("nessuna consegna o jolly registrati con dati non validi", conta() == (0, 0))
st, h, _ = req("/inserimento/1/soluzione", {"team_number": "07", "problem_number": "01", "answer": "1"})
st, _, b = req(h["location"])
check("la pagina mostra l'avviso in rosso", st == 200 and "La squadra 07 non esiste in questa gara" in b and "bg-red-100" in b)

st, _, _ = req("/inserimento/1/soluzione", {"team_number": "1", "problem_number": "1", "answer": "42"})
check("risposta corta valida accettata e completata con zeri (42 -> 0042)",
      st == 303 and db("SELECT answer, is_correct FROM submissions")[0] == ("0042", 1))

sid = db("SELECT id FROM submissions")[0][0]
altra = db("SELECT id FROM teams WHERE competition_id=1 AND number=2")[0][0]
prob = db("SELECT id FROM problems WHERE competition_id=1 AND number=1")[0][0]
base = f"/inserimento/1/consegne/{sid}/modifica?ordine=crescente"
st, h, _ = req(base, {"team_id": altra, "problem_id": prob, "answer": "abc"})
check("modifica con risposta non valida: torna alla modifica con avviso e filtri",
      st == 303 and "/modifica?ordine=crescente&errore=" in h["location"]
      and "da 0 a 9999" in errore(h["location"]))
st, _, b = req(h["location"])
check("pagina di modifica: avviso mostrato, filtri senza l'errore nel form",
      "Modifica non salvata" in b and re.search(r'/modifica\?ordine=crescente"', b) is not None)
st, h, _ = req("/admin/crea", {"name": "Altra", "date": "2026-12-01", "threshold_minute": "60", "blackout_minute": "80"})
req(h["location"].split("/modifica")[0] + "/squadre/aggiungi", {"number": "1", "name": "Estranea"})
estranea = db("SELECT id FROM teams WHERE name='Estranea'")[0][0]
st, h, _ = req(base, {"team_id": estranea, "problem_id": prob, "answer": "0042"})
check("modifica con una squadra di un'altra gara rifiutata", "errore=" in h["location"])
check("la consegna non è stata modificata", db("SELECT team_id, answer FROM submissions")[0][1] == "0042"
      and db("SELECT team_id FROM submissions")[0][0] != estranea)

# --- solo cifre nei campi, e dopo una consegna il cursore torna sulle risposte ---
pagina = req("/inserimento/1")[2]
campi = re.findall(r'<input x-ref="(?:j|s)_\w+"[^>]*>', pagina)
check("tutti i campi dell'inserimento: tastiera numerica e lettere tolte mentre si scrive",
      len(campi) == 5 and all('pattern="[0-9]*"' in c and 'oninput="autoAvanza(this)"' in c for c in campi)
      and "function soloCifre(el)" in pagina and "soloCifre(el);" in pagina)
check("cursore iniziale scelto dalla pagina (jolly, o risposte dopo una consegna), non da autofocus",
      "autofocus" not in pagina and "location.hash === '#risposte'" in pagina)
st, h, _ = req("/inserimento/1/soluzione", {"team_number": "02", "problem_number": "02", "answer": "0001"})
check("consegna registrata: si torna alla pagina sui campi delle risposte", h["location"] == "/inserimento/1#risposte")
st, h, _ = req("/inserimento/1/soluzione", {"team_number": "77", "problem_number": "02", "answer": "0001"})
check("consegna rifiutata dal server: avviso e cursore sulle risposte",
      h["location"].endswith("#risposte") and "non esiste" in errore(h["location"]))
st, h, _ = req("/inserimento/1/jolly", {"team_number": "03", "problem_number": "02"})
check("dopo un jolly si resta sui campi dei jolly", "#risposte" not in h["location"])
storico = req("/inserimento/1/consegne")[2]
check("storico (aggiunta dell'Admin): anche lì solo cifre nella risposta",
      re.search(r'<input name="answer"[^>]*pattern="\[0-9\]\*"[^>]*replace\(/\\D/g', storico) is not None)
finish()
