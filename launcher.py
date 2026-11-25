"""Finestra di avvio di Gare di Mate: avvia il server e mostra come collegarsi."""
import logging
import os
import socket
import sys
import threading
import tkinter as tk
import urllib.request
import webbrowser
from tkinter import messagebox

from paths import BASE_DIR, DATA_DIR

PORT = 8000
LOCAL_URL = f"http://localhost:{PORT}"
LOG_PATH = DATA_DIR / "gare-di-mate.log"

_log_stream = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
# Nell'eseguibile senza console stdout/stderr sono None: li mandiamo al file di log.
if sys.stdout is None:
    sys.stdout = _log_stream
if sys.stderr is None:
    sys.stderr = _log_stream
logging.basicConfig(stream=_log_stream, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

FONT = "Segoe UI"
GREEN, ORANGE, RED = "#15803d", "#c2410c", "#b91c1c"


def app_version() -> str:
    try:
        return (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def port_is_free() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", PORT))
            return True
        except OSError:
            return False


def our_server_responds() -> bool:
    try:
        with urllib.request.urlopen(f"{LOCAL_URL}/accesso", timeout=2) as r:
            return "Gare di Mate" in r.read().decode("utf-8", "ignore")
    except Exception:
        return False


class Launcher:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.server = None
        self.thread = None
        self.browser_opened = False
        self.closing = False
        self.fatal_error = None

        root.title("Gare di Mate")
        root.resizable(False, False)
        icon = BASE_DIR / "icon.ico"
        if icon.exists():
            root.iconbitmap(default=str(icon))
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        pad = {"padx": 24}
        tk.Label(root, text="Gare di Mate", font=(FONT, 22, "bold")).pack(pady=(20, 4), **pad)

        self.status = tk.Label(root, text="● Avvio in corso…", font=(FONT, 14, "bold"), fg=ORANGE)
        self.status.pack(pady=(0, 16), **pad)

        tk.Label(root, font=(FONT, 12), justify="center",
                 text="Per collegare gli altri dispositivi (tablet, computer dei display),\n"
                      "aprire nel loro browser questo indirizzo:").pack(**pad)
        row = tk.Frame(root)
        row.pack(pady=(6, 18), **pad)
        self.url_var = tk.StringVar(value="…")
        tk.Label(row, textvariable=self.url_var, font=("Consolas", 18, "bold")).pack(side="left")
        tk.Button(row, text="Copia", font=(FONT, 11), command=self.copy_url).pack(side="left", padx=(8, 0))

        btn = {"font": (FONT, 13), "width": 28, "pady": 6}
        self.admin_btn = tk.Button(root, text="Apri pannello Admin", state="disabled",
                                   command=self.open_admin, **btn)
        self.admin_btn.pack(pady=4, **pad)
        tk.Button(root, text="Apri cartella dei dati (backup)", command=self.open_data, **btn).pack(pady=4, **pad)

        tk.Label(root, font=(FONT, 11), fg="#555555", justify="center",
                 text="Tenere aperta questa finestra per tutta la gara:\n"
                      "chiudendola il server si ferma.").pack(pady=(16, 8), **pad)
        tk.Button(root, text="Chiudi Gare di Mate", command=self.on_close, **btn).pack(pady=(0, 8), **pad)
        version = app_version()
        tk.Label(root, text=f"Versione {version}" if version else "", font=(FONT, 9),
                 fg="#888888").pack(pady=(0, 10))

        self.refresh_ip()
        root.after(100, self.start_server)

    def set_status(self, text: str, color: str):
        self.status.config(text=f"● {text}", fg=color)

    def refresh_ip(self):
        from auth import get_local_ip
        ip = get_local_ip()
        self.url_var.set(f"http://{ip}:{PORT}" if ip != "N/D" else "rete non disponibile")
        self.root.after(10_000, self.refresh_ip)

    def copy_url(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.url_var.get())

    def open_admin(self):
        webbrowser.open(f"{LOCAL_URL}/admin/")

    def open_data(self):
        os.startfile(DATA_DIR)

    def start_server(self):
        self.thread = threading.Thread(target=self.run_server, daemon=True)
        self.thread.start()
        self.root.after(300, self.check_ready)

    def run_server(self):
        try:
            from database import init_db
            from migrations import MigrationError, SchemaTooNewError
            try:
                init_db()
            except (MigrationError, SchemaTooNewError) as e:
                logging.exception("Database non utilizzabile")
                self.fatal_error = str(e)
                return
            import uvicorn
            from main import app
            config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_config=None)
            self.server = uvicorn.Server(config)
            self.server.run()
        except Exception:
            logging.exception("Errore del server")

    def check_ready(self):
        if self.closing:
            return
        if self.thread and not self.thread.is_alive():
            self.set_status("Il server non è attivo", RED)
            messagebox.showerror("Gare di Mate", self.fatal_error or
                                 "Il server si è fermato per un errore.\n\n"
                                 f"Dettagli nel file:\n{LOG_PATH}")
            return
        if self.server is not None and self.server.started:
            self.set_status("Il server è attivo", GREEN)
            self.admin_btn.config(state="normal")
            if not self.browser_opened:
                self.browser_opened = True
                self.open_admin()
            self.root.after(2000, self.check_ready)
            return
        self.root.after(300, self.check_ready)

    def on_close(self):
        if self.server is not None and self.server.started:
            if not messagebox.askyesno("Chiudere Gare di Mate?",
                                       "Chiudendo, il server si ferma e i dispositivi collegati "
                                       "non riceveranno più aggiornamenti.\n\nChiudere?"):
                return
            self.closing = True
            self.set_status("Chiusura in corso…", ORANGE)
            self.root.update()
            self.server.should_exit = True
            self.thread.join(timeout=10)
        self.root.destroy()


def migrate_only() -> int:
    """Modalità --migra, usata dall'installer: aggiorna il database e termina.
    Codici di uscita: 0 = ok, 1 = errore, 2 = database di una versione più recente."""
    from database import init_db
    from migrations import SchemaTooNewError
    try:
        logging.info("--migra: database %s", init_db())
        return 0
    except SchemaTooNewError:
        logging.exception("--migra: database di una versione più recente")
        return 2
    except Exception:
        logging.exception("--migra: errore")
        return 1


def main():
    if "--migra" in sys.argv[1:]:
        sys.exit(migrate_only())
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    if not port_is_free():
        root.withdraw()
        if our_server_responds():
            messagebox.showinfo("Gare di Mate", "Gare di Mate è già aperto.\nApro il pannello Admin nel browser.")
            webbrowser.open(f"{LOCAL_URL}/admin/")
        else:
            messagebox.showerror("Gare di Mate",
                                 f"La porta {PORT} è usata da un altro programma, "
                                 "quindi Gare di Mate non può partire.\n\n"
                                 "Provare a riavviare il computer e poi riaprire Gare di Mate.")
        root.destroy()
        return
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
