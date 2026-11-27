"""Accesso degli altri dispositivi della rete.

- Il computer server (127.0.0.1) non ha bisogno di accesso: è l'unico che apre Admin e Regia.
- Gli altri dispositivi entrano con la password globale. Ogni accesso riuscito crea una sessione
  propria (token casuale nel cookie, impronta nel database), che l'Admin vede e può revocare.
- Permessi: ogni sessione ha un ruolo; il ruolo dice quali aree può aprire (vedi ROLES).
  Oggi c'è solo 'completo' (Inserimento e Display), ma i controlli passano già tutti da
  `session_allows`, così gli accessi parziali futuri si aggiungono qui.
- Tentativi di accesso limitati per indirizzo e in totale (vedi LoginLimiter).
"""
import hashlib
import hmac
import json
import secrets
import socket
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Request

from gdm.database import SessionLocal
from gdm.models import AccessSession, Setting

# Prefisso __Host-: il browser lo accetta solo da HTTPS, senza dominio e con Path=/, quindi
# nessuno può impostarlo dalla porta HTTP o da un altro indirizzo.
COOKIE_NAME = "__Host-gdm-accesso"
SESSION_MAX_IDLE = timedelta(days=30)   # una sessione inutilizzata per 30 giorni scade
COOKIE_MAX_AGE = 30 * 24 * 3600
LAST_SEEN_EVERY = 30                    # secondi tra un aggiornamento di last_seen e il successivo
LOOPBACK = ("127.0.0.1", "::1")
MIN_PASSWORD = 8

DEVICE_COOKIE = "dispositivo"
DEVICE_COOKIE_MAX_AGE = 400 * 24 * 3600  # massimo consentito dai browser

# Aree dell'applicazione aperte agli altri dispositivi e permesso richiesto da ciascuna.
PERM_INSERIMENTO = "inserimento"
PERM_DISPLAY = "display"
ROLES = {
    "completo": {PERM_INSERIMENTO, PERM_DISPLAY},
    # In futuro, per esempio:
    # "display": {PERM_DISPLAY},          con scope {"displays": [id, ...]} per accessi parziali
    # "inserimento": {PERM_INSERIMENTO},  con funzioni limitate
}
ROLE_LABELS = {"completo": "Completo (inserimento e display)"}


def new_device_id() -> str:
    return secrets.token_hex(16)


def valid_device_id(value: str) -> bool:
    return len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "N/D"


def client_ip(request: Request) -> str:
    """Indirizzo del dispositivo: quello della connessione (mai intestazioni come X-Forwarded-For)."""
    return request.client.host if request.client else ""


def is_local(request: Request) -> bool:
    """Solo il computer server stesso, attraverso l'indirizzo di loopback.

    Il traffico verso 127.0.0.1 non esce dal computer e nessun altro dispositivo può usare
    quell'indirizzo come mittente."""
    return client_ip(request) in LOOPBACK


# --- Password globale ---

def _get(db, key: str) -> str | None:
    s = db.get(Setting, key)
    return s.value if s else None


def _set(db, key: str, value: str):
    s = db.get(Setting, key)
    if s:
        s.value = value
    else:
        db.add(Setting(key=key, value=value))


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def password_is_set(db) -> bool:
    return _get(db, "access_password_hash") is not None


def set_password(db, password: str):
    """Nuova password: tutte le sessioni esistenti vengono chiuse."""
    gia_impostata = password_is_set(db)
    salt = secrets.token_hex(16)
    _set(db, "access_password_salt", salt)
    _set(db, "access_password_hash", _hash(password, salt))
    scollegati = db.query(AccessSession).delete()
    db.commit()
    _sessions.clear()
    if not gia_impostata:
        events.add("Password di accesso impostata")
    else:
        events.add("Password cambiata" + (f": {scollegati} dispositivi scollegati" if scollegati else ""))


def check_password(db, password: str) -> bool:
    salt = _get(db, "access_password_salt")
    stored = _get(db, "access_password_hash")
    if not salt or not stored:
        return False
    return hmac.compare_digest(_hash(password, salt), stored)


# --- Sessioni dei dispositivi ---

@dataclass
class SessionInfo:
    id: int
    role: str
    scope: dict | None
    last_seen: datetime


_sessions: dict[str, SessionInfo] = {}   # impronta del token -> sessione (evita il database a ogni richiesta)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, request: Request, role: str = "completo", scope: dict | None = None) -> str:
    """Nuova sessione per il dispositivo che ha fatto l'accesso. Ritorna il token per il cookie."""
    token = secrets.token_urlsafe(32)
    s = AccessSession(
        token_hash=_token_hash(token), role=role, scope=json.dumps(scope) if scope else None,
        ip=client_ip(request), user_agent=request.headers.get("user-agent", "")[:300],
        device_id=getattr(request.state, "device_id", None),
    )
    db.add(s)
    db.commit()
    return token


