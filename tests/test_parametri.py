"""Parametri di gara: punteggio iniziale delle squadre (vuoto = 10 × numero di problemi)."""
import json
import re

from _util import check, db, finish, req


def totali(cid):
    return [t["total"] for t in json.loads(req(f"/admin/api/gara/{cid}/stato")[2])["teams"]]


def crea(**extra):
    dati = {"name": "Parametri", "date": "2026-12-01", "threshold_minute": "60", "blackout_minute": "80", **extra}
    st, h, b = req("/admin/crea", dati)
    return st, h, b


# gara di prova: 4 problemi, punteggio iniziale non indicato
check("gara esistente: automatico = 10 × 4 problemi = 40", set(totali(1)) == {40})
g = req("/admin/gara/1")[2]
check("pagina gara: valore effettivo e 'automatico'", re.search(r"40 <span[^>]*>\(automatico: 10 × 4 problemi\)", g) is not None)
m = req("/admin/gara/1/modifica")[2]
check("modifica: campo vuoto con suggerimento del valore automatico",
      'name="starting_score"' in m and 'value=""' in m.split('name="starting_score"')[1][:200]
      and "10 × 4 problemi = 40" in m)

st, h, _ = crea(starting_score="")
cid = int(re.search(r"/gara/(\d+)/", h["location"]).group(1))
check("creazione con campo vuoto: salvato come automatico", db(f"SELECT starting_score FROM competitions WHERE id={cid}")[0][0] is None)
st, h, _ = crea(starting_score="150")
cid = int(re.search(r"/gara/(\d+)/", h["location"]).group(1))
req(f"/admin/gara/{cid}/squadre/aggiungi", {"number": "1", "name": "Una"})
req(f"/admin/gara/{cid}/problemi/aggiungi", {"number": "1", "name": "P", "answer": "0001"})
check("creazione con 150: le squadre partono da 150", totali(cid) == [150])
st, _, b = crea(starting_score="abc")
check("valore non numerico rifiutato", st == 400 and "numero intero" in b)

campi = dict(re.findall(r'name="(\w+)"[^>]*value="([^"]*)"', req("/admin/gara/1/modifica")[2]))
campi.update({"starting_score": "100", "display_theme": "light"})
req("/admin/gara/1/modifica", campi)
check("modifica a 100: le squadre partono da 100 (cache aggiornata subito)", set(totali(1)) == {100})
campi["starting_score"] = ""
req("/admin/gara/1/modifica", campi)
check("modifica a vuoto: torna automatico (40)", set(totali(1)) == {40}
      and db("SELECT starting_score FROM competitions WHERE id=1")[0][0] is None)
req("/admin/gara/1/problemi/aggiungi", {"number": "5", "name": "Quinto", "answer": "0005"})
check("in automatico segue il numero di problemi (5 → 50)", set(totali(1)) == {50})

# --- numero precompilato per nuove squadre e problemi ---
def prossimi(cid):
    m = req(f"/admin/gara/{cid}/modifica")[2]
    squadre = m.split('id="squadre"')[1].split('id="problemi"')[0]
    problemi = m.split('id="problemi"')[1]
    num = lambda s: int(re.search(r'name="number"[^>]*value="(\d+)"', s).group(1))
    return num(squadre), num(problemi)


st, h, _ = crea()
nuova = int(re.search(r"/gara/(\d+)/", h["location"]).group(1))
check("gara vuota: si parte da 1 per squadre e problemi", prossimi(nuova) == (1, 1))
req(f"/admin/gara/{nuova}/squadre/aggiungi", {"number": "1", "name": "A"})
req(f"/admin/gara/{nuova}/squadre/aggiungi", {"number": "2", "name": "B"})
req(f"/admin/gara/{nuova}/problemi/aggiungi", {"number": "1", "name": "P1", "answer": "0001"})
check("dopo le aggiunte: squadra 3, problema 2", prossimi(nuova) == (3, 2))
req(f"/admin/gara/{nuova}/squadre/aggiungi", {"number": "10", "name": "Salto"})
check("prosegue dal numero più alto (10 → 11)", prossimi(nuova)[0] == 11)
check("dopo un'aggiunta il cursore va sul nome", "nuova-squadra-nome" in req(f"/admin/gara/{nuova}/modifica")[2])

