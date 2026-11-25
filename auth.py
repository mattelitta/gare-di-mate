import hashlib
import hmac
import secrets
import socket

from fastapi import Request

from database import SessionLocal
from models import Setting

COOKIE_NAME = "accesso"
COOKIE_MAX_AGE = 30 * 24 * 3600
LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost")

_UNSET = object()
_expected_token = _UNSET


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "N/D"


def is_local(request: Request) -> bool:
    """Localhost, oppure il server stesso raggiunto tramite il suo IP di rete."""
    host = request.client.host if request.client else ""
    return host in LOCAL_HOSTS or host == get_local_ip()


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
    global _expected_token
    salt = secrets.token_hex(16)
    _set(db, "access_password_salt", salt)
    _set(db, "access_password_hash", _hash(password, salt))
    db.commit()
    _expected_token = _UNSET


def check_password(db, password: str) -> bool:
    salt = _get(db, "access_password_salt")
    stored = _get(db, "access_password_hash")
    if not salt or not stored:
        return False
    return hmac.compare_digest(_hash(password, salt), stored)


def expected_token() -> str | None:
    """Token del cookie: HMAC dell'hash password con un segreto del server.
    Cambia (e invalida tutti i cookie) quando cambia la password."""
    global _expected_token
    if _expected_token is _UNSET:
        db = SessionLocal()
        try:
            stored = _get(db, "access_password_hash")
            if stored is None:
                _expected_token = None
            else:
                secret = _get(db, "cookie_secret")
                if not secret:
                    secret = secrets.token_hex(32)
                    _set(db, "cookie_secret", secret)
                    db.commit()
                _expected_token = hmac.new(secret.encode(), stored.encode(), hashlib.sha256).hexdigest()
        finally:
            db.close()
    return _expected_token


def has_valid_cookie(request: Request) -> bool:
    expected = expected_token()
    got = request.cookies.get(COOKIE_NAME, "")
    return expected is not None and hmac.compare_digest(got, expected)