def get_session(request: Request) -> SessionInfo | None:
    """Sessione valida del dispositivo, o None (cookie assente, revocato o scaduto)."""
    token = request.cookies.get(COOKIE_NAME, "")
    if not token or len(token) > 100:
        return None
    h = _token_hash(token)
    now = datetime.utcnow()
    info = _sessions.get(h)
    if info is None or (now - info.last_seen).total_seconds() > LAST_SEEN_EVERY:
        db = SessionLocal()
        try:
            s = db.query(AccessSession).filter(AccessSession.token_hash == h).first()
            if s is None or now - s.last_seen > SESSION_MAX_IDLE:
                _sessions.pop(h, None)
                return None
            s.last_seen = now
            s.ip = client_ip(request)
            db.commit()
            info = SessionInfo(s.id, s.role, json.loads(s.scope) if s.scope else None, now)
            _sessions[h] = info
        finally:
            db.close()
    return info


def revoke_session(db, session_id: int):
    s = db.get(AccessSession, session_id)
    if s is not None:
        _sessions.pop(s.token_hash, None)
        db.delete(s)
        db.commit()


def revoke_all(db):
    db.query(AccessSession).delete()
    db.commit()
    _sessions.clear()


def logout(request: Request):
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        return
    db = SessionLocal()
    try:
        s = db.query(AccessSession).filter(AccessSession.token_hash == _token_hash(token)).first()
        if s is not None:
            revoke_session(db, s.id)
    finally:
        db.close()


def permission_for_path(path: str) -> str | None:
    """Permesso necessario per un percorso aperto agli altri dispositivi; None se il percorso
    non è aperto a nessuno di loro (Admin, Regia...)."""
    if path == "/inserimento" or path.startswith("/inserimento/"):
        return PERM_INSERIMENTO
    if path == "/display" or path.startswith("/display/"):
        return PERM_DISPLAY
    return None


def session_allows(session: SessionInfo, permission: str, path: str = "") -> bool:
    """Il punto unico in cui si decide cosa può fare un dispositivo. `path` (e `session.scope`)
    serviranno agli accessi parziali, es. solo alcuni display."""
    return permission in ROLES.get(session.role, set())


def home_for(session: SessionInfo) -> str:
    """Pagina iniziale di un dispositivo secondo il suo ruolo."""
    perms = ROLES.get(session.role, set())
    return "/inserimento/" if PERM_INSERIMENTO in perms else "/display/"


# --- Limite ai tentativi di accesso ---

class LoginLimiter:
    """Dopo MAX_FAILURES errori in WINDOW secondi un indirizzo è bloccato per LOCK secondi,
    raddoppiati a ogni nuovo blocco (fino a MAX_LOCK). Oltre GLOBAL_MAX errori al minuto da
    tutti gli indirizzi insieme (chi prova a cambiare indirizzo) si blocca ogni accesso per
    GLOBAL_LOCK secondi. Durante un blocco anche la password giusta viene rifiutata, altrimenti
    i tentativi continuerebbero. L'Admin può togliere i blocchi."""
    MAX_FAILURES = 5
    WINDOW = 600
    LOCK = 60
    MAX_LOCK = 900
    GLOBAL_MAX = 20
    GLOBAL_LOCK = 60

    def __init__(self):
        self.reset()

    def reset(self):
        self.failures: dict[str, deque] = {}
        self.locked_until: dict[str, float] = {}
        self.lock_count: dict[str, int] = {}
        self.global_failures: deque = deque()
        self.global_locked_until = 0.0

    def wait_seconds(self, ip: str) -> int:
        """Secondi di blocco rimasti per questo indirizzo (0 = può provare)."""
        now = time.monotonic()
        remaining = max(self.locked_until.get(ip, 0) - now, self.global_locked_until - now, 0)
        return int(remaining + 0.999)

    def failure(self, ip: str):
        now = time.monotonic()
        q = self.failures.setdefault(ip, deque())
        q.append(now)
        while q and q[0] < now - self.WINDOW:
            q.popleft()
        if len(q) >= self.MAX_FAILURES:
            n = self.lock_count.get(ip, 0)
            lock = min(self.LOCK * (2 ** n), self.MAX_LOCK)
            self.locked_until[ip] = now + lock
            self.lock_count[ip] = n + 1
            q.clear()
            events.add(f"{ip}: troppi tentativi errati, bloccato per {lock} s")
        g = self.global_failures
        g.append(now)
        while g and g[0] < now - 60:
            g.popleft()
        if len(g) >= self.GLOBAL_MAX and self.global_locked_until < now:
            self.global_locked_until = now + self.GLOBAL_LOCK
            g.clear()
            events.add(f"Troppi tentativi errati da più indirizzi: accessi sospesi per {self.GLOBAL_LOCK} s")

    def success(self, ip: str):
        self.failures.pop(ip, None)
        self.lock_count.pop(ip, None)

    def active_locks(self) -> list[tuple[str, int]]:
        out = [(ip, self.wait_seconds(ip)) for ip in self.locked_until]
        out = [(ip, s) for ip, s in out if s > 0]
        if self.global_locked_until > time.monotonic():
            out.append(("tutti gli indirizzi", self.wait_seconds("")))
        return out


limiter = LoginLimiter()


# --- Registro degli eventi di sicurezza (in memoria, ultimi 100; anche nel file di log) ---

class SecurityEvents:
    def __init__(self):
        self.items: deque = deque(maxlen=100)

    def add(self, text: str):
        import logging
        logging.getLogger("sicurezza").warning(text)
        self.items.appendleft((datetime.now(), text))

    def recent(self, n: int = 20) -> list:
        return list(self.items)[:n]


events = SecurityEvents()
