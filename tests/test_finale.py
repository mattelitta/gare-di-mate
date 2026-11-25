"""Fine gara: classifica finale ricalcolabile ("fotografia") e spunta che blocca gli inserimenti."""
import json
import re
from urllib.parse import parse_qs, urlsplit

from _util import check, db, finish, req


def msg(location, chiave):
    return parse_qs(urlsplit(location).query).get(chiave, [""])[0]


def admin_stato():
    return json.loads(req("/admin/api/gara/1/stato")[2])


def finale_display():
    return json.loads(req("/display/api/1/schermo/1/stato")[2])


req("/regia/1/display/aggiungi", {"name": "Schermo"})
req("/admin/gara/1/avvia", {})
req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"})
req("/inserimento/1/soluzione", {"team_number": "02", "problem_number": "02", "answer": "0137"})

st, h, _ = req("/admin/gara/1/calcola-finale", {})
check("calcolo rifiutato a gara in corso", "errore=" in h["location"])
st, h, _ = req("/admin/gara/1/blocco-inserimenti", {"bloccati": "1"})
check("blocco rifiutato a gara in corso", "errore=" in h["location"] and not admin_stato()["insertions_locked"])

check("prima del minuto di oscuramento la classifica è visibile", finale_display()["blackout_active"] is False)
req("/admin/gara/1/termina", {})
check("'Termina' (anche in anticipo) oscura la classifica dei display", finale_display()["blackout_active"] is True)
g = req("/admin/gara/1")[2]
check("gara terminata: tasto 'Calcola' e spunta del blocco, nessun vecchio 'Blocca inserimenti e calcola'",
      "Calcola classifica finale" in g and 'name="bloccati"' in g and "blocca-finale" not in g and "non ancora calcolata" in g)
check("display: classifica finale non ancora disponibile", finale_display()["final_ready"] is False)
check("regia: invito a calcolare la classifica dall'Admin", "calcolarla dalla pagina Admin" in req("/regia/1")[2])

st, h, _ = req("/admin/gara/1/calcola-finale", {})
check("calcolo: esito in verde", msg(h["location"], "esito") == "Classifica finale calcolata.")
d = finale_display()
prima = [t["id"] for t in d["final_ranking"]]
check("display: classifica finale disponibile e uguale a quella calcolata",
      d["final_ready"] and prima == [t["id"] for t in admin_stato()["teams"]])
g = req("/admin/gara/1")[2]
check("pagina gara: 'Ricalcola' e orario del calcolo", "Ricalcola classifica finale" in g and re.search(r"calcolata alle \d\d:\d\d", g))
check("regia: rivelazione disponibile", "Rivela prossima posizione" in req("/regia/1")[2])

# consegna in ritardo che cambia la classifica: la fotografia non cambia finché non si ricalcola
squadra3 = db("SELECT id FROM teams WHERE competition_id=1 AND number=3")[0][0]
for p, a in (("01", "0042"), ("02", "0137"), ("03", "1024")):
    req("/inserimento/1/soluzione", {"team_number": "03", "problem_number": p, "answer": a})
check("consegne post-gara accettate (inserimenti aperti)", db("SELECT COUNT(*) FROM submissions WHERE is_post_game=1")[0][0] == 3)
check("la classifica del momento cambia (squadra 03 prima): le consegne post-gara contano "
      "anche se la gara è stata terminata prima della fine teorica",
      admin_stato()["teams"][0]["id"] == squadra3, str([(t["number"], t["total"]) for t in admin_stato()["teams"]]))
check("consegne post-gara registrate al momento in cui la gara è finita (non a 10:00)",
      db("SELECT MAX(game_seconds) FROM submissions WHERE is_post_game=1")[0][0] < 60)
check("la classifica finale dei display NON cambia da sola", [t["id"] for t in finale_display()["final_ranking"]] == prima)
check("regia: 'Annulla ultima' disattivato prima di rivelare", re.search(r"\sdisabled>\s*↶ Annulla ultima", req("/regia/1")[2]) is not None)
req("/regia/1/rivela", {})
req("/regia/1/rivela", {})
req("/regia/1/rivela", {})
check("rivelazione avanzata a 3", admin_stato()["revealed_positions"] == 3)
st, h, _ = req("/regia/1/rivela-indietro", {})
check("'Annulla ultima': si torna a 2 posizioni rivelate",
      h["location"] == "/regia/1" and admin_stato()["revealed_positions"] == 2
      and finale_display()["revealed_positions"] == 2)
