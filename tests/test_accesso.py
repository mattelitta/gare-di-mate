"""Password di accesso e permessi dei dispositivi in rete (Inserimento e Display sì, Admin e Regia no)."""
import sys
import time

from _util import REMOTE, check, finish, opener, req, skip

if not REMOTE:
    skip("nessun indirizzo secondario per simulare un dispositivo in rete")
    sys.exit(0)

remote = opener()
local = opener()


def r(path, data=None):
    return req(path, data, op=remote, base=REMOTE)


st, h, _ = r("/inserimento/")
check("remoto senza cookie -> pagina di accesso", st == 303 and h["location"].startswith("/accesso?next=/inserimento/"))
st, _, b = r("/accesso")
check("password non impostata -> messaggio", st == 200 and "non è ancora configurato" in b)
check("pagina di accesso: tasto del tema sì, 'Esci' no", 'id="tasto-tema"' in b and 'href="/esci"' not in b)
st, _, css = r("/static/css/scuro.css")
check("foglio della modalità scura raggiungibile anche senza accesso", st == 200 and "html.scuro" in css)
st, _, _ = r("/display/api/1/schermo/1/stato")
check("API display senza cookie -> 401", st == 401)
st, _, b = req("/", op=local)
check("il computer server passa e vede Admin", st == 200 and 'href="/admin/"' in b)
st, h, _ = r("/admin/password-accesso", {"password": "segreta-123"})
check("un remoto non può impostare la password", st == 303 and h["location"].startswith("/accesso"))
st, _, _ = req("/admin/password-accesso", {"password": "segreta-123"}, op=local)
check("il computer server imposta la password", st == 303)

t0 = time.time()
st, _, b = r("/accesso", {"password": "sbagliata", "next": "/inserimento/"})
check("password errata -> 401 con ritardo", st == 401 and "Password errata" in b and time.time() - t0 >= 1)
st, h, _ = r("/accesso", {"password": "segreta-123", "next": "//evil.com"})
check("'next' verso un altro sito neutralizzato", st == 303 and h["location"] == "/")
st, h, _ = r("/accesso", {"password": "segreta-123", "next": "/inserimento/"})
check("password corretta -> redirect a next", st == 303 and h["location"] == "/inserimento/")

st, h, _ = r("/")
check("remoto: la home porta all'inserimento", st == 303 and h["location"] == "/inserimento/")
st, _, b = r("/inserimento/")
check("remoto: barra con solo Inserimento, Display, Esci",
      st == 200 and 'href="/esci"' in b and 'href="/display/"' in b and 'href="/regia/"' not in b)
req("/regia/1/display/aggiungi", {"name": "Proiettore"}, op=local)
for p in ("/inserimento/1", "/display/", "/display/1", "/display/1/schermo/1"):
    st, _, _ = r(p)
    check(f"remoto apre {p}", st == 200)
st, _, b = r("/display/api/1/schermo/1/stato")
check("remoto: API display con dati", st == 200 and '"view"' in b)
st, _, b = r("/inserimento/api/firma")
check("remoto: firma dell'elenco gare per l'aggiornamento automatico", st == 200 and len(b) == 16)
st, h, _ = r("/admin/api/gara/1/firma")
check("remoto: nessuna firma delle pagine Admin e Regia", st == 303 and "/admin" not in h["location"])
for p in ("/admin/", "/regia/", "/regia/1", "/admin/gara/1/vista/ranking", "/admin/api/gara/1/vista/ranking/stato"):
    st, h, _ = r(p)
    check(f"remoto bloccato su {p}", st == 303 and h["location"] == "/inserimento/")
st, h, _ = r("/regia/1/display/1/vista", {"view": "ranking"})
check("remoto non può cambiare vista dalla regia", st == 303 and h["location"] == "/inserimento/")

req("/admin/password-accesso", {"password": "nuova-password"}, op=local)
st, _, _ = r("/inserimento/")
check("cambiare password disconnette i dispositivi", st == 303)
r("/accesso", {"password": "nuova-password", "next": "/"})
st, h, _ = r("/esci")
check("esci -> pagina di accesso", st == 303 and h["location"] == "/accesso")
st, _, _ = r("/inserimento/")
check("dopo esci serve di nuovo la password", st == 303)
finish()
