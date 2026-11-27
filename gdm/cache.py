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

    # Varianti per gara: "full" (tutto) e "public" (senza jolly, per i display finché sono nascosti).
    def __init__(self):
        self._store: dict[tuple[int, str], _CacheEntry] = {}

    def get(self, comp_id: int, variant: str = "full") -> Any | None:
        entry = self._store.get((comp_id, variant))
        if entry is None:
            return None
        if time.monotonic() - entry.computed_at > self.TTL:
            del self._store[(comp_id, variant)]
            return None
        return entry.data

    def set(self, comp_id: int, data: Any, variant: str = "full") -> None:
        self._store[(comp_id, variant)] = _CacheEntry(data=data, computed_at=time.monotonic())

    def invalidate(self, comp_id: int) -> None:
        for key in [k for k in self._store if k[0] == comp_id]:
            del self._store[key]

    def invalidate_all(self) -> None:
        self._store.clear()


# Singleton globale
state_cache = StateCache()
