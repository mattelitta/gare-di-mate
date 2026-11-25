"""Esegue i test su una copia temporanea del progetto (il gare.db vero non viene toccato).

    py tests/run.py              suite rapida (uso quotidiano, meno di un minuto)
    py tests/run.py --completa   suite completa (prima di una release: crash, --migra, gara di 2 minuti)
    py tests/run.py -v           mostra il dettaglio di ogni controllo
    py tests/run.py -k crash     solo i gruppi il cui nome o file contiene "crash" (anche tra i lenti)

Per simulare un dispositivo in rete serve un secondo indirizzo IPv4 del computer (es. una VPN
come ZeroTier); se manca, quei controlli vengono saltati. Si può indicarlo con GDM_REMOTE_IP.
"""
import argparse
import os
import py_compile
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (nome, script relativo alla radice, avviare il server?, incluso nella suite rapida?)
TESTS = [
    ("Punteggi interi", "tests/test_interi.py", False, True),
    ("Calcolo dei punteggi", "test_data.py", False, True),
    ("Migrazioni del database", "tests/test_migrazioni.py", False, True),
    ("Accesso dei dispositivi", "tests/test_accesso.py", True, True),
    ("Storico consegne", "tests/test_consegne.py", True, True),
    ("Consegne aggiunte dall'Admin", "tests/test_consegna_admin.py", True, True),
    ("Inserimenti non validi", "tests/test_input.py", True, True),
    ("Stato gara e jolly", "tests/test_jolly.py", True, True),
    ("Visibilità dei jolly", "tests/test_jolly_visibili.py", True, True),
    ("Fine gara: classifica e blocco", "tests/test_finale.py", True, True),
    ("Esportazione PDF", "tests/test_pdf.py", True, True),
    ("Oscuramento e scadenze", "tests/test_oscuramento.py", True, True),
    ("Pagine admin e inserimento", "tests/test_admin.py", True, True),
    ("Parametri di gara", "tests/test_parametri.py", True, True),
    ("Avanzamenti del tempo", "tests/test_avanzamenti.py", False, True),
    ("Crash e avanzamento manuale", "tests/test_crash.py", False, False),
    ("Crash con due gare", "tests/test_crash_due.py", False, False),
    ("Modalità --migra (installer)", "tests/test_migra.py", False, False),
    ("Gara completa di 2 minuti", "test_live.py", True, False),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


def primary_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def secondary_ip() -> str:
    """Un IPv4 del computer diverso da quello principale: il server lo vede come dispositivo remoto."""
    if os.environ.get("GDM_REMOTE_IP"):
        return os.environ["GDM_REMOTE_IP"]
    primary = primary_ip()
    try:
        addresses = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        return ""
    for ip in sorted(addresses):
        if ip != primary and not ip.startswith(("127.", "169.254.")):
            return ip
    return ""


def prepare_copy() -> Path:
    dest = Path(tempfile.mkdtemp(prefix="gdm-test-")) / "app"
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "venv", ".venv", "build", "dist", "__pycache__", "*.db", "*.log"))
    return dest


def compile_all(app: Path) -> list[str]:
    errors = []
    for f in [*app.glob("*.py"), *app.glob("routers/*.py"), *app.glob("tests/*.py")]:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(str(e))
    return errors


def fresh_database(app: Path):
    for f in app.glob("gare*.db"):
        f.unlink()
    subprocess.run([sys.executable, "setup_test.py"], cwd=app, capture_output=True, check=True)


def start_server(app: Path, port: int):
    log = open(app / "server.log", "a", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)],
                         cwd=app, stdout=log, stderr=log)
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/accesso", timeout=1)
            return p
        except Exception:
            time.sleep(0.25)
    p.kill()
    raise RuntimeError("il server di prova non è partito (vedi server.log)")


def summary_line(output: str) -> str:
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.endswith("superati") or "SUPERATI" in line or "calcoli" in line:
            return line.replace("\x1b[92m", "").replace("\x1b[1m", "").replace("\x1b[0m", "").strip()
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--completa", action="store_true", help="esegue anche i test lenti")
    parser.add_argument("-v", "--verbose", action="store_true", help="mostra ogni controllo")
    parser.add_argument("-k", metavar="TESTO", help="solo i gruppi il cui nome o file contiene TESTO")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.k:
        selected = [t for t in TESTS if args.k.lower() in (t[0] + t[1]).lower()]
    else:
        selected = [t for t in TESTS if args.completa or t[3]]
    app = prepare_copy()
    port = free_port()
    remote_ip = secondary_ip()
    env = {**os.environ, "GDM_APP": str(app), "GDM_PORT": str(port), "GDM_REMOTE_IP": remote_ip,
           "GDM_BASE": f"http://127.0.0.1:{port}", "PYTHONIOENCODING": "utf-8"}
    nome = f"filtrata '{args.k}'" if args.k else ("completa" if args.completa else "rapida")
    print(f"Suite {nome}: {len(selected)} gruppi di test")
    print(f"Copia di prova: {app}  (porta {port}"
          + (f", dispositivo remoto simulato da {remote_ip})" if remote_ip else ", nessun IP secondario: controlli remoti saltati)"))
    print()

    started = time.time()
    failures = 0
    errors = compile_all(app)
    print(f"{'OK  ' if not errors else 'FAIL'} Compilazione di tutti i file Python")
    for e in errors:
        print("     " + e)
    failures += bool(errors)

    for name, script, needs_server, _ in selected:
        t0 = time.time()
        fresh_database(app)
        server = start_server(app, port) if needs_server else None
        try:
            res = subprocess.run([sys.executable, script], cwd=app, env=env,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
        finally:
            if server:
                server.kill()
                server.wait()
        output = res.stdout + res.stderr
        ok = res.returncode == 0
        failures += not ok
        skipped = [line for line in output.splitlines() if line.startswith("SALTATO")]
        detail = summary_line(output) or f"codice di uscita {res.returncode}"
        print(f"{'OK  ' if ok else 'FAIL'} {name:<32} {detail}  ({time.time() - t0:.1f} s)")
        for line in skipped:
            print(f"     {line}")
        if args.verbose or not ok:
            for line in output.splitlines():
                if (args.verbose or line.startswith("FAIL") or "[!!]" in line
                        or "Traceback" in line or "Error" in line):
                    print(f"     {line}")

    print(f"\n{'Tutti i test superati' if not failures else f'{failures} gruppi con errori'}"
          f" in {time.time() - started:.0f} s")
    shutil.rmtree(app.parent, ignore_errors=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
