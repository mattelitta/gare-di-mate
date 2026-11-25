"""Modalità `launcher.py --migra` usata dall'installer: codici di uscita 0/1/2. Suite completa."""
import sqlite3
import subprocess
import sys

from _util import APP, DB, check, finish, make_legacy_db
from migrations import SCHEMA_VERSION


def migra():
    return subprocess.run([sys.executable, str(APP / "launcher.py"), "--migra"], cwd=APP).returncode


def version():
    c = sqlite3.connect(DB)
    v = c.execute("PRAGMA user_version").fetchone()[0]
    c.close()
    return v


def cleanup():
    for f in [DB, *APP.glob("gare-backup-*.db")]:
        f.unlink(missing_ok=True)


cleanup()
check("nessun database -> codice 0, database creato allo schema corrente", migra() == 0 and version() == SCHEMA_VERSION)
c = sqlite3.connect(DB)
c.execute("PRAGMA user_version = 99")
c.commit()
c.close()
check("database di una versione più recente -> codice 2", migra() == 2 and version() == 99)

cleanup()
make_legacy_db(DB)
check("database 1.0 -> codice 0, migrato, backup creato",
      migra() == 0 and version() == SCHEMA_VERSION and len(list(APP.glob("gare-backup-*.db"))) == 1)

c = sqlite3.connect(DB)
c.execute("PRAGMA user_version = 2")
c.commit()
c.close()
lock = sqlite3.connect(DB, timeout=0)
lock.execute("BEGIN EXCLUSIVE")
code = migra()
lock.rollback()
lock.close()
check("database bloccato da un altro programma -> codice 1", code == 1)
log = (APP / "gare-di-mate.log").read_text(encoding="utf-8")
check("errori scritti nel log", "--migra: errore" in log and "--migra: database di una versione più recente" in log)
cleanup()
finish()
