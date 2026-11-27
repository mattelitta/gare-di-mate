"""Oscuramento: automatico (minuto previsto e fine gara) e manuale dall'admin; scadenze nella pagina admin."""
import json
import re

from _util import APP, check, db, finish, req


def oscurata():
    return json.loads(req("/display/api/1/schermo/1/stato")[2])["blackout_active"]


def toggle(valore):
    return req("/admin/gara/1/oscuramento", {"oscurata": "1"} if valore else {})


def nota():
    m = re.search(r"Classifica oscurata\s*</label>\s*<span[^>]*>\s*(.*?)\s*</span>", req("/admin/gara/1")[2], re.S)
    return " ".join(m.group(1).split()) if m else ""


req("/regia/1/display/aggiungi", {"name": "Schermo"})
check("prima della partenza: classifica visibile, stato automatico", not oscurata() and nota().startswith("Automatico"))
toggle(True)
check("oscurata a mano anche prima della partenza", oscurata() and nota() == "Impostato a mano")
toggle(False)
check("mostrata di nuovo a mano", not oscurata())

req("/admin/gara/1/avvia", {})
check("gara in corso prima del minuto di oscuramento: visibile", not oscurata())
st, h, _ = toggle(True)
check("oscurata a mano durante la gara (con esito)", oscurata() and "oscurata" in h["location"])
toggle(False)
check("mostrata a mano durante la gara", not oscurata())

req("/admin/gara/1/avanza-tempo", {"minutes": "7", "seconds": "0"})  # minuto di oscuramento della gara di prova
check("raggiunto il minuto di oscuramento si oscura da sola (anche se era stata mostrata a mano)",
      oscurata() and nota().startswith("Automatico"))
toggle(False)
check("dopo lo scatto automatico si può mostrare a mano", not oscurata() and nota() == "Impostato a mano")
req("/admin/gara/1/avanza-tempo", {"minutes": "1", "seconds": "0"})
check("e resta visibile finché non c'è un nuovo scatto automatico", not oscurata())
req("/admin/gara/1/termina", {})
check("'Termina' la oscura di nuovo", oscurata() and nota().startswith("Automatico"))
toggle(False)
check("a gara terminata si può mostrare a mano", not oscurata())

viewer = (APP / "gdm" / "templates" / "display" / "viewer.html").read_text(encoding="utf-8")
for funzione in ("renderRanking", "renderTeamList", "renderCompStatus"):
    corpo = viewer.split(f"function {funzione}()")[1][:120]
    check(f"display: {funzione} mostra la schermata di oscuramento", "schermataOscurata()" in corpo)
emoji = re.findall(r"[\U0001F300-\U0001FAFF☀-➿⬀-⯿]", viewer)
check("nessuna emoji negli schermi pubblici", not emoji, str(emoji))

# --- scadenze nella pagina admin (gara di prova: jolly 5, soglia, oscuramento 7, durata 10) ---
db("UPDATE competitions SET status='created', started_at=NULL, ended_at=NULL, time_offset_seconds=0 WHERE id=1")
db("DELETE FROM time_adjustments")
req("/admin/gara/1/avvia", {})
g = req("/admin/gara/1")[2]
scadenze = re.findall(r'data-prima="([^"]+)"', g)
check("scadenze in ordine di tempo: jolly (5), oscuramento (7), valori (8), fine gara (10)",
      scadenze == ["Chiusura jolly", "Oscuramento", "Congelamento valori", "Fine gara"], str(scadenze))
check("senza tempo per le domande sul testo: nessuna scadenza, parametro 'non previste'",
      "Domande sul testo" not in scadenze and "Non previste" in g)
db("UPDATE competitions SET questions_minutes=6 WHERE id=1")
g = req("/admin/gara/1")[2]
scadenze = re.findall(r'data-prima="([^"]+)"', g)
check("domande sul testo al minuto 6: tra le scadenze, al loro posto in ordine di tempo",
      scadenze == ["Chiusura jolly", "Domande sul testo", "Oscuramento", "Congelamento valori", "Fine gara"], str(scadenze))
stato_ins = json.loads(req("/inserimento/1/stato")[2])
pagina_ins = req("/inserimento/1")[2]
check("inseritori: domande sul testo e scelta jolly nella barra, in ordine di tempo",
      stato_ins["questions_seconds"] == 360 and "scadenze()" in pagina_ins
      and "'Domande sul testo'" in pagina_ins and "l.sort((a, b) => a.sec - b.sec)" in pagina_ins)
check("colori: giallo negli ultimi 2 minuti per tutti; rosso (primo minuto dopo) solo per jolly e domande",
      g.count('data-rosso="1"') == 2 and re.search(r'data-prima="Chiusura jolly"[^>]*data-rosso', g)
      and re.search(r'data-prima="Domande sul testo"[^>]*data-rosso', g)
      and "AVVISO_SECONDI = 120, SCADUTO_SECONDI = 60" in g
      and "this.evidenza(this.jollySec, true)" in pagina_ins and "this.evidenza(this.domandeSec, true)" in pagina_ins
      and "classeFase(evidenza(durata))" in pagina_ins)
check("inseritori: congelamento e oscuramento non compaiono (solo nella pagina Admin)",
      "threshold_seconds" not in stato_ins and "blackout_seconds" not in stato_ins
      and "'Congelamento valori'" not in pagina_ins and "'Oscuramento'" not in pagina_ins)
db("UPDATE competitions SET blackout_minute=duration_minutes WHERE id=1")
scadenze = re.findall(r'data-prima="([^"]+)"', req("/admin/gara/1")[2])
check("se l'oscuramento coincide con la fine della gara non compare tra le scadenze", "Oscuramento" not in scadenze, str(scadenze))
req("/admin/gara/1/termina", {})
check("a gara terminata le scadenze non compaiono", 'id="scadenze"' not in req("/admin/gara/1")[2])

# --- schermi interni: ignorano l'oscuramento ---
req("/regia/1/display/aggiungi", {"name": "Sala staff"})
interno = db("SELECT id FROM displays WHERE name='Sala staff'")[0][0]
regia = req("/regia/1")[2]
check("regia: interruttore 'Interno' per ogni display, spento di default",
      regia.count('/interno"') == 2 and db(f"SELECT internal FROM displays WHERE id={interno}")[0][0] == 0)
req(f"/regia/1/display/{interno}/interno", {"interno": "1"})
check("regia: schermo segnato come interno (etichetta accanto al nome)",
      db(f"SELECT internal FROM displays WHERE id={interno}")[0][0] == 1 and ">Interno</span>" in req("/regia/1")[2])
toggle(True)
pubblico = json.loads(req("/display/api/1/schermo/1/stato")[2])
staff = json.loads(req(f"/display/api/1/schermo/{interno}/stato")[2])
check("con l'oscuramento lo schermo pubblico non riceve punteggi", pubblico["blackout_active"] and pubblico["teams"] == [])
check("lo schermo interno ignora l'oscuramento e riceve la classifica",
      not staff["blackout_active"] and staff["teams"] and "total" in staff["teams"][0])
check("lo schermo interno mostra l'avviso 'oscuramento ignorato'",
      staff["blackout_ignored"] is True and pubblico["blackout_ignored"] is False
      and 'id="hdr-interno"' in req(f"/display/1/schermo/{interno}")[2])
req(f"/regia/1/display/{interno}/interno", {})
staff = json.loads(req(f"/display/api/1/schermo/{interno}/stato")[2])
check("tolta la spunta torna come gli altri (oscurato)", staff["blackout_active"] and staff["teams"] == [])
toggle(False)
finish()
