"""Sicurezza in rete: HTTPS, sessioni per dispositivo, limiti ai tentativi, controlli su origine e nome
del server, intestazioni, e dati nascosti che non devono nemmeno arrivare ai display."""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from _util import (BASE, CERT, REMOTE, REMOTE_HTTP, REMOTE_IP, check, db, finish, opener, req, skip)

if not REMOTE:
    skip("nessun indirizzo secondario per simulare un dispositivo in rete")
    sys.exit(0)

PASSWORD = "segreta-123"


def r(path, data=None, op=None):
    return req(path, data, op=op, base=REMOTE)


def raw(url, data=None, headers=None, op=None):
    """Richiesta con intestazioni a scelta: (status, headers, testo)."""
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    rq = urllib.request.Request(url, body, headers=headers or {})
    try:
        resp = (op or opener()).open(rq, timeout=15)
        return resp.status, resp.headers, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode()


def entra(op):
    return r("/accesso", {"password": PASSWORD, "next": "/inserimento/"}, op=op)


# --- certificato ---
from cryptography import x509  # noqa: E402
cert = x509.load_pem_x509_certificate(CERT.read_bytes())
san = {str(ip) for ip in cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
       .get_values_for_type(x509.IPAddress)}
check("certificato creato al primo avvio, valido per gli indirizzi del computer", REMOTE_IP in san and "127.0.0.1" in san)
check("la chiave privata resta nella cartella dei dati, fuori dal progetto pubblicato",
      (CERT.parent / "chiave.pem").exists() and "dati/" in (CERT.parents[2] / ".gitignore").read_text(encoding="utf-8"))

# --- porta HTTP: per gli altri dispositivi solo il rimando a HTTPS ---
st, h, b = req("/inserimento/1?x=1", base=REMOTE_HTTP)
check("remoto su HTTP: rimandato all'indirizzo HTTPS, stesso percorso",
      st == 301 and h["location"] == f"{REMOTE}/inserimento/1?x=1")
check("remoto su HTTP: nessun contenuto e nessun cookie di accesso",
      "Gare di Mate" not in b and all("gdm-accesso" not in c for c in h.get_all("set-cookie") or []))
st, h, _ = req("/inserimento/1/soluzione", {"team_number": "01"}, base=REMOTE_HTTP)
check("remoto su HTTP: anche gli invii vengono rimandati (307), non eseguiti", st == 307)

# --- password e sessioni ---
req("/admin/password-accesso", {"password": PASSWORD})
st, h, _ = req("/admin/password-accesso", {"password": "corta"})
check("password sotto gli 8 caratteri rifiutata con avviso", "errore=" in h["location"])
check("la password rifiutata non sostituisce quella valida", entra(opener())[0] == 303)

a, b_ = opener(), opener()
st, h, _ = entra(a)
cookie = next((c for c in h.get_all("set-cookie", []) if c.startswith("__Host-gdm-accesso=")), "")
attr = cookie.lower()
check("cookie di accesso: __Host-, Secure, HttpOnly, SameSite=Strict, Path=/, senza dominio",
      cookie and "secure" in attr and "httponly" in attr and "samesite=strict" in attr
      and "path=/" in attr and "domain" not in attr, cookie)
token = cookie.split("=", 1)[1].split(";")[0]
entra(b_)
righe = db("SELECT token_hash FROM access_sessions")
check("ogni accesso è una sessione a sé (due dispositivi, due sessioni)", len(righe) >= 3)
check("nel database c'è solo l'impronta del token, non il token", all(token not in rr[0] for rr in righe))
check("entrambi i dispositivi lavorano", r("/inserimento/", op=a)[0] == 200 and r("/inserimento/", op=b_)[0] == 200)

home = req("/admin/")[2]
check("Admin: elenco dei dispositivi collegati con indirizzo", "Dispositivi collegati" in home and REMOTE_IP in home)
sid = db("SELECT id FROM access_sessions ORDER BY id DESC LIMIT 1")[0][0]  # la sessione di b_
st, h, _ = req(f"/admin/dispositivi/{sid}/scollega", {})
check("Admin scollega un dispositivo (esito)", "esito=" in h["location"])
check("il dispositivo scollegato deve rifare l'accesso", r("/inserimento/", op=b_)[0] == 303)
check("gli altri dispositivi restano collegati", r("/inserimento/", op=a)[0] == 200)
st, h, _ = r(f"/admin/dispositivi/{sid}/scollega", {}, op=a)
check("un dispositivo in rete non può scollegare gli altri", st == 303 and "/admin/" not in h["location"])

falso = opener()
st, _, _ = raw(f"{REMOTE}/inserimento/", headers={"Cookie": "__Host-gdm-accesso=" + "x" * 43}, op=falso)
check("token inventato rifiutato", st == 303)
st, _, _ = raw(f"{REMOTE}/inserimento/", headers={"Cookie": "accesso=" + "a" * 64}, op=opener())
check("il vecchio cookie unico della 1.2 non vale più", st == 303)

prima = db("SELECT COUNT(*) FROM access_sessions")[0][0]
r("/esci", op=a)
check("'Esci' chiude la sessione anche sul server",
      r("/inserimento/", op=a)[0] == 303 and db("SELECT COUNT(*) FROM access_sessions")[0][0] == prima - 1)
entra(a)
entra(b_)
req("/admin/dispositivi/scollega-tutti", {})
check("'Scollega tutti': nessuno resta dentro",
      r("/inserimento/", op=a)[0] == 303 and r("/inserimento/", op=b_)[0] == 303
      and db("SELECT COUNT(*) FROM access_sessions")[0][0] == 0)

