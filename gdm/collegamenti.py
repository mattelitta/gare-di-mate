"""Dispositivi collegati a ciascun display della regia.

Ogni schermo che mostra un display lo interroga ogni 1,5 secondi; qui si ricorda, per ogni display,
quando ogni indirizzo si è fatto vivo l'ultima volta. Così la regia vede tutti i dispositivi impostati
sullo stesso display (non solo l'ultimo) e si aggiorna quando uno si collega o se ne va (firma.py).
In memoria: dopo un riavvio i display si rifanno vivi entro un paio di secondi.
"""
from datetime import datetime, timedelta

COLLEGATO_ENTRO = timedelta(seconds=15)   # oltre, il dispositivo non è più considerato collegato
DIMENTICA_DOPO = timedelta(minutes=10)

_visti: dict[int, dict[str, datetime]] = {}


def segna(display_id: int, ip: str):
    """Il dispositivo `ip` sta mostrando il display."""
    if ip:
        _visti.setdefault(display_id, {})[ip] = datetime.utcnow()


def collegati(display_id: int) -> list[str]:
    """Indirizzi dei dispositivi che mostrano il display adesso (ordinati)."""
    adesso = datetime.utcnow()
    visti = _visti.get(display_id, {})
    for ip, quando in list(visti.items()):
        if adesso - quando > DIMENTICA_DOPO:
            del visti[ip]
    return sorted(ip for ip, quando in visti.items() if adesso - quando <= COLLEGATO_ENTRO)


def dimentica(display_id: int):
    """Display eliminato."""
    _visti.pop(display_id, None)
