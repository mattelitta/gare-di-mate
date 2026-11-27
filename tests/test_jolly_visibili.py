"""Visibilità dei jolly nei display: appena inseriti (default) o tutti insieme alla chiusura dei jolly."""
import json
import re

from _util import check, db, finish, req


def campi_modifica(cid):
    campi = dict(re.findall(r'name="(\w+)"[^>]*value="([^"]*)"', req(f"/admin/gara/{cid}/modifica")[2]))
    campi["display_theme"] = "light"
    return campi


def display(cid):
    return json.loads(req(f"/display/api/{cid}/schermo/{schermo}/stato")[2])


def squadra(dati, numero, chiave="number"):
    return next(t for t in dati["teams"] if t[chiave] == numero)


# --- default e salvataggio ---
st, h, _ = req("/admin/crea", {"name": "Default", "threshold_minute": "60", "blackout_minute": "80"})
nuova = int(re.search(r"/gara/(\d+)/", h["location"]).group(1))
check("nuova gara: jolly visibili appena inseriti (default)",
      db(f"SELECT jolly_reveal FROM competitions WHERE id={nuova}")[0][0] == "immediate")
check("modulo di creazione: scelta presente, default selezionato",
      re.search(r'value="immediate" selected>Visibili appena inseriti', req("/admin/crea")[2]) is not None)
check("gara di prova esistente (migrata): default 'immediate'",
      db("SELECT jolly_reveal FROM competitions WHERE id=1")[0][0] == "immediate")

campi = campi_modifica(1)
campi["jolly_reveal"] = "deadline"
req("/admin/gara/1/modifica", campi)
check("modifica: salvato 'alla chiusura dei jolly'", db("SELECT jolly_reveal FROM competitions WHERE id=1")[0][0] == "deadline")
check("modifica: la scelta salvata risulta selezionata",
      re.search(r'value="deadline" selected>Tutti insieme', req("/admin/gara/1/modifica")[2]) is not None)
check("pagina gara: parametro mostrato", "alla chiusura dei jolly" in req("/admin/gara/1")[2])
campi["jolly_reveal"] = "qualsiasi"
req("/admin/gara/1/modifica", campi)
check("valore sconosciuto -> 'immediate'", db("SELECT jolly_reveal FROM competitions WHERE id=1")[0][0] == "immediate")
campi["jolly_reveal"] = "deadline"
req("/admin/gara/1/modifica", campi)

# --- jolly nascosti fino alla chiusura (gara di prova: jolly entro il minuto 5) ---
req("/regia/1/display/aggiungi", {"name": "Schermo"})
schermo = db("SELECT id FROM displays WHERE competition_id=1")[0][0]
pid, risposta = db("SELECT id, answer FROM problems WHERE competition_id=1 AND number=3")[0]
req("/admin/gara/1/avvia", {})
req("/inserimento/1/jolly", {"team_number": "02", "problem_number": "03"})
req("/inserimento/1/soluzione", {"team_number": "02", "problem_number": "03", "answer": risposta})

d = display(1)
adm = json.loads(req("/admin/api/gara/1/stato")[2])
t_d, t_a = squadra(d, 2), squadra(adm, 2)
check("prima della chiusura: display senza jolly", d["jolly_public"] is False and t_d["jolly_problem_id"] is None)
check("prima della chiusura: admin vede il jolly", t_a["jolly_problem_id"] == pid)
contributo = t_d["problem_contributions"][str(pid)]
check("prima della chiusura: display conta il problema senza raddoppio, admin con",
      contributo > 0 and t_a["total"] - t_d["total"] == contributo, f"{t_a['total']} vs {t_d['total']} (+{contributo})")
check("inseritori vedono sempre i jolly", json.loads(req("/inserimento/1/stato")[2])["jolly"] == {"2": 3})
req("/regia/1/display/aggiungi", {"name": "Sala staff"})
interno = db("SELECT id FROM displays WHERE name='Sala staff'")[0][0]
req(f"/regia/1/display/{interno}/interno", {"interno": "1"})
staff = json.loads(req(f"/display/api/1/schermo/{interno}/stato")[2])
check("prima della chiusura: lo schermo interno vede il jolly, con i punti dell'admin",
      staff["jolly_public"] is True and squadra(staff, 2)["jolly_problem_id"] == pid
      and {t["number"]: t["total"] for t in staff["teams"]} == {t["number"]: t["total"] for t in adm["teams"]})
check("...mentre lo schermo pubblico continua a non vederlo", display(1)["jolly_public"] is False)

req("/admin/gara/1/avanza-tempo", {"minutes": "5", "seconds": "0"})
d = display(1)
adm = json.loads(req("/admin/api/gara/1/stato")[2])
t_d = squadra(d, 2)
check("dopo la chiusura: display con il jolly", d["jolly_public"] is True and t_d["jolly_problem_id"] == pid)
# (il contributo cresce con il tempo di gara: si confrontano i totali con quelli dell'admin)
check("dopo la chiusura: punti con raddoppio, uguali all'admin per tutte le squadre",
      {t["number"]: t["total"] for t in d["teams"]} == {t["number"]: t["total"] for t in adm["teams"]},
      f"display {t_d['total']}, admin {squadra(adm, 2)['total']}, contributo {t_d['problem_contributions'][str(pid)]} (prima {contributo})")

# --- modalità predefinita: visibili subito, anche lontano dalla chiusura ---
req(f"/admin/gara/{nuova}/squadre/aggiungi", {"number": "1", "name": "A"})
req(f"/admin/gara/{nuova}/problemi/aggiungi", {"number": "1", "name": "P", "answer": "0001"})
req(f"/regia/{nuova}/display/aggiungi", {"name": "Schermo"})
schermo = db(f"SELECT id FROM displays WHERE competition_id={nuova}")[0][0]
pid_n = db(f"SELECT id FROM problems WHERE competition_id={nuova}")[0][0]
req(f"/admin/gara/{nuova}/avvia", {})
req(f"/inserimento/{nuova}/jolly", {"team_number": "01", "problem_number": "01"})
d = display(nuova)
check("modalità 'appena inseriti': jolly subito nel display",
      d["jolly_public"] is True and squadra(d, 1)["jolly_problem_id"] == pid_n)

# --- copia ---
st, h, _ = req("/admin/gara/1/copia", {})
copia = int(re.search(r"/gara/(\d+)", h["location"]).group(1))
check("la copia mantiene la scelta", db(f"SELECT jolly_reveal FROM competitions WHERE id={copia}")[0][0] == "deadline")
finish()