# --- limite ai tentativi ---
c = opener()
for _ in range(5):
    r("/accesso", {"password": "sbagliata", "next": "/"}, op=c)
st, _, b = entra(c)
check("dopo 5 password errate anche quella giusta è rifiutata per un po' (429)",
      st == 429 and "Troppi tentativi" in b)
home = req("/admin/")[2]
check("Admin: blocco segnalato con il tasto per toglierlo", "tentativi di accesso bloccati" in home and "/admin/sicurezza/sblocca" in home)
check("Admin: eventi recenti (password errata, blocco)", "password errata" in home and "bloccato per 60 s" in home)
req("/admin/sicurezza/sblocca", {})
check("tolto il blocco, l'accesso funziona", entra(c)[0] == 303)

# --- origine, nome del server, intestazioni ---
st, _, _ = raw(f"{BASE}/admin/", headers={"Host": "gare.example.com"})
check("nome del server sconosciuto rifiutato (DNS rebinding)", st == 400)
st, _, _ = raw(f"{BASE}/admin/", headers={"Host": f"localhost:{BASE.rsplit(':', 1)[1]}"})
check("localhost ammesso", st == 200)
req("/admin/gara/1/avvia", {})
cookie_c = next(ck for ck in c.handlers if isinstance(ck, urllib.request.HTTPCookieProcessor)).cookiejar
intestazione = "; ".join(f"{k.name}={k.value}" for k in cookie_c)
st, _, b = raw(f"{REMOTE}/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"},
               headers={"Origin": "https://sito-malevolo.example", "Cookie": intestazione})
check("invio da un'altra origine rifiutato (CSRF)", st == 403)
check("...e nessuna consegna registrata", db("SELECT COUNT(*) FROM submissions")[0][0] == 0)
st, _, _ = raw(f"{REMOTE}/inserimento/1/soluzione", {"team_number": "01", "problem_number": "01", "answer": "0042"},
               headers={"Origin": REMOTE, "Cookie": intestazione})
check("invio dalla stessa origine accettato", st == 303 and db("SELECT COUNT(*) FROM submissions")[0][0] == 1)
st, _, _ = raw(f"{BASE}/admin/gara/1/pausa", {}, headers={"Origin": "null"})
check("origine 'null' rifiutata anche sul computer server", st == 403 and
      db("SELECT status FROM competitions WHERE id=1")[0][0] == "running")
st, h, _ = r("/inserimento/", op=c)
check("intestazioni: niente iframe, nosniff, nessuna cache",
      h.get("x-frame-options") == "DENY" and "frame-ancestors 'none'" in h.get("content-security-policy", "")
      and h.get("x-content-type-options") == "nosniff" and h.get("cache-control") == "no-store")
st, h, _ = r("/static/css/scuro.css", op=c)
check("i file statici restano in cache", h.get("cache-control") != "no-store")

# --- i display ricevono solo ciò che mostrano ---
req("/regia/1/display/aggiungi", {"name": "Schermo"})
disp = db("SELECT id FROM displays WHERE competition_id=1")[0][0]
api = f"/display/api/1/schermo/{disp}/stato"
raw(f"{REMOTE}/display/1/schermo/{disp}", headers={"X-Forwarded-For": "6.6.6.6"}, op=c)
check("l'indirizzo del display non si può falsificare con X-Forwarded-For",
      db(f"SELECT ip_address FROM displays WHERE id={disp}")[0][0] == REMOTE_IP)
risposte = {n: a for n, a in db("SELECT number, answer FROM problems WHERE competition_id=1")}
for t, p in ((2, 2), (1, 2)):
    req("/inserimento/1/soluzione", {"team_number": f"{t:02d}", "problem_number": f"{p:02d}", "answer": risposte[p]})
d = json.loads(r(api, op=c)[2])
check("senza oscuramento i display hanno i punteggi", d["teams"] and "total" in d["teams"][0])
req("/admin/gara/1/oscuramento", {"oscurata": "1"})
st, _, b = r(api, op=c)
d = json.loads(b)
check("con l'oscuramento il server non invia punteggi né griglia",
      d["blackout_active"] and d["teams"] == [] and '"total"' not in b and "problem_contributions" not in b)
check("con l'oscuramento niente numero di risolutori", all(p["num_solvers"] is None for p in d["problems"]))
req("/admin/gara/1/termina", {})
req("/admin/gara/1/calcola-finale", {})
nomi = [n for (n,) in db("SELECT name FROM teams WHERE competition_id=1")]
st, _, b = r(api, op=c)
d = json.loads(b)
check("classifica finale prima della rivelazione: solo segnaposto, nessun nome né punto",
      d["final_ready"] and d["final_ranking"] and all(t.get("hidden") for t in d["final_ranking"])
      and not any(n in b for n in nomi))
req("/regia/1/rivela", {})
st, _, b = r(api, op=c)
d = json.loads(b)
in_gara = [t for t in d["final_ranking"] if not t.get("is_guest")]
svelate = [t for t in in_gara if not t.get("hidden")]
foto = [t for t in json.loads(db("SELECT final_ranking_json FROM competitions WHERE id=1")[0][0]) if not t["is_guest"]]
check("dopo una rivelazione: solo l'ultima posizione, con nome e punti",
      len(svelate) == 1 and in_gara[-1] == foto[-1] and all(t.get("hidden") for t in in_gara[:-1]))
check("le posizioni restano tutte (il display disegna i segnaposto)", len(in_gara) == len(foto))
nascosti = [t["name"] for t in foto[:-1]]
check("i nomi non ancora svelati non arrivano al display", not any(re.search(re.escape(n), b) for n in nascosti))
finish()
