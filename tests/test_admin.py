"""Pagine admin: squadre e problemi in "Modifica parametri", bonus o penalizzazioni, città facoltativa,
gara non ancora iniziata vista dagli inseritori, host riconosciuto anche dal suo IP di rete."""
import json
import re

from _util import BASE, PORT, check, db, finish, lan_ip, req

# --- creazione e gestione di squadre e problemi ---
st, h, _ = req("/admin/crea", {"name": "Prova layout", "date": "2026-12-01", "threshold_minute": "60", "blackout_minute": "80"})
loc = h.get("location", "")
check("dopo la creazione si va a 'Modifica parametri' sulle squadre", st == 303 and loc.endswith("/modifica#squadre"))
cid = re.search(r"/gara/(\d+)/", loc).group(1)
G, M = f"/admin/gara/{cid}", f"/admin/gara/{cid}/modifica"
st, _, b = req(M)
check("modifica: sezioni squadre e problemi", 'id="squadre"' in b and 'id="problemi"' in b and f"{G}/squadre/aggiungi" in b)
check("modifica: tema chiaro predefinito", re.search(r'value="light"\s+selected>Chiaro \(default', b) is not None)
st, h, _ = req(f"{G}/squadre/aggiungi", {"number": "1", "name": "Alfa", "city": "Roma"})
check("aggiungi squadra -> torna alle squadre", h["location"] == f"{M}#squadre")
req(f"{G}/squadre/aggiungi", {"number": "2", "name": "Beta"})
st, h, _ = req(f"{G}/problemi/aggiungi", {"number": "1", "name": "Primo", "answer": "0042"})
check("aggiungi problema -> torna ai problemi", h["location"] == f"{M}#problemi")
b = req(M)[2]
team_ids = re.findall(rf"{G}/squadre/(\d+)/elimina", b)
prob_ids = re.findall(rf"{G}/problemi/(\d+)/elimina", b)
st, h, _ = req(f"{G}/squadre/{team_ids[0]}/modifica", {"number": "1", "name": "Alfa 2", "city": ""})
check("modifica squadra -> torna alle squadre", h["location"] == f"{M}#squadre")
st, h, _ = req(f"{G}/problemi/{prob_ids[0]}/modifica", {"number": "1", "name": "Primo", "answer": "0043"})
check("modifica problema -> torna ai problemi", h["location"] == f"{M}#problemi")
st, _, b = req(G)
check("gara: squadre e problemi solo in lettura",
      "/squadre/aggiungi" not in b and "/problemi/aggiungi" not in b and "Alfa 2" in b and "[0043]" in b)
check("gara: sezione 'Bonus o penalizzazioni'", "Bonus o penalizzazioni" in b and ">Penalizzazioni<" not in b)
st, h, _ = req(f"{G}/penalizzazioni/aggiungi", {"team_id": team_ids[0], "value": "15", "note": "fair play"})
check("bonus positivo aggiunto e mostrato (+15)", st == 303 and "+15" in req(G)[2])
req(f"{G}/avvia", {})
check("modifica a gara iniziata: avviso presente", "La gara è già iniziata" in req(M)[2])

# --- città facoltativa ---
req(f"{G}/squadre/aggiungi", {"number": "9", "name": "Senza Citta", "city": "   "})
check("città fatta di spazi salvata vuota", db("SELECT city FROM teams WHERE name='Senza Citta'")[0][0] == "")
squadre = req(G)[2].split('font-semibold">Squadre (')[1].split('font-semibold">Problemi (')[0]
check("nessuna '()' vuota nell'elenco squadre", "()" not in squadre and "Senza Citta" in squadre)
check("campi città non obbligatori", not re.search(r'name="city"[^>]*required', req(M)[2]))

# --- gara di prova (setup_test) non ancora iniziata, vista dall'inserimento ---
st, _, b = req("/inserimento/")
check("l'inserimento elenca la gara non iniziata", 'href="/inserimento/1"' in b)
st, _, b = req("/inserimento/1")
check("pagina inserimento con avviso e invio disattivato",
      st == 200 and "La gara non è ancora iniziata" in b and b.count(" disabled") >= 2)
check("stato: created", json.loads(req("/inserimento/1/stato")[2])["status"] == "created")
st, _, b = req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"})
check("soluzione rifiutata prima della partenza (409)", st == 409)
st, _, b = req("/inserimento/1/jolly", {"team_number": "01", "problem_number": "01"})
check("jolly rifiutato prima della partenza (409)", st == 409)
req("/admin/gara/1/avvia", {})
check("dopo l'avvio lo stato è running", json.loads(req("/inserimento/1/stato")[2])["status"] == "running")
st, _, _ = req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"})
check("soluzione accettata dopo la partenza", st == 303)
sid = re.findall(r"/consegne/(\d+)/modifica", req("/inserimento/1/consegne")[2])[0]
check("modifica consegna: nessuna '()' vuota", "()" not in req(f"/inserimento/1/consegne/{sid}/modifica")[2])

# --- host riconosciuto anche dal suo IP di rete ---
for base in (BASE, f"http://{lan_ip()}:{PORT}"):
    st, _, home = req("/", base=base)
    check(f"{base}: barra completa e Admin raggiungibile",
          'href="/regia/"' in home and 'href="/esci"' not in home and req("/admin/", base=base)[0] == 200)
finish()
