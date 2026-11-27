"""Strumenti comuni ai test. I test vanno avviati da tests/run.py, che prepara una copia
del progetto (variabile GDM_APP) e una porta libera (GDM_PORT): il gare.db vero non viene toccato."""
import http.cookiejar
import os
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP = Path(os.environ["GDM_APP"])
PORT = int(os.environ["GDM_PORT"])
TLS_PORT = int(os.environ.get("GDM_TLS_PORT", "0"))
BASE = f"http://127.0.0.1:{PORT}"
REMOTE_IP = os.environ.get("GDM_REMOTE_IP", "")
REMOTE = f"https://{REMOTE_IP}:{TLS_PORT}" if REMOTE_IP else ""  # simula un dispositivo in rete
REMOTE_HTTP = f"http://{REMOTE_IP}:{PORT}" if REMOTE_IP else ""  # lo stesso dispositivo sulla porta HTTP
CERT = APP / "certificato" / "certificato.pem"
DB = APP / "gare.db"

sys.path.insert(0, str(APP))
sys.stdout.reconfigure(encoding="utf-8")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def tls_context(verify: bool = True) -> ssl.SSLContext:
    """Contesto HTTPS che si fida solo del certificato del server di prova (e ne controlla gli indirizzi)."""
    if not verify or not CERT.exists():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context(cafile=str(CERT))


def opener(verify: bool = True):
    """Un "browser": cookie propri, redirect non seguiti (per controllarli)."""
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), _NoRedirect(),
        urllib.request.HTTPSHandler(context=tls_context(verify)))


class _Lazy:
    """Il "browser" predefinito, creato al primo uso (quando il certificato del server esiste)."""
    _op = None

    def open(self, *a, **k):
        if _Lazy._op is None:
            _Lazy._op = opener()
        return _Lazy._op.open(*a, **k)


_default = _Lazy()


def req(path, data=None, op=None, base=None):
    """GET (o POST se data non è None). Ritorna (status, headers, testo)."""
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        r = (op or _default).open((base or BASE) + path, body, timeout=15)
        return r.status, r.headers, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode()


def db(sql, params=()):
    c = sqlite3.connect(DB)
    try:
        rows = c.execute(sql, params).fetchall()
        c.commit()
        return rows
    finally:
        c.close()


def wait_server(base=None):
    for _ in range(80):
        try:
            urllib.request.urlopen((base or BASE) + "/accesso", timeout=1)
            return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("il server di prova non risponde")


def start_server():
    log = open(APP / "server.log", "a", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "server.py", "--http-port", str(PORT), "--https-port", str(TLS_PORT)],
                         cwd=APP, stdout=log, stderr=log)
    wait_server()
    return p


def crash_server(p):
    """Termina il processo di colpo (nessuna chiusura ordinata), come un crash."""
    p.kill()
    p.wait()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def make_legacy_db(path: Path, with_data=True):
    """Database come quelli della versione 1.0.x (schema 0): senza le colonne e le tabelle
    aggiunte dalle migrazioni successive."""
    from sqlalchemy import create_engine
    from database import Base
    import models  # noqa: F401
    path.unlink(missing_ok=True)
    e = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(bind=e)
    e.dispose()
    c = sqlite3.connect(path)
    if with_data:
        c.execute("INSERT INTO competitions (id, name, date, threshold_minute, blackout_minute, status, "
                  "initial_value, n, k, first_delivery_bonuses_json, full_bonuses_json, duration_minutes, "
                  "jolly_time_minutes, num_qualified, final_reveal_count, total_paused_seconds, "
                  "revealed_positions, final_locked, display_theme, time_offset_seconds, insertions_locked, "
                  "created_at) VALUES "
                  "(1, 'Vecchia gara', '2026-01-01', 60, 80, 'ended', 40, 2, 1, '[20]', '[50]', 90, 30, 0, 3, "
                  "0, 0, 1, 'light', 0, 0, CURRENT_TIMESTAMP)")  # final_locked = 1: "bloccata" col vecchio sistema
        c.execute("INSERT INTO teams (id, competition_id, number, name, city, is_guest) VALUES (1, 1, 1, 'A', '', 0)")
        c.execute("INSERT INTO problems (id, competition_id, number, name, answer) VALUES (1, 1, 1, 'P1', '0042')")
        c.execute("INSERT INTO submissions (competition_id, team_id, problem_id, answer, is_correct, is_post_game, "
                  "game_seconds, submitted_at) VALUES (1, 1, 1, '0042', 1, 0, 120, CURRENT_TIMESTAMP)")
    for table, column in (("submissions", "device_id"), ("competitions", "time_offset_seconds"),
                          ("competitions", "last_alive_at"), ("competitions", "recovery_crash_at"),
                          ("competitions", "recovery_downtime_seconds"), ("competitions", "insertions_locked"),
                          ("competitions", "final_ranking_json"), ("competitions", "final_computed_at"),
                          ("competitions", "blackout_manual"), ("competitions", "blackout_manual_at")):
        c.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    c.execute("DROP TABLE time_adjustments")
    c.execute("PRAGMA user_version = 0")
    c.commit()
    c.close()


_results = []


def check(name, cond, extra=""):
    _results.append(bool(cond))
    print(("OK  " if cond else "FAIL") + " " + name + (f"  [{extra}]" if extra else ""))


def skip(reason):
    print(f"SALTATO: {reason}")


def finish():
    print(f"\n{sum(_results)}/{len(_results)} superati")
    sys.exit(0 if all(_results) else 1)
