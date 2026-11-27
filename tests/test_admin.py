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
st, h, _ = req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"})
check("soluzione rifiutata prima della partenza, con avviso", st == 303 and "errore=" in h["location"])
st, h, _ = req("/inserimento/1/jolly", {"team_number": "01", "problem_number": "01"})
check("jolly rifiutato prima della partenza, con avviso", st == 303 and "errore=" in h["location"])
check("nulla registrato prima della partenza",
      db("SELECT COUNT(*) FROM submissions")[0][0] == 0 and db("SELECT COUNT(*) FROM jolly_choices")[0][0] == 0)
req("/admin/gara/1/avvia", {})
check("dopo l'avvio lo stato è running", json.loads(req("/inserimento/1/stato")[2])["status"] == "running")
st, _, _ = req("/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"})
check("soluzione accettata dopo la partenza", st == 303)
sid = re.findall(r"/consegne/(\d+)/modifica", req("/inserimento/1/consegne")[2])[0]
testo = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", req(f"/inserimento/1/consegne/{sid}/modifica")[2], flags=re.S))
check("modifica consegna: nessuna '()' vuota nel testo", "()" not in testo)

# --- finestre di conferma: "Annulla" selezionato per le azioni pericolose, "Conferma" per le consegne ---
import pathlib
radice = pathlib.Path(__file__).resolve().parent.parent / "templates"
con_confirm = [str(p.relative_to(radice)) for p in radice.rglob("*.html")
               if "confirm(" in re.sub(r"\{#.*?#\}", "", p.read_text(encoding="utf-8"), flags=re.S)]
check("nessun confirm() del browser (seleziona sempre OK)", not con_confirm, ", ".join(con_confirm))
home = req("/admin/")[2]
check("finestra di conferma comune: parte su Annulla",
      'id="dialogo-conferma"' in home and "getElementById('dialogo-conferma-no').focus()" in home)
g = req("/admin/gara/1")[2]
check("termina gara chiede conferma (gara in corso)",
      re.search(r'action="/admin/gara/1/termina"\s+data-conferma="Terminare definitivamente', g) is not None)
check("elimina gara chiede conferma", 'data-conferma="Eliminare la gara' in home)
# avvio in due passi: "Prepara l'avvio…" apre il riepilogo, la gara parte solo con "Avvia ora"
st, h, _ = req("/admin/crea", {"name": "Avvio", "threshold_minute": "60", "blackout_minute": "80"})
av = re.search(r"/gara/(\d+)/", h["location"]).group(1)
pagina = req(f"/admin/gara/{av}")[2]
check("gara vuota: avviso nel riepilogo di avvio", "non ci sono né squadre né problemi" in pagina)
req(f"/admin/gara/{av}/squadre/aggiungi", {"number": "1", "name": "A"})
req(f"/admin/gara/{av}/squadre/aggiungi", {"number": "2", "name": "B", "is_guest": "on"})
req(f"/admin/gara/{av}/problemi/aggiungi", {"number": "1", "name": "P", "answer": "0001"})
pagina = req(f"/admin/gara/{av}")[2]
riepilogo = pagina.split('id="dialogo-avvio"')[1].split("</dialog>")[0] if 'id="dialogo-avvio"' in pagina else ""
check("tasto 'Prepara l'avvio…' che apre il riepilogo (non invia nulla)",
      "Prepara l'avvio…" in pagina and 'type="button" onclick="apriAvvio()"' in pagina)
check("riepilogo: squadre (con ospiti), problemi, durata, n e k, ora attuale, nessun avviso",
      re.search(r"Squadre</span>\s*<span[^>]*>2 <span[^>]*>\(di cui 1 ospite\)", riepilogo) is not None
      and re.search(r"Problemi</span>\s*<span[^>]*>1<", riepilogo) is not None
      and "90 min" in riepilogo and "n = 2, k = 1" in riepilogo and 'id="avvio-ora"' in riepilogo and "non ci sono" not in riepilogo)
check("riepilogo: la gara parte solo con 'Avvia ora', cursore su Annulla",
      f'action="/admin/gara/{av}/avvia"' in riepilogo and "Avvia ora</button>" in riepilogo
      and "getElementById('avvio-annulla').focus()" in pagina)
check("ancora da avviare dopo aver aperto la pagina", db(f"SELECT status FROM competitions WHERE id={av}")[0][0] == "created")
req(f"/admin/gara/{av}/avvia", {})
check("dopo l'avvio niente più riepilogo di avvio", 'id="dialogo-avvio"' not in req(f"/admin/gara/{av}")[2])

ins = req("/inserimento/1")[2]
check("consegna: tasto Conferma selezionato all'apertura",
      'x-ref="conferma"' in ins and "this.$refs.conferma.focus()" in ins)

# --- modalità scura locale: nelle pagine di lavoro sì, nei display no ---
for pagina in ("/admin/", "/admin/gara/1", "/inserimento/1", "/inserimento/1/consegne", "/regia/1"):
    b = req(pagina)[2]
    check(f"{pagina}: modalità scura disponibile (tasto e tema letto dal browser)",
          'href="/static/css/scuro.css"' in b and 'id="tasto-tema"' in b and "localStorage.getItem('gdm-tema')" in b)
req("/regia/1/display/aggiungi", {"name": "Tema"})
disp = db("SELECT id FROM displays WHERE competition_id=1 ORDER BY id DESC")[0][0]
viewer = req(f"/display/1/schermo/{disp}")[2]
check("schermo del display: nessuna modalità scura delle pagine di lavoro",
      viewer and "scuro.css" not in viewer and "gdm-tema" not in viewer)
# --- vista "Matrice" ---
check("regia: tasto della vista Matrice", 'value="matrix"' in req("/regia/1")[2] and ">\n          Matrice\n" in req("/regia/1")[2])
req(f"/regia/1/display/{disp}/vista", {"view": "matrix"})
check("vista Matrice impostata sul display", db(f"SELECT current_view FROM displays WHERE id={disp}")[0][0] == "matrix")
matrice = viewer.split("function renderMatrix()")[1].split("// --- FINAL RANKING")[0] if "function renderMatrix()" in viewer else ""
check("matrice: nascosta con l'oscuramento, solo numeri, colori e jolly (niente nomi, valori, punti)",
      "if (state.blackout_active) return schermataOscurata();" in matrice
      and "t.name" not in matrice and "p.value" not in matrice and "problem_contributions" not in matrice
      and "text = errors" in matrice
      and "const isJolly = t.jolly_problem_id === p.id;" in matrice and "ring-2 ring-yellow-400" in matrice)
check("matrice: disegnata sia al cambio di vista sia negli aggiornamenti",
      viewer.count("case 'matrix':") == 2)

css = req("/static/css/scuro.css")[2]
check("foglio scuro: sfondo pagina scuro anche con la classe bg-gray-100 del body",
      "html.scuro body.bg-gray-100" in css and "color-scheme: dark" in css)

# --- il computer server è riconosciuto solo da 127.0.0.1 ---
st, _, home = req("/", base=BASE)
check("127.0.0.1: barra completa e Admin raggiungibile",
      'href="/regia/"' in home and 'href="/esci"' not in home and req("/admin/", base=BASE)[0] == 200)
st, h, _ = req("/admin/", base=f"http://{lan_ip()}:{PORT}")
check("dal suo IP di rete il server è un dispositivo come gli altri: rimandato all'indirizzo HTTPS",
      st == 301 and h["location"].startswith(f"https://{lan_ip()}:"))
finish()