check("regia: 'Annulla ultima' attivo", re.search(r"\sdisabled>\s*↶ Annulla ultima", req("/regia/1")[2]) is None)
check("il tasto avvisa che la rivelazione è iniziata", "La rivelazione della classifica finale è già iniziata" in req("/admin/gara/1")[2])
st, h, _ = req("/admin/gara/1/calcola-finale", {})
check("ricalcolo: esito che segnala la rivelazione azzerata",
      "ricalcolata" in msg(h["location"], "esito") and "ripartirà dall'inizio" in msg(h["location"], "esito"))
check("ricalcolo: la classifica finale ora include le consegne in ritardo, rivelazione a 0",
      finale_display()["final_ranking"][0]["id"] == squadra3 and admin_stato()["revealed_positions"] == 0)
req("/regia/1/rivela-indietro", {})
check("'Annulla ultima' con nulla di rivelato resta a 0", admin_stato()["revealed_positions"] == 0)

# spunta del blocco: blocca soluzioni, jolly, assegnazione automatica, modifica ed eliminazione
st, h, _ = req("/admin/gara/1/blocco-inserimenti", {"bloccati": "1"})
check("blocco attivato con esito", msg(h["location"], "esito") == "Inserimenti bloccati." and admin_stato()["insertions_locked"])
g = req("/admin/gara/1")[2]
check("pagina gara: spunta selezionata", re.search(r'name="bloccati" value="1"[^>]*checked', g) is not None)
n_sub = db("SELECT COUNT(*) FROM submissions")[0][0]
n_jolly = db("SELECT COUNT(*) FROM jolly_choices")[0][0]
for path, dati, cosa in (
    ("/inserimento/1/soluzione", {"team_number": "04", "problem_number": "01", "answer": "0042"}, "soluzione"),
    ("/inserimento/1/jolly", {"team_number": "04", "problem_number": "01"}, "jolly"),
    ("/inserimento/1/jolly-mancanti", {}, "assegnazione automatica dei jolly"),
):
    st, h, _ = req(path, dati)
    check(f"bloccato: {cosa} rifiutata con avviso", "bloccati dall'Admin" in msg(h["location"], "errore"))
sid = db("SELECT id FROM submissions ORDER BY id LIMIT 1")[0][0]
team, prob = db(f"SELECT team_id, problem_id FROM submissions WHERE id={sid}")[0]
st, h, _ = req(f"/inserimento/1/consegne/{sid}/modifica", {"team_id": team, "problem_id": prob, "answer": "9999"})
check("bloccato: modifica rifiutata", "bloccati dall'Admin" in msg(h["location"], "errore"))
st, h, _ = req(f"/inserimento/1/consegne/{sid}/elimina", {})
check("bloccato: eliminazione rifiutata", "bloccati dall'Admin" in msg(h["location"], "errore"))
check("bloccato: nulla è cambiato nel database",
      db("SELECT COUNT(*) FROM submissions")[0][0] == n_sub and db("SELECT COUNT(*) FROM jolly_choices")[0][0] == n_jolly
      and db(f"SELECT answer FROM submissions WHERE id={sid}")[0][0] != "9999")
check("stato per la pagina dell'inseritore: locked", json.loads(req("/inserimento/1/stato")[2])["locked"] is True)
st, _, b = req("/inserimento/1/consegne")
check("storico: avviso di blocco e azioni nascoste", "bloccati dall'Admin" in b and "/elimina" not in b and "bloccato" in b)

st, h, _ = req("/admin/gara/1/blocco-inserimenti", {})
check("spunta tolta: inserimenti di nuovo aperti", msg(h["location"], "esito") == "Inserimenti di nuovo aperti."
      and not admin_stato()["insertions_locked"])
st, h, _ = req("/inserimento/1/jolly-mancanti", {})
check("gara terminata prima della scadenza dei jolly: l'assegnazione automatica è possibile",
      "problema 01" in msg(h["location"], "esito"))
st, h, _ = req("/inserimento/1/soluzione", {"team_number": "04", "problem_number": "01", "answer": "0042"})
check("dopo lo sblocco la soluzione viene accettata", "errore" not in h["location"]
      and db("SELECT COUNT(*) FROM submissions")[0][0] == n_sub + 1)
finish()
