# Gare di Mate

Software di gestione per gare a squadre di matematica. Permette di amministrare gare, inserire soluzioni in tempo reale e mostrare classifiche e statistiche su display distribuiti in rete locale.

## Funzionalità

- **Admin** — creazione e gestione gare; squadre e problemi (nella pagina "Modifica parametri", per non toccarli per sbaglio durante la gara); bonus o penalizzazioni in punti; controllo stato (avvia / pausa / riprendi / termina); accessibile solo dal dispositivo host
- **Inserimento** — registrazione jolly e soluzioni durante e dopo la gara (la pagina si può aprire già prima della partenza: l'invio si attiva da solo quando la gara inizia); storico consegne modificabile e filtrabile per squadra, problema e dispositivo che le ha inserite; ottimizzato per uso rapido da tablet (il cursore passa da solo al campo successivo: es. `04` `03` Invio)
- **Regia** — controllo dei display in sala (scelta della vista, scala del testo), rivelazione progressiva della classifica finale
- **Display** — viste in tempo reale aggiornate via polling: classifica, elenco squadre, valori problemi, stato gara, classifica finale

## Requisiti

Solo per l'installazione da sorgente (l'installer Windows include già tutto):

- Python 3.11+ (con Python 3.14 serve SQLAlchemy 2.1, già indicato in `requirements.txt`)
- Dipendenze in `requirements.txt`: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `jinja2`, `python-multipart`, `itsdangerous`

## Installazione su Windows (consigliata)

1. Scaricare ed eseguire `GareDiMate-Setup-<versione>.exe` e seguire la procedura guidata.
   Python non serve: è già incluso.
2. Aprire **Gare di Mate** dall'icona sul desktop. Si apre una finestra che avvia il server,
   mostra l'indirizzo per gli altri dispositivi e apre il pannello Admin nel browser.
3. Tenere aperta la finestra per tutta la gara: chiudendola il server si ferma.

L'installer configura da solo il firewall di Windows (solo per Gare di Mate, porta 8000,
dispositivi della rete locale). I dati sono salvati in `Documenti\Gare di Mate` e restano
anche disinstallando il programma.

Al primo avvio Windows può mostrare "Windows ha protetto il PC" (l'eseguibile non è firmato
digitalmente): cliccare **Ulteriori informazioni** → **Esegui comunque**.

L'app funziona completamente offline: non serve una connessione a internet.

**Aggiornare**: scaricare il nuovo installer dalla pagina
[Releases](https://github.com/mattelitta/gare-di-mate/releases) ed eseguirlo. Riconosce la versione
già installata e la aggiorna; se Gare di Mate è aperto propone di chiuderlo. Le gare salvate restano.
La versione installata è scritta in basso nella finestra di Gare di Mate.
Se la nuova versione cambia la struttura del database, le gare salvate vengono adattate in automatico
già durante l'installazione; prima viene salvata una copia di sicurezza (`gare-backup-….db`) nella
stessa cartella `Documenti\Gare di Mate`.

**Disinstallare**: menu Start → cartella *Gare di Mate* → *Disinstalla Gare di Mate*
(oppure Impostazioni → App). Le gare salvate in `Documenti\Gare di Mate` non vengono eliminate.

### Creare l'installer

Serve un PC Windows con Python, PyInstaller (`py -m pip install pyinstaller`)
e Inno Setup 6 (`winget install JRSoftware.InnoSetup`). Poi:

1. aggiornare il numero di versione nel file `VERSION` (es. `1.1.0`);
2. eseguire `build_installer.bat`;
3. pubblicare `dist\GareDiMate-Setup-<versione>.exe` come nuova release su GitHub.

## Installazione da sorgente (sviluppo, Linux, macOS)

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
| Inserimento | `http://<ip-host>:8000/inserimento/` | Host + LAN con password di accesso |
| Regia | `http://localhost:8000/regia/` | Solo dal dispositivo host |
| Display | `http://<ip-host>:8000/display/` | Host + LAN con password di accesso |

### Accesso dagli altri dispositivi

La home Admin mostra l'indirizzo a cui collegarsi e permette di impostare la **password di accesso**.
Ogni dispositivo diverso dall'host deve inserirla una volta (resta valida 30 giorni nel browser)
e può poi usare solo **Inserimento** e **Display** (Admin e Regia restano sul dispositivo host).
Finché la password non è impostata, gli altri dispositivi non possono accedere.
Cambiandola, tutti i dispositivi collegati dovranno rifare l'accesso.

## Flusso di una gara

1. L'**Admin** crea la gara con i parametri, poi aggiunge squadre e problemi in "Modifica parametri"
2. L'**Admin** avvia la gara — il timer parte
3. La **Regia** assegna le viste ai display e regola la scala del testo; gli **inseritori** possono
   già aprire la pagina di inserimento (anche prima della partenza)
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
| `tema_display` | Chiaro (default, adatto alla proiezione) o scuro |

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
Il **tema** (chiaro, predefinito e adatto alla proiezione, oppure scuro) si sceglie nei parametri della gara.

## Struttura del progetto

```
gare-di-mate/
├── main.py              # Applicazione FastAPI, controllo accesso, broadcast loop cache
├── launcher.py          # Finestra di avvio (eseguibile Windows)
├── paths.py             # Percorsi di template, file statici e database
├── auth.py              # Password di accesso per i dispositivi in rete
├── database.py          # Setup SQLite / SQLAlchemy, eager loading
├── migrations.py        # Aggiornamento automatico della struttura del database (con backup)
├── models.py            # Modelli dati (Competition, Team, Problem, ...)
├── engine.py            # Motore di calcolo punteggi (O(S), nessun punteggio salvato)
├── cache.py             # Cache in memoria con TTL e invalidazione esplicita
├── routers/
│   ├── admin.py         # Gare, squadre, problemi, bonus/penalizzazioni, controllo stato
│   ├── inserimento.py   # Jolly e soluzioni, storico consegne
│   ├── regia.py         # Gestione display, scala testo, rivelazione finale
│   └── display.py       # Viewer display, API JSON polling
├── templates/
│   ├── base.html
│   ├── admin/
│   ├── inserimento/
│   ├── regia/
│   └── display/
├── static/vendor/       # Tailwind e Alpine.js in locale (funzionamento offline)
├── packaging/           # Configurazione PyInstaller e Inno Setup, icona
├── VERSION              # Numero di versione usato dall'installer
├── build_installer.bat  # Crea l'installer Windows
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
