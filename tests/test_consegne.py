"""Storico consegne: filtri, ordine, numerazione, filtri conservati dopo modifica/eliminazione."""
import re

from _util import check, db, finish, opener, req

team = {n: i for i, n in db("SELECT id, number FROM teams WHERE competition_id=1")}
prob = {n: i for i, n in db("SELECT id, number FROM problems WHERE competition_id=1")}
A, B = opener(), opener()  # due dispositivi (browser) diversi


def nrows(html):
    return html.count("hover:brightness-95")


req("/admin/gara/1/avvia", {})
req("/inserimento/1", op=A)
req("/inserimento/1", op=B)
for op, (t, p, a) in [(A, (1, 1, "0042")), (A, (2, 1, "0000")), (B, (1, 2, "0137")), (B, (3, 1, "0042"))]:
    st, _, b = req("/inserimento/1/soluzione",
                   {"team_number": f"{t:02d}", "problem_number": f"{p:02d}", "answer": a}, op=op)
    assert st == 303, (st, b[:200])

C = "/inserimento/1/consegne"
st, _, b = req(C, op=A)
check("senza filtri: 4 consegne", st == 200 and nrows(b) == 4 and "4 consegne" in b)
check("di default la più recente in alto (#4 prima di #1)", b.find('font-mono">4</td>') < b.find('font-mono">1</td>'))
st, _, b = req(C + "?ordine=crescente", op=A)
check("'più vecchie in alto' inverte l'ordine", b.find('font-mono">1</td>') < b.find('font-mono">4</td>'))
st, _, b = req(C + "?mie=1", op=A)
check("dispositivo A, solo le sue: 2", nrows(b) == 2 and "2 di 4 consegne" in b)
st, _, b = req(C + "?mie=1", op=B)
check("dispositivo B vede le sue, non quelle di A", nrows(b) == 2 and ">0000<" not in b and "0137" in b)
st, _, b = req(C + f"?squadra={team[1]}")
check("filtro squadra 01: 2", nrows(b) == 2)
st, _, b = req(C + f"?problema={prob[1]}")
check("filtro problema 01: 3", nrows(b) == 3)
st, _, b = req(C + f"?squadra={team[1]}&problema={prob[1]}&mie=1", op=A)
check("tre filtri insieme: 1", nrows(b) == 1)
st, _, b = req(C + "?squadra=&problema=")
check("'Tutte'/'Tutti' (parametri vuoti) non danno errore", st == 200 and nrows(b) == 4)
st, _, b = req(C + f"?squadra={team[4]}")
check("nessun risultato: messaggio dedicato", nrows(b) == 0 and "Nessuna consegna corrisponde ai filtri" in b)
st, _, b = req(C + f"?problema={prob[2]}")
check("numerazione cronologica conservata (P02 resta #3)", 'font-mono">3</td>' in b)

q = f"squadra={team[1]}"
sub_ids = re.findall(r"/consegne/(\d+)/modifica", req(C + "?" + q)[2])
st, _, b = req(f"{C}/{sub_ids[0]}/modifica?{q}")
check("pagina modifica conserva i filtri", st == 200 and f"/modifica?{q}" in b and f'consegne?{q}"' in b)
st, h, _ = req(f"{C}/{sub_ids[0]}/modifica?{q}", {"team_id": team[1], "problem_id": prob[1], "answer": "0042"})
check("dopo la modifica torna allo storico filtrato", st == 303 and h["location"] == f"{C}?{q}")
st, h, _ = req(f"{C}/{sub_ids[1]}/elimina?{q}", {})
check("dopo l'eliminazione torna allo storico filtrato", st == 303 and h["location"] == f"{C}?{q}")
check("eliminata: restano 3 consegne", nrows(req(C)[2]) == 3)
finish()
