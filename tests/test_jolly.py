"""Pagina di inserimento: stato della gara, tempi, squadre senza jolly e assegnazione automatica."""
import json
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlsplit

from _util import check, db, finish, req
from gdm.routers.inserimento import _problema_jolly_predefinito


def stato():
    return json.loads(req("/inserimento/1/stato")[2])


def messaggio(location, chiave):
    return parse_qs(urlsplit(location).query).get(chiave, [""])[0]


s = stato()
check("stato iniziale: non iniziata, durata e tempo jolly in secondi",
      s["status"] == "created" and s["duration"] == 600 and s["jolly_seconds"] == 300 and s["jolly"] == {})
st, _, b = req("/inserimento/1")
check("pagina: barra di stato e riquadro squadre senza jolly",
      "etichettaStato()" in b and "scadenzaJolly()" in b and "Squadre senza jolly" in b and "STATO_INIZIALE" in b)
invio = b.split("async inviaJolly(e)")[1].split("apriConferma(e)")[0] if "async inviaJolly(e)" in b else ""
check("jolly: conferma solo se si sostituisce un jolly diverso, detto esplicitamente",
      "attuale !== undefined && attuale !== p" in invio and "ha già il jolly sul problema" in invio
      and "chiediConferma(" in invio and "await this.aggiorna()" in invio)
st, h, _ = req("/inserimento/1/jolly-mancanti", {})
check("assegnazione automatica rifiutata a gara non iniziata", "errore=" in h["location"])

req("/admin/gara/1/avvia", {})
req("/inserimento/1/jolly", {"team_number": "02", "problem_number": "03"})
s = stato()
check("stato in corso con il jolly della squadra 02 sul problema 03",
      s["status"] == "running" and s["jolly"] == {"2": 3} and 0 <= s["elapsed"] < 10)
st, h, _ = req("/inserimento/1/jolly-mancanti", {})
check("assegnazione automatica rifiutata prima della scadenza dei jolly",
      "non è ancora scaduto" in messaggio(h["location"], "errore"))

req("/admin/gara/1/avanza-tempo", {"minutes": "5", "seconds": "0"})
check("dopo 5 minuti il tempo dei jolly è scaduto", stato()["elapsed"] >= 300)
st, h, _ = req("/inserimento/1/jolly-mancanti", {})
esito = messaggio(h["location"], "esito")
check("assegnazione automatica: esito con il numero di squadre", st == 303 and "problema 01" in esito and "3 squadre" in esito, esito)
s = stato()
check("le 3 squadre senza jolly ora l'hanno sul problema 01, la 02 resta sul 03",
      s["jolly"] == {"1": 1, "2": 3, "3": 1, "4": 1}, str(s["jolly"]))
check("messaggio verde nella pagina", "bg-green-100" in req(h["location"])[2])
st, h, _ = req("/inserimento/1/jolly-mancanti", {})
check("seconda pressione: nessuna squadra da aggiornare",
      "già un jolly" in messaggio(h["location"], "esito") and db("SELECT COUNT(*) FROM jolly_choices")[0][0] == 4)

for numeri, atteso in (([1, 5, 2], 1), ([3, 2, 7], 2), ([], None)):
    p = _problema_jolly_predefinito(NS(problems=[NS(number=n) for n in numeri]))
    check(f"problema predefinito per {numeri}: {atteso}", (p.number if p else None) == atteso)
finish()
