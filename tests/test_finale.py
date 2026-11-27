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


def fotografia():
    """Classifica finale salvata dall'Admin."""
    return json.loads(db("SELECT final_ranking_json FROM competitions WHERE id=1")[0][0])


req("/regia/1/display/aggiungi", {"name": "Schermo"})
req("/admin/gara/1/avvia", {})
req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"})
req("/inserimento/1/soluzione", {"team_number": "02", "problem_number": "02", "answer": "0137"})

st, h, _ = req("/admin/gara/1/calcola-finale", {})
check("calcolo rifiutato a gara in corso", "errore=" in h["location"])
st, h, _ = req("/admin/gara/1/archivio", {"archiviata": "1"})
check("una gara non terminata non si può archiviare", "errore=" in h["location"]
      and not admin_stato()["archived"] and db("SELECT archived_manual FROM competitions WHERE id=1")[0][0] is None)
check("pagina gara in corso: niente interruttore dell'archiviazione", 'name="archiviata"' not in req("/admin/gara/1")[2])

check("prima del minuto di oscuramento la classifica è visibile", finale_display()["blackout_active"] is False)
req("/admin/gara/1/termina", {})
check("'Termina' (anche in anticipo) oscura la classifica dei display", finale_display()["blackout_active"] is True)
g = req("/admin/gara/1")[2]
check("gara terminata: tasto 'Calcola' e interruttore 'Gara archiviata' (niente più blocco degli inserimenti)",
      "Calcola classifica finale" in g and 'name="archiviata"' in g and 'name="bloccati"' not in g
      and "non ancora calcolata" in g and "automatica il " in g)
check("display: classifica finale non ancora disponibile", finale_display()["final_ready"] is False)
check("regia: invito a calcolare la classifica dall'Admin", "calcolarla dalla pagina Admin" in req("/regia/1")[2])

st, h, _ = req("/admin/gara/1/calcola-finale", {})
check("calcolo: esito in verde", msg(h["location"], "esito") == "Classifica finale calcolata.")
d = finale_display()
prima = [t["id"] for t in fotografia()]
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
check("la classifica finale NON cambia da sola", [t["id"] for t in fotografia()] == prima)
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
      fotografia()[0]["id"] == squadra3 and admin_stato()["revealed_positions"] == 0)
req("/regia/1/rivela-indietro", {})
check("'Annulla ultima' con nulla di rivelato resta a 0", admin_stato()["revealed_positions"] == 0)

# gara archiviata: niente soluzioni, jolly, assegnazione automatica, modifica ed eliminazione
st, h, _ = req("/admin/gara/1/archivio", {"archiviata": "1"})
check("archiviata a mano, con esito", msg(h["location"], "esito").startswith("Gara archiviata")
      and admin_stato()["archived"] and admin_stato()["insertions_locked"])
g = req("/admin/gara/1")[2]
check("pagina gara: interruttore spuntato, 'archiviata a mano'",
      re.search(r'name="archiviata" value="1"[^>]*checked', g) is not None and "archiviata a mano" in g)
# archiviata = sola lettura: parametri, squadre, problemi, bonus e classifica finale non si toccano
check("pagina gara archiviata: niente tasti di modifica, avviso 'sola lettura'",
      "sola lettura" in g and 'href="/admin/gara/1/modifica' not in g and "/penalizzazioni/aggiungi" not in g
      and "/calcola-finale" not in g)
squadra1 = db("SELECT id FROM teams WHERE competition_id=1 AND number=1")[0][0]
prob1 = db("SELECT id FROM problems WHERE competition_id=1 AND number=1")[0][0]
prima_nome = db("SELECT name FROM competitions WHERE id=1")[0][0]
n_teams = db("SELECT COUNT(*) FROM teams")[0][0]
for metodo_path, dati, cosa in (
    ("/admin/gara/1/modifica", None, "pagina dei parametri"),
    ("/admin/gara/1/modifica", {"name": "Cambiata", "threshold_minute": "8", "blackout_minute": "7"}, "salvataggio dei parametri"),
    ("/admin/gara/1/squadre/aggiungi", {"number": "9", "name": "Nuova"}, "nuova squadra"),
    (f"/admin/gara/1/squadre/{squadra1}/modifica", {"number": "1", "name": "Rinominata"}, "modifica di una squadra"),
    (f"/admin/gara/1/problemi/{prob1}/modifica", {"number": "1", "name": "P", "answer": "0001"}, "modifica di un problema"),
    ("/admin/gara/1/penalizzazioni/aggiungi", {"team_id": squadra1, "value": "5"}, "bonus"),
    ("/admin/gara/1/calcola-finale", {}, "ricalcolo della classifica finale"),
):
    st, h, _ = req(metodo_path, dati)
    check(f"archiviata: {cosa} rifiutata", st == 303 and "de-archiviarla" in msg(h["location"], "errore"))
check("archiviata: nulla è cambiato (nome, squadre, bonus)",
      db("SELECT name FROM competitions WHERE id=1")[0][0] == prima_nome and db("SELECT COUNT(*) FROM teams")[0][0] == n_teams
      and db("SELECT COUNT(*) FROM penalties")[0][0] == 0 and db(f"SELECT name FROM teams WHERE id={squadra1}")[0][0] != "Rinominata")
