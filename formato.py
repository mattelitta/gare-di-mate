"""Formattazione di tempi e durate per i template (registrata come globali Jinja)."""
from datetime import datetime


def mmss(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def durata(seconds: float) -> str:
    """Es. "45 s", "6 min 20 s", "2 h 5 min"."""
    s = int(round(max(0, seconds)))
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min {s} s" if s else f"{m} min"
    return f"{s} s"


def ora_locale(utc: datetime) -> str:
    return (utc + (datetime.now() - datetime.utcnow())).strftime("%H:%M")


def registra(templates):
    templates.env.globals.update(mmss=mmss, durata=durata, ora_locale=ora_locale)