# --- gara a qualificazione (interruttore + numero di qualificate) ---
check("creazione: interruttore spento di default, numero nascosto",
      re.search(r'x-data="\{ qualificazione: false \}"', req("/admin/crea")[2]) is not None)
st, h, _ = crea(qualificazione="1", num_qualified="3")
q = int(re.search(r"/gara/(\d+)/", h["location"]).group(1))
check("a qualificazione con 3: salvato 3", db(f"SELECT num_qualified FROM competitions WHERE id={q}")[0][0] == 3)
m = req(f"/admin/gara/{q}/modifica")[2]
check("modifica: interruttore acceso e numero 3",
      'x-data="{ qualificazione: true }"' in m and re.search(r'name="num_qualified"[^>]*value="3"', m) is not None)
check("pagina gara: 'si qualificano le prime 3'", "si qualificano le prime 3" in req(f"/admin/gara/{q}")[2])
st, h, _ = crea(num_qualified="5")
nq = int(re.search(r"/gara/(\d+)/", h["location"]).group(1))
check("senza la spunta il numero è ignorato: 0", db(f"SELECT num_qualified FROM competitions WHERE id={nq}")[0][0] == 0)
check("pagina gara: 'Qualificazione no'", re.search(r"Qualificazione</span><span>no<", req(f"/admin/gara/{nq}")[2]) is not None)
for valore in ("", "0", "x"):
    st, _, b = crea(qualificazione="1", num_qualified=valore)
    check(f"a qualificazione con '{valore}': rifiutata", st == 400 and "almeno 1" in b)
campi_q = dict(re.findall(r'name="(\w+)"[^>]*value="([^"]*)"', m))
campi_q.update({"display_theme": "light"})
campi_q.pop("num_qualified", None)
req(f"/admin/gara/{q}/modifica", campi_q)
check("modifica togliendo la spunta: torna 0", db(f"SELECT num_qualified FROM competitions WHERE id={q}")[0][0] == 0)

# --- data facoltativa ---
st, h, _ = req("/admin/crea", {"name": "Senza data", "threshold_minute": "60", "blackout_minute": "80"})
sd = int(re.search(r"/gara/(\d+)/", h["location"]).group(1))
check("creazione senza data accettata, data salvata vuota", st == 303 and db(f"SELECT date FROM competitions WHERE id={sd}")[0][0] == "")
req(f"/admin/gara/{sd}/avvia", {})
req(f"/regia/{sd}/display/aggiungi", {"name": "Schermo"})
vuota = re.compile(r'<span class="(?:text-gray-500 text-sm(?: ml-2)?|text-sm text-gray-500)">\s*</span>')
for pagina in ("/admin/", f"/admin/gara/{sd}", "/inserimento/", f"/inserimento/{sd}", "/regia/", f"/regia/{sd}", "/display/"):
    st, _, b = req(pagina)
    check(f"{pagina}: nessuno spazio vuoto per la data", st == 200 and not vuota.search(b))
disp = db(f"SELECT id FROM displays WHERE competition_id={sd}")[0][0]
check("display: data vuota nell'API (l'intestazione non mostra nulla)",
      json.loads(req(f"/display/api/{sd}/schermo/{disp}/stato")[2])["comp_date"] == "")
check("con la data indicata, la data compare", "2026-05-29" in req("/admin/")[2] or "2026-" in req("/admin/gara/1")[2])

campi["starting_score"] = "77"
req("/admin/gara/1/modifica", campi)
st, h, _ = req("/admin/gara/1/copia", {})
copia = int(re.search(r"/gara/(\d+)", h["location"]).group(1))
check("la copia della gara mantiene il punteggio iniziale", db(f"SELECT starting_score FROM competitions WHERE id={copia}")[0][0] == 77)
finish()
