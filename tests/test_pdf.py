"""Esportazione in PDF dei risultati (classifica finale, valori dei problemi, stato della gara)."""
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from _util import BASE, REMOTE, check, db, finish, opener, req
import urllib.request

G = "/admin/gara/1"
PDF = f"{G}/esporta-pdf"


def scarica():
    """(status, headers, bytes) senza decodificare il contenuto."""
    try:
        r = opener().open(f"{BASE}{PDF}", timeout=30)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def errore(headers):
    return parse_qs(urlsplit(headers.get("location", "")).query).get("errore", [""])[0]


risposta = {n: a for n, a in db("SELECT number, answer FROM problems WHERE competition_id=1")}
check("gara non terminata: nessun tasto", "esporta-pdf" not in req(G)[2])
st, h, _ = scarica()
check("gara non terminata: export rifiutato", st == 303 and "a gara terminata" in errore(h), errore(h))

req(f"{G}/avvia", {})
req("/inserimento/1/jolly", {"team_number": "01", "problem_number": "02"})
for t, p, a in [(1, 1, risposta[1]), (1, 2, risposta[2]), (2, 1, "9999"), (2, 1, risposta[1]), (3, 3, "1")]:
    req("/inserimento/1/soluzione", {"team_number": f"{t:02d}", "problem_number": f"{p:02d}", "answer": a})
req(f"{G}/termina", {})
st, h, _ = scarica()
check("terminata ma classifica non calcolata: rifiutato", st == 303 and "classifica finale" in errore(h))

req(f"{G}/calcola-finale", {})
check("classifica calcolata: tasto presente", 'href="/admin/gara/1/esporta-pdf"' in req(G)[2])
st, h, contenuto = scarica()
pagine = len(re.findall(rb"/Type\s*/Page\b", contenuto))
check("PDF scaricato: tipo, nome del file, 3 pagine (classifica, valori, stato)",
      st == 200 and h["content-type"] == "application/pdf" and contenuto.startswith(b"%PDF")
      and "attachment" in h["content-disposition"] and pagine == 3,
      f"{st} {h.get('content-type')} {unquote(h.get('content-disposition', ''))} pagine={pagine}")
if os.environ.get("GDM_PDF_OUT"):
    Path(os.environ["GDM_PDF_OUT"]).write_bytes(contenuto)

team1 = db("SELECT id FROM teams WHERE competition_id=1 AND number=1")[0][0]
req(f"{G}/penalizzazioni/aggiungi", {"team_id": team1, "value": "-5", "note": "prova"})
st, h, _ = scarica()
check("punteggi cambiati dopo il calcolo: rifiutato con invito a ricalcolare",
      st == 303 and "ricalcolarla" in errore(h), errore(h))
req(f"{G}/calcola-finale", {})
st, _, contenuto = scarica()
check("dopo il ricalcolo: di nuovo scaricabile", st == 200 and contenuto.startswith(b"%PDF"))
if os.environ.get("GDM_PDF_OUT"):  # con una penalizzazione: colonna "Bonus" e spiegazione presenti
    Path(os.environ["GDM_PDF_OUT"]).with_suffix(".penalita.pdf").write_bytes(contenuto)

# Molte squadre: lo stato della gara continua su più pagine
for n in range(10, 50):
    req(f"{G}/squadre/aggiungi", {"number": str(n), "name": f"Squadra con un nome piuttosto lungo {n}", "city": "Città"})
for n in range(5, 31):  # 30 problemi: celle strette, testo rimpicciolito
    req(f"{G}/problemi/aggiungi", {"number": str(n), "name": f"Problema {n}", "answer": "0001"})
st, h, _ = req("/inserimento/1/consegne/aggiungi",
                {"team_id": team1, "problem_id": db("SELECT id FROM problems WHERE competition_id=1 AND number=30")[0][0],
                 "answer": "9999", "minutes": "0", "seconds": "0"})  # la gara di prova dura 0 s
check("errore sul problema 30 aggiunto dall'Admin", "esito=" in h.get("location", ""), h.get("location"))
req(f"{G}/calcola-finale", {})
st, _, contenuto = scarica()
pagine = len(re.findall(rb"/Type\s*/Page\b", contenuto))
check("44 squadre e 30 problemi: classifica e stato su più pagine", st == 200 and pagine >= 5, f"pagine={pagine}")
if os.environ.get("GDM_PDF_OUT"):
    Path(os.environ["GDM_PDF_OUT"]).with_suffix(".molte.pdf").write_bytes(contenuto)

if REMOTE:
    remoto = opener()
    req("/admin/password-accesso", {"password": "segreta-123"})
    req("/accesso", {"password": "segreta-123", "next": "/inserimento/"}, op=remoto, base=REMOTE)
    st, _, _ = req(PDF, op=remoto, base=REMOTE)
    check("dispositivo in rete: export non permesso", st in (303, 403))
finish()
