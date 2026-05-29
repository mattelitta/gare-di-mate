# Gare di Mate

Software di gestione per gare a squadre di matematica. Permette di amministrare gare, inserire soluzioni in tempo reale e mostrare classifiche e statistiche su display distribuiti in rete locale.

## Funzionalità

- **Admin** — creazione e gestione gare, squadre, problemi, penalizzazioni; controllo stato (avvia / pausa / riprendi / termina); accessibile solo dal dispositivo host
- **Inserimento** — registrazione jolly e soluzioni durante e dopo la gara, storico consegne modificabile; ottimizzato per uso rapido da tablet
- **Regia** — controllo dei display in sala (scelta della vista, scala del testo), rivelazione progressiva della classifica finale
- **Display** — viste in tempo reale aggiornate via polling: classifica, elenco squadre, valori problemi, stato gara, classifica finale

## Requisiti

- Python 3.11+
- Dipendenze: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `jinja2`, `python-multipart`

## Installazione

```bash
git clone https://github.com/mattelitta/gare-di-mate.git
cd gare-di-mate
pip install -r requirements.txt
```

## Avvio

**Windows** — doppio clic su `avvia.bat`, oppure da terminale:
```bat
avvia.bat
```

**Linux / macOS**:
```bash
./avvia.sh
```

**Manuale** (qualsiasi sistema):
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Gli script rilevano automaticamente un eventuale ambiente virtuale nella cartella `venv/`.

Il server sarà accessibile su:

| Client | URL | Accesso |
|---|---|---|
| Admin | `http://localhost:8000/admin/` | Solo dal dispositivo host |
| Inserimento | `http://<ip-host>:8000/inserimento/` | Tutta la LAN |
| Regia | `http://<ip-host>:8000/regia/` | Tutta la LAN |
| Display | `http://<ip-host>:8000/display/` | Tutta la LAN |

Inserimento, Regia e Display supportano una password opzionale per gara (configurabile dall'Admin).

## Flusso di una gara

1. L'**Admin** crea la gara con parametri, squadre e problemi
2. L'**Admin** avvia la gara — il timer parte
3. La **Regia** assegna le viste ai display e regola la scala del testo
4. L'**Inserimento** registra jolly (entro il tempo jolly) e soluzioni
5. I **Display** mostrano classifica, valori e stato in tempo reale
6. Al minuto di oscuramento la classifica viene nascosta al pubblico
7. Al minuto soglia i valori dei problemi si congelano
8. L'**Admin** termina la gara; l'**Inserimento** può continuare per consegne in ritardo
9. L'**Admin** blocca gli inserimenti — la classifica finale è calcolata
10. La **Regia** rivela le posizioni una alla volta dal basso verso l'alto

## Parametri di una gara

| Parametro | Descrizione |
|---|---|
| `valore_iniziale` | Valore di partenza di ogni problema |
| `n` | Squadre non-ospiti che devono risolvere per bloccare il `+1/min` |
| `k` | Max errori per squadra non-ospite che contribuiscono al valore |
| `bonus_prima_consegna` | Lista di bonus per le prime squadre a risolvere ogni problema |
| `bonus_full` | Lista di bonus per le prime squadre a completare tutti i problemi |
| `durata_minuti` | Durata della gara |
| `tempo_jolly` | Minuti disponibili per scegliere il jolly (default 30) |
| `minuto_soglia` | Dopo questo minuto i valori si congelano (`≤ durata`) |
| `minuto_oscuramento` | Dopo questo minuto la classifica è nascosta al pubblico (`≤ durata`) |
| `squadre_qualificate` | Squadre che si qualificano (linea separatrice in classifica) |
| `posizioni_finale` | Posizioni rivelate una alla volta nella classifica finale |
| `password` | Opzionale — protegge Inserimento, Regia e Display |

## Display — viste disponibili

| Vista | Contenuto |
|---|---|
| `test` | Nome e IP del display |
| `ranking` | Classifica con barre, linea qualificate, oscurabile |
| `team_list` | Elenco squadre per numero |
| `problem_values` | Valori correnti dei problemi con barre |
| `competition_status` | Griglia squadre × problemi con contributi e jolly |
| `final_ranking` | Rivelazione progressiva gestita dalla Regia |

La **scala del testo** di ogni display (1–5) è regolabile dalla Regia in tempo reale: scala 1 per 30+ squadre, scala 5 per 5–10 squadre.

## Struttura del progetto

```
gare-di-mate/
├── main.py              # Applicazione FastAPI, broadcast loop cache
├── database.py          # Setup SQLite / SQLAlchemy, eager loading, migrazioni
├── models.py            # Modelli dati (Competition, Team, Problem, ...)
├── engine.py            # Motore di calcolo punteggi (O(S), nessun punteggio salvato)
├── cache.py             # Cache in memoria con TTL e invalidazione esplicita
├── routers/
│   ├── admin.py         # CRUD gare/squadre/problemi/penalizzazioni, controllo stato
│   ├── inserimento.py   # Jolly e soluzioni, storico consegne
│   ├── regia.py         # Gestione display, scala testo, rivelazione finale
│   └── display.py       # Viewer display, API JSON polling
├── templates/
│   ├── base.html
│   ├── admin/
│   ├── inserimento/
│   ├── regia/
│   └── display/
├── static/
├── avvia.bat            # Script di avvio Windows
├── avvia.sh             # Script di avvio Linux/macOS
├── setup_test.py        # Crea una gara di prova pronta all'avvio
├── test_live.py         # Test automatizzato end-to-end (gara di 2 minuti)
└── requirements.txt
```

## Script di utilità

```bash
# Crea una gara di prova (3 squadre + 1 ospite, 4 problemi, 10 minuti)
python setup_test.py

# Esegui il test automatizzato end-to-end (richiede il server in esecuzione)
python test_live.py
```
