"""Migrazioni dello schema: database nuovo, vecchio, più recente, guasto a metà, con backup."""
import sqlite3

from sqlalchemy import create_engine

from _util import APP, check, finish, make_legacy_db
import migrations
import models  # noqa: F401  (registra le tabelle in Base)
from database import Base

WORK = APP / "_migrazioni"
WORK.mkdir(exist_ok=True)
N = migrations.SCHEMA_VERSION


def run(p):
    e = create_engine(f"sqlite:///{p.as_posix()}")
    try:
        return migrations.run(e, p, lambda: Base.metadata.create_all(bind=e))
    finally:
        e.dispose()


def info(p):
    c = sqlite3.connect(p)
    v = c.execute("PRAGMA user_version").fetchone()[0]
    cols = {t: {r[1] for r in c.execute(f"PRAGMA table_info({t})")} for t in ("competitions", "submissions")}
    counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("competitions", "teams", "submissions")}
    c.close()
    return v, cols, counts


def backups():
    return sorted(WORK.glob("gare-backup-*.db"))


def clear_backups():
    for f in backups():
        f.unlink()


p = WORK / "nuovo.db"
check("nuovo: esito 'nuovo'", run(p) == "nuovo")
check(f"nuovo: user_version = {N}, nessun backup", info(p)[0] == N and not backups())

p = WORK / "vecchio.db"
make_legacy_db(p)
v0, cols0, counts0 = info(p)
check("database 1.0: schema 0, senza device_id", v0 == 0 and "device_id" not in cols0["submissions"])
check("database 1.0: esito 'aggiornato'", run(p) == "aggiornato")
v, cols, counts = info(p)
check(f"database 1.0: schema {N}, colonne aggiunte",
      v == N and "device_id" in cols["submissions"] and "time_offset_seconds" in cols["competitions"])
check("database 1.0: dati conservati", counts == counts0)
check("database 1.0: un backup identico all'originale",
      len(backups()) == 1 and info(backups()[0])[0] == 0 and info(backups()[0])[2] == counts0)
check("secondo avvio: 'invariato', nessun nuovo backup", run(p) == "invariato" and len(backups()) == 1)

p = WORK / "futuro.db"
run(p)
c = sqlite3.connect(p)
c.execute(f"PRAGMA user_version = {N + 5}")
c.commit()
c.close()
try:
    run(p)
    check("più recente: rifiutato", False)
except migrations.SchemaTooNewError as e:
    check("più recente: rifiutato con SchemaTooNewError", "più recente" in str(e))
check("più recente: database non toccato", info(p)[0] == N + 5)

p = WORK / "guasto.db"
run(p)
c = sqlite3.connect(p)
c.execute(f"PRAGMA user_version = {N - 1}")
c.commit()
c.close()
clear_backups()
originale = migrations.MIGRATIONS[N - 1]


def guasto(conn):
    raise RuntimeError("guasto simulato")


migrations.MIGRATIONS[N - 1] = guasto
try:
    run(p)
    check("guasto: errore segnalato", False)
except migrations.MigrationError as e:
    check("guasto: MigrationError con il percorso del backup", "gare-backup-" in str(e))
finally:
    migrations.MIGRATIONS[N - 1] = originale
check("guasto: user_version fermo all'ultimo passaggio riuscito, backup presente",
      info(p)[0] == N - 1 and len(backups()) == 1)
check("guasto: al riavvio (passaggio sistemato) completa", run(p) == "aggiornato" and info(p)[0] == N)

p = WORK / "offset.db"
run(p)
c = sqlite3.connect(p)
c.execute("INSERT INTO competitions (name, date, threshold_minute, blackout_minute, status, time_offset_seconds, "
          "initial_value, n, k, first_delivery_bonuses_json, full_bonuses_json, duration_minutes, jolly_time_minutes, "
          "num_qualified, final_reveal_count, total_paused_seconds, revealed_positions, final_locked, display_theme, "
          "created_at) VALUES ('X', '2026-01-01', 60, 80, 'running', 120, 40, 2, 1, '[]', '[]', 90, 30, 0, 3, 0, 0, 0, "
          "'light', CURRENT_TIMESTAMP)")
c.execute("PRAGMA user_version = 4")
c.commit()
c.close()
run(p)
c = sqlite3.connect(p)
rows = c.execute("SELECT seconds, reason FROM time_adjustments").fetchall()
c.close()
check("schema 5: tempo avanzato preesistente diventa un avanzamento", rows == [(120.0, "manuale")])
finish()
