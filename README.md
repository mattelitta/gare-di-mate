# Gare di Mate

Software di gestione per gare a squadre di matematica. Permette di amministrare gare, inserire soluzioni in tempo reale e mostrare classifiche e statistiche su display distribuiti in rete locale.

## Funzionalità

- **Admin** — creazione e gestione gare, squadre, problemi, penalizzazioni, controllo stato (avvia/pausa/termina)
- **Inserimento** — registrazione jolly e soluzioni durante e dopo la gara, storico consegne modificabile
- **Regia** — controllo dei display in sala, rivelazione progressiva della classifica finale
- **Display** — viste in tempo reale: classifica, stato gara, valori problemi, classifica finale

## Meccaniche di punteggio

- Ogni squadra parte con `10 × numero_problemi` punti
- Il valore di ogni problema cresce dinamicamente: `+1/minuto` (finché meno di `n` squadre lo hanno risolto) e `+2` per ogni risposta errata (fino a `k` errori per squadra), fino al minuto soglia
- Risposta corretta: `+valore_corrente`; risposta errata: `-10` (sempre)
- **Jolly**: raddoppia tutti i contributi (positivi e negativi) su un problema scelto nella prima mezz'ora
- **Bonus prima consegna**: punti extra alle prime squadre a risolvere ogni problema
- **Bonus full**: punti extra alle prime squadre a completare tutti i problemi
- Il punteggio è sempre calcolato in tempo reale

## Requisiti

- Python 3.13+
- Dipendenze: `fastapi`, `uvicorn`, `sqlalchemy`, `jinja2`, `python-multipart`, `itsdangerous`

## Installazione

```bash
git clone https://github.com/mattelitta/gare-di-mate.git
cd gare-di-mate
py -m pip install -r requirements.txt
```

## Avvio

```bash
py -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Il server sarà accessibile su:

| Client | URL | Accesso |
|---|---|---|
| Admin | `http://localhost:8000/admin/` | Solo dal dispositivo host |
| Inserimento | `http://<ip-host>:8000/inserimento/` | Tutta la LAN |
| Regia | `http://<ip-host>:8000/regia/` | Tutta la LAN |
| Display | `http://<ip-host>:8000/display/` | Tutta la LAN |

## Struttura del progetto

```
gare-di-mate/
├── main.py              # Applicazione FastAPI, WebSocket
├── database.py          # Setup SQLite / SQLAlchemy
├── models.py            # Modelli dati
├── engine.py            # Motore di calcolo punteggi
├── routers/
│   ├── admin.py
│   ├── inserimento.py
│   ├── regia.py
│   └── display.py
├── templates/
│   ├── base.html
│   ├── admin/
│   ├── inserimento/
│   ├── regia/
│   └── display/
├── static/
└── requirements.txt
```

## Parametri di una gara

| Parametro | Descrizione |
|---|---|
| `valore_iniziale` | Valore di partenza di ogni problema |
| `n` | Numero di squadre che devono risolvere un problema per bloccare il bonus al minuto |
| `k` | Numero massimo di errori per squadra che contribuiscono al valore del problema |
| `bonus_prima_consegna` | Lista di bonus per le prime squadre a risolvere ogni problema |
| `bonus_full` | Lista di bonus per le prime squadre a completare tutti i problemi |
| `durata_minuti` | Durata della gara |
| `tempo_jolly` | Minuti disponibili per scegliere il jolly (default 30) |
| `minuto_soglia` | Minuto dopo il quale i valori dei problemi si bloccano |
| `minuto_oscuramento` | Minuto dopo il quale la classifica viene nascosta al pubblico |
| `squadre_qualificate` | Numero di squadre che si qualificano (linea rossa in classifica) |
| `posizioni_finale` | Numero di posizioni rivelate una alla volta nella classifica finale |
