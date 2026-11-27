# Gare di Mate

Software di gestione per gare a squadre di matematica. Permette di amministrare gare, inserire soluzioni in tempo reale e mostrare classifiche e statistiche su display distribuiti in rete locale.

## Funzionalità

- **Admin** — creazione e gestione gare; squadre e problemi (nella pagina "Modifica parametri", per non toccarli per sbaglio durante la gara); bonus o penalizzazioni in punti; controllo stato (avvia / pausa / riprendi / termina) e avanzamento manuale del tempo di gara; accessibile solo dal dispositivo host
- **PDF dei risultati** — a gara terminata e classifica calcolata, l'Admin scarica un PDF con la classifica finale e i valori dei problemi come grafici a barre e lo stato della gara
- **Consegne con il tempo** — dallo storico consegne l'Admin può aggiungere una consegna dimenticata indicandone il tempo di gara (non oltre quello attuale); i punteggi si ricalcolano come se fosse stata inserita in quel momento; nello storico dell'Admin (e solo lì) queste consegne sono segnate "aggiunta da Admin"
- **Modalità scura** per le pagine di lavoro (admin, inserimento, regia): tasto in alto a destra, vale solo per il browser su cui si attiva e non tocca i display
- **Ripresa dopo un crash** — se il programma si chiude con una gara in corso, alla riapertura la gara riprende dal minuto raggiunto e un avviso propone di far avanzare il tempo della durata dell'interruzione (modificabile o ignorabile)
- **Inserimento** — registrazione jolly e soluzioni durante e dopo la gara (la pagina si può aprire già prima della partenza: l'invio si attiva da solo quando la gara inizia); stato della gara e tempi alla fine e alla chiusura dei jolly sempre visibili; squadre senza jolly evidenziate in giallo negli ultimi 2 minuti e in rosso dopo la scadenza, con un tasto per assegnare loro il jolly sul problema 01; errori di inserimento segnalati nella pagina; storico consegne (più recenti in alto) modificabile e filtrabile per squadra, problema e dispositivo che le ha inserite, con gli avanzamenti del tempo al loro posto; ottimizzato per uso rapido da tablet (il cursore passa da solo al campo successivo: es. `04` `03` Invio)
- **Regia** — controllo dei display in sala (scelta della vista, scala del testo, schermi interni che ignorano l'oscuramento), rivelazione progressiva della classifica finale
- **Pagine sempre aggiornate** — le pagine di Admin e Regia e l'elenco delle gare dell'Inserimento si ricaricano da sole quando cambia lo stato della gara (avvio, pausa, oscuramento automatico, fine allo scadere del tempo, classifica finale calcolata, modifiche fatte da un'altra finestra); mai mentre si sta scrivendo in un campo o è aperta una finestra di conferma
- **Display** — viste in tempo reale aggiornate via polling: classifica, elenco squadre, valori problemi, stato gara, classifica finale

## Requisiti

Solo per l'installazione da sorgente (l'installer Windows include già tutto):

- Python 3.11+ (con Python 3.14 serve SQLAlchemy 2.1, già indicato in `requirements.txt`)
- Dipendenze in `requirements.txt`: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `jinja2`, `python-multipart`, `itsdangerous`, `fpdf2` (esportazione PDF), `cryptography` (certificato HTTPS)

## Installazione su Windows (consigliata)

1. Scaricare ed eseguire `GareDiMate-Setup-<versione>.exe` e seguire la procedura guidata.
   Python non serve: è già incluso.
2. Aprire **Gare di Mate** dall'icona sul desktop. Si apre una finestra che avvia il server,
   mostra l'indirizzo per gli altri dispositivi e apre il pannello Admin nel browser.
3. Tenere aperta la finestra per tutta la gara: chiudendola il server si ferma.

L'installer configura da solo il firewall di Windows (solo per Gare di Mate, porte 8000 e 8443,
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

1. eseguire la suite completa: `python tests/run.py --completa`;
2. aggiornare il numero di versione nel file `VERSION` (es. `1.1.0`);
3. eseguire `build_installer.bat`;
4. pubblicare `dist\GareDiMate-Setup-<versione>.exe` come nuova release su GitHub.

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
python server.py            # porte predefinite: 8000 (HTTP) e 8443 (HTTPS)
```

Gli script rilevano automaticamente un eventuale ambiente virtuale nella cartella `venv/`.

Il server sarà accessibile su:

| Client | URL | Accesso |
|---|---|---|
| Admin | `http://localhost:8000/admin/` | Solo dal computer server |
| Regia | `http://localhost:8000/regia/` | Solo dal computer server |
| Inserimento | `https://<ip-host>:8443/inserimento/` | Computer server + rete locale con password |
| Display | `https://<ip-host>:8443/display/` | Computer server + rete locale con password |

La porta 8000 serve il computer server (indirizzo `localhost`, il traffico non esce dal computer).
Un altro dispositivo che la usa viene solo rimandato all'indirizzo HTTPS.

### Accesso dagli altri dispositivi

La home Admin (e la finestra di avvio) mostra l'indirizzo a cui collegarsi e permette di impostare
la **password di accesso** (almeno 8 caratteri). Ogni dispositivo diverso dal computer server deve
inserirla una volta e può poi usare solo **Inserimento** e **Display** (Admin e Regia restano sul
computer server). Finché la password non è impostata, gli altri dispositivi non possono accedere.

- **Collegamento cifrato (HTTPS).** Al primo avvio Gare di Mate crea un certificato per gli
  indirizzi di questo computer (cartella `certificato` nei dati; la chiave privata non lascia mai il
  computer). Non essendo rilasciato da un ente pubblico, alla prima apertura il browser mostra un
  avviso di sicurezza: è normale, si accetta una volta per dispositivo (e di nuovo se cambia
  l'indirizzo del computer). Per controllare di essere collegati proprio al computer server,
  l'impronta SHA-256 del certificato, nei dettagli del certificato nel browser, deve coincidere con
  quella mostrata nella home Admin e nella finestra di avvio.
- **Un accesso per dispositivo.** Ogni accesso con la password crea una sessione propria (valida
  finché il dispositivo la usa, scade dopo 30 giorni di inattività). In *Dispositivi collegati*
  (home Admin) si vedono indirizzo, browser e ultima attività di ciascuno e si può scollegare un
  singolo dispositivo o tutti. Cambiando la password vengono scollegati tutti.
- **Tentativi limitati.** Dopo 5 password errate un indirizzo è bloccato per un minuto (poi per
  tempi crescenti); con molti errori da più indirizzi gli accessi sono sospesi per un minuto. Durante
  un blocco è rifiutata anche la password giusta. I blocchi e gli eventi recenti compaiono in
  *Dispositivi collegati*, con il tasto per togliere i blocchi.

### Sicurezza della rete

Gare di Mate protegge la gara anche da chi è collegato alla stessa rete e conosce il programma:

- il traffico tra il server e gli altri dispositivi è cifrato (HTTPS): non si possono leggere
  password, risposte corrette, consegne o classifiche intercettando i pacchetti;
- senza la password non si apre nulla, e un dispositivo scollegato dall'Admin non rientra;
- Admin e Regia rispondono solo al computer server;
- ciò che i display non mostrano non viene nemmeno inviato: con l'oscuramento nessun punteggio, e
  della classifica finale solo le posizioni già svelate;
- moduli inviati da altri siti, pagine incorporate in altri siti e nomi di server falsi sono rifiutati.

Limiti da conoscere:

- chi è sulla stessa rete può sempre **disturbarla** (per esempio disturbando il Wi-Fi o
  sovraccaricando il server): nessun programma lo impedisce. Il computer server continua comunque
  a funzionare, e da lì si possono inserire le consegne;
- l'avviso del certificato si accetta "sulla fiducia": chi controlla attivamente la rete potrebbe
  presentare un proprio certificato al suo posto. Il confronto dell'impronta (vedi sopra) svela il
  trucco; accettare l'avviso solo al primo collegamento, e insospettirsi se ricompare senza che sia
  cambiato l'indirizzo del computer.

Consigli per il giorno della gara: un router dedicato con una password Wi-Fi nota solo allo staff
(WPA2 o WPA3), il computer server collegato via cavo, e se il router lo permette l'isolamento dei
client Wi-Fi (i tablet raggiungono il server ma non si vedono tra loro). Una password di accesso
lunga, diversa da quella del Wi-Fi, comunicata solo a chi inserisce.

## Flusso di una gara

1. L'**Admin** crea la gara con i parametri, poi aggiunge squadre e problemi in "Modifica parametri"
2. L'**Admin** preme "Prepara l'avvio…", controlla il riepilogo (squadre, problemi, durata, ora attuale) e preme "Avvia ora" nel momento esatto — il timer parte
3. La **Regia** assegna le viste ai display e regola la scala del testo; gli **inseritori** possono
   già aprire la pagina di inserimento (anche prima della partenza)
4. L'**Inserimento** registra jolly (entro il tempo jolly) e soluzioni
5. I **Display** mostrano classifica, valori e stato in tempo reale
6. Al minuto di oscuramento la classifica (con elenco squadre e stato gara) viene nascosta al pubblico;
   (non sugli schermi segnati come interni dalla Regia);
   l'Admin può anche oscurarla o mostrarla a mano in qualsiasi momento, e vede il tempo mancante
   alle scadenze (chiusura jolly, congelamento valori, oscuramento, fine gara)
7. Al minuto soglia i valori dei problemi si congelano
8. Allo scadere del tempo la gara termina da sola (l'**Admin** può anche terminarla prima);
   l'**Inserimento** può continuare per consegne in ritardo, registrate alla fine della gara
9. L'**Admin** calcola la classifica finale (si può ricalcolare quante volte serve, per esempio dopo
   consegne in ritardo) e, quando serve, spunta "Inserimenti bloccati" (si può togliere)
10. La **Regia** rivela le posizioni una alla volta dal basso verso l'alto

## Parametri di una gara

| Parametro | Descrizione |
|---|---|
| `valore_iniziale` | Valore di partenza di ogni problema |
| `punteggio_iniziale` | Punteggio di partenza delle squadre (facoltativo: se vuoto, 10 × numero di problemi) |
| `n` | Squadre non-ospiti che devono risolvere per bloccare il `+1/min` |
| `k` | Max errori per squadra non-ospite che contribuiscono al valore |
| `bonus_prima_consegna` | Lista di bonus per le prime squadre a risolvere ogni problema |
| `bonus_full` | Lista di bonus per le prime squadre a completare tutti i problemi |
| `durata_minuti` | Durata della gara |
| `tempo_jolly` | Minuti disponibili per scegliere il jolly (default 30) |
| `jolly nei display` | Visibili appena inseriti (default) o tutti insieme alla chiusura dei jolly; nel secondo caso fino ad allora i display contano i punti senza raddoppio |
| `minuto_soglia` | Dopo questo minuto i valori si congelano (`≤ durata`) |
| `minuto_oscuramento` | Dopo questo minuto la classifica è nascosta al pubblico (`≤ durata`) |
| `gara a qualificazione` | Interruttore: se attivo si indica quante squadre si qualificano (linea separatrice in classifica); se spento nessuna linea |
| `posizioni_finale` | Posizioni rivelate una alla volta nella classifica finale |
| `tema_display` | Chiaro (default, adatto alla proiezione) o scuro |

## Display — viste disponibili

| Vista | Contenuto |
|---|---|
| `test` | Nome e IP del display |
| `ranking` | Classifica con barre, linea qualificate, oscurabile |
| `team_list` | Elenco squadre per numero |
| `problem_values` | Valori correnti dei problemi con barre |
| `competition_status` | Griglia squadre × problemi con contributi e jolly; squadre in ordine di classifica con numero, nome e punteggio sulla destra (linea rossa sotto l'ultima qualificata) |
| `matrix` | "Matrice": la stessa griglia con soli numeri di squadra e problema; casella verde se risolto, rossa con il numero di errori se solo sbagliato, bordo giallo spesso sul jolly (visibile come nello stato gara) |
| `final_ranking` | Rivelazione progressiva gestita dalla Regia |

La **scala del testo** di ogni display (1–7) è regolabile dalla Regia in tempo reale: scala 1 per 30+ squadre, scala 5 per 5–10 squadre, scale 6 e 7 per gare con pochissime squadre.
Il **tema** (chiaro, predefinito e adatto alla proiezione, oppure scuro) si sceglie nei parametri della gara.
Un display può essere segnato dalla Regia come **interno** (es. lo schermo nella sala dello staff):
ignora l'oscuramento e mostra sempre classifica, punteggi e jolly (anche quando i jolly sono nascosti
fino alla chiusura), con un avviso arancione nell'intestazione mentre l'oscuramento è attivo. Da non usare per schermi visibili al pubblico.

## Struttura del progetto

```
gare-di-mate/
├── main.py              # Applicazione FastAPI, controlli di sicurezza e di accesso, broadcast loop cache
├── server.py            # Avvio dei due server (HTTP per il computer server, HTTPS per la rete)
├── tls.py               # Certificato HTTPS autofirmato per gli indirizzi del computer
├── firma.py             # Firma dello stato di una pagina, per l'aggiornamento automatico
├── launcher.py          # Finestra di avvio (eseguibile Windows)
├── paths.py             # Percorsi di template, file statici e database
├── auth.py              # Password, sessioni per dispositivo e permessi, limite ai tentativi
├── database.py          # Setup SQLite / SQLAlchemy, eager loading
├── migrations.py        # Aggiornamento automatico della struttura del database (con backup)
├── tempo.py             # Tempo di gara: ripresa dopo un crash e avanzamento manuale
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
├── tests/               # Test automatici (run.py: suite rapida e completa)
├── setup_test.py        # Crea una gara di prova pronta all'avvio
├── test_data.py         # Verifica dei calcoli dei punteggi (usato dai test)
├── test_live.py         # Gara completa di 2 minuti (usato dalla suite completa)
└── requirements.txt
```

## Test

I test girano su una copia temporanea del progetto con una porta libera: il `gare.db` vero
non viene toccato e non serve avere il server acceso.

```bash
# Suite rapida (meno di un minuto): da usare durante lo sviluppo
python tests/run.py

# Suite completa (qualche minuto): prima di compilare una versione definitiva.
# Aggiunge i test di sicurezza in rete, crash veri con riavvio, la modalità --migra
# dell'installer e una gara di 2 minuti.
python tests/run.py --completa

# Dettaglio di ogni controllo
python tests/run.py -v

# Solo i gruppi il cui nome contiene un testo (anche tra quelli lenti), es. i crash
python tests/run.py -k crash
```

Per simulare un dispositivo in rete serve un secondo indirizzo IPv4 del computer (per esempio
una VPN come ZeroTier); se manca, quei controlli vengono segnalati come saltati.

## Script di utilità

```bash
# Crea una gara di prova (3 squadre + 1 ospite, 4 problemi, 10 minuti)
python setup_test.py
```