import urllib.request  # noqa: E402  (il PDF è binario: niente req(), che decodifica il testo)
from _util import BASE  # noqa: E402
with urllib.request.urlopen(BASE + "/admin/gara/1/esporta-pdf", timeout=30) as pdf:
    check("archiviata: il PDF dei risultati si esporta ancora", pdf.status == 200 and pdf.read(4) == b"%PDF")
check("archiviata: le finestre delle viste dell'Admin funzionano ancora",
      req("/admin/gara/1/vista/matrix")[0] == 200 and json.loads(req("/admin/api/gara/1/vista/matrix/stato")[2])["view"] == "matrix")
n_sub = db("SELECT COUNT(*) FROM submissions")[0][0]
n_jolly = db("SELECT COUNT(*) FROM jolly_choices")[0][0]
for path, dati, cosa in (
    ("/inserimento/1/soluzione", {"team_number": "04", "problem_number": "01", "answer": "0042"}, "soluzione"),
    ("/inserimento/1/jolly", {"team_number": "04", "problem_number": "01"}, "jolly"),
    ("/inserimento/1/jolly-mancanti", {}, "assegnazione automatica dei jolly"),
):
    st, h, _ = req(path, dati)
    check(f"archiviata: {cosa} rifiutata con avviso", "archiviata" in msg(h["location"], "errore"))
sid = db("SELECT id FROM submissions ORDER BY id LIMIT 1")[0][0]
team, prob = db(f"SELECT team_id, problem_id FROM submissions WHERE id={sid}")[0]
st, h, _ = req(f"/inserimento/1/consegne/{sid}/modifica", {"team_id": team, "problem_id": prob, "answer": "9999"})
check("archiviata: modifica rifiutata", "archiviata" in msg(h["location"], "errore"))
st, h, _ = req(f"/inserimento/1/consegne/{sid}/elimina", {})
check("archiviata: eliminazione rifiutata", "archiviata" in msg(h["location"], "errore"))
check("archiviata: nulla è cambiato nel database",
      db("SELECT COUNT(*) FROM submissions")[0][0] == n_sub and db("SELECT COUNT(*) FROM jolly_choices")[0][0] == n_jolly
      and db(f"SELECT answer FROM submissions WHERE id={sid}")[0][0] != "9999")
check("stato per la pagina dell'inseritore: locked", json.loads(req("/inserimento/1/stato")[2])["locked"] is True)
st, _, b = req("/inserimento/1/consegne")
check("storico: avviso dell'archiviazione e azioni nascoste", "La gara è archiviata" in b and "/elimina" not in b)

# elenchi: l'archiviata non compare a inseritori e display, nella home Admin sta nell'archivio
nome = db("SELECT name FROM competitions WHERE id=1")[0][0]
check("archiviata: non compare nell'elenco degli inseritori", 'href="/inserimento/1"' not in req("/inserimento/")[2])
check("archiviata: non compare nell'elenco dei display", 'href="/display/1"' not in req("/display/")[2])
check("archiviata: non compare nell'elenco della regia", 'href="/regia/1"' not in req("/regia/")[2])
home = req("/admin/")[2]
check("home Admin: non c'è nell'elenco, c'è il link all'archivio con il numero di gare",
      'href="/admin/gara/1"' not in home and 'href="/admin/archivio"' in home and "Archivio (1 gara)" in home)
arch = req("/admin/archivio")[2]
check("pagina dell'archivio: la gara, con 'De-archivia'", 'href="/admin/gara/1"' in arch and "De-archivia" in arch)

st, h, _ = req("/admin/gara/1/archivio", {"torna": "archivio"})
check("de-archiviata dall'archivio: torna nell'elenco principale e accetta di nuovo gli inserimenti",
      h["location"] == "/admin/archivio" and not admin_stato()["archived"]
      and 'href="/admin/gara/1"' in req("/admin/")[2] and 'href="/inserimento/1"' in req("/inserimento/")[2]
      and 'href="/regia/1"' in req("/regia/")[2])
check("de-archiviata a mano: non si archivia più da sola", "de-archiviata a mano" in req("/admin/gara/1")[2])

# archiviazione automatica 24 ore dopo la fine (si sposta indietro la fine nel database)
db("UPDATE competitions SET archived_manual=NULL, ended_at=datetime(ended_at, '-23 hours') WHERE id=1")
check("23 ore dopo la fine: non ancora archiviata", not admin_stato()["archived"])
db("UPDATE competitions SET ended_at=datetime(ended_at, '-2 hours') WHERE id=1")
check("25 ore dopo la fine: archiviata da sola", admin_stato()["archived"]
      and "archiviata" in msg(req("/inserimento/1/soluzione", {"team_number": "04", "problem_number": "01", "answer": "0042"})[1]["location"], "errore"))
req("/admin/gara/1/archivio", {})
check("anche dopo l'archiviazione automatica si può de-archiviare", not admin_stato()["archived"])
db("UPDATE competitions SET ended_at=datetime(ended_at, '+25 hours') WHERE id=1")  # fine al suo posto
st, h, _ = req("/inserimento/1/jolly-mancanti", {})
check("gara terminata prima della scadenza dei jolly: l'assegnazione automatica è possibile",
      "problema 01" in msg(h["location"], "esito"))
st, h, _ = req("/inserimento/1/soluzione", {"team_number": "04", "problem_number": "01", "answer": "0042"})
check("dopo lo sblocco la soluzione viene accettata", "errore" not in h["location"]
      and db("SELECT COUNT(*) FROM submissions")[0][0] == n_sub + 1)
finish()
