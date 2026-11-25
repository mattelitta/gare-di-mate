"""Crash con due gare in corso: ognuna riprende dal suo minuto, un popup alla volta. Suite completa."""
import json
import re
import time

from _util import check, crash_server, finish, req, start_server


def elapsed(cid):
    return json.loads(req(f"/admin/api/gara/{cid}/stato")[2])["elapsed_seconds"]


def popup(html):
    return re.findall(r"mentre la gara <strong>(.*?)</strong>", html)


p = start_server()
st, h, _ = req("/admin/crea", {"name": "Seconda gara", "date": "2026-12-01", "duration_minutes": "90",
                               "threshold_minute": "60", "blackout_minute": "80"})
g2 = int(re.search(r"/gara/(\d+)/", h["location"]).group(1))
req("/admin/gara/1/avvia", {})
time.sleep(3)
req(f"/admin/gara/{g2}/avvia", {})
time.sleep(2)
prima = {1: elapsed(1), g2: elapsed(g2)}
crash_server(p)
time.sleep(6)
p = start_server()
dopo = {1: elapsed(1), g2: elapsed(g2)}
check("entrambe le gare riprendono dal proprio minuto", all(-1.2 <= dopo[c] - prima[c] < 3 for c in prima))
nomi = popup(req("/admin/")[2])
check("home: un solo popup alla volta", len(nomi) == 1, str(nomi))
check("ogni pagina gara mostra solo il proprio popup",
      popup(req("/admin/gara/1")[2]) == ["Gara di Prova"] and popup(req(f"/admin/gara/{g2}")[2]) == ["Seconda gara"])
primo = 1 if nomi[0] == "Gara di Prova" else g2
altro = g2 if primo == 1 else 1
home = req("/admin/")[2]
m = re.search(r'name="minutes"[^>]*value="(\d+)"', home).group(1)
s = re.search(r'name="seconds"[^>]*value="(\d+)"', home).group(1)
e_primo, e_altro = elapsed(primo), elapsed(altro)
req(f"/admin/gara/{primo}/ripresa", {"azione": "avanza", "minutes": m, "seconds": s, "torna": "home"})
check("'Avanza' sulla prima gara fa avanzare solo quella",
      abs((elapsed(primo) - e_primo) - (int(m) * 60 + int(s))) < 1.5 and elapsed(altro) - e_altro < 1.5)
nomi2 = popup(req("/admin/")[2])
check("poi compare il popup dell'altra gara", len(nomi2) == 1 and nomi2 != nomi)
e_altro = elapsed(altro)
req(f"/admin/gara/{altro}/ripresa", {"azione": "ignora", "minutes": "", "seconds": "", "torna": "home"})
check("'Riprendi senza avanzare' sull'altra: nessun salto, nessun popup rimasto",
      elapsed(altro) - e_altro < 1.5 and popup(req("/admin/")[2]) == [])
crash_server(p)
finish()
