"""
In-memory cache for computed game state.

Design:
- Stores (prob_states, team_scores) per competition_id
- TTL di 2 secondi come fallback di sicurezza
- Invalidazione immediata ad ogni scrittura (consegna, jolly, penalizzazione, cambio stato)
- Thread-safe: FastAPI usa un singolo event loop asyncio, nessun lock necessario
- Il DB rimane sempre la sorgente di verità: la cache è solo un'ottimizzazione
"""

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _CacheEntry:
    data: Any
    computed_at: float


class StateCache:
    TTL = 2.0  # secondi: fallback se l'invalidazione esplicita manca

    def __init__(self):
        self._store: dict[int, _CacheEntry] = {}

    def get(self, comp_id: int) -> Any | None:
        entry = self._store.get(comp_id)
        if entry is None:
            return None
        if time.monotonic() - entry.computed_at > self.TTL:
            del self._store[comp_id]
            return None
        return entry.data

    def set(self, comp_id: int, data: Any) -> None:
        self._store[comp_id] = _CacheEntry(data=data, computed_at=time.monotonic())

    def invalidate(self, comp_id: int) -> None:
        self._store.pop(comp_id, None)

    def invalidate_all(self) -> None:
        self._store.clear()


# Singleton globale
state_cache = StateCache()
