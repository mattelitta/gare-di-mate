"""Migrazioni dello schema SQLite, numerate con PRAGMA user_version.

Per cambiare la struttura del database: aggiungere un passaggio in fondo a MIGRATIONS
(mai modificare o riordinare quelli esistenti) e aggiornare i modelli in models.py.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


class MigrationError(Exception):
    pass


class SchemaTooNewError(Exception):
    pass


def _add_column(conn, table: str, column: str, ddl: str):
    columns = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# Ogni passaggio deve essere idempotente: i database precedenti alla numerazione
# (user_version = 0) possono averne già applicati alcuni, e SQLite esegue i DDL
# fuori transazione, quindi un passaggio interrotto può essere ripetuto.
def _time_columns(c):
    _add_column(c, "competitions", "time_offset_seconds", "FLOAT DEFAULT 0")
    _add_column(c, "competitions", "last_alive_at", "DATETIME")
    _add_column(c, "competitions", "recovery_crash_at", "DATETIME")
    _add_column(c, "competitions", "recovery_downtime_seconds", "FLOAT")


def _backfill_time_adjustments(c):
    # La tabella time_adjustments la crea create_all; qui si registra come un unico avanzamento
    # l'eventuale tempo già avanzato prima che i singoli avanzamenti venissero salvati.
    c.exec_driver_sql(
        "INSERT INTO time_adjustments (competition_id, seconds, game_seconds_at, reason, created_at) "
        "SELECT id, time_offset_seconds, 0, 'manuale', CURRENT_TIMESTAMP FROM competitions "
        "WHERE time_offset_seconds > 0 "
        "AND id NOT IN (SELECT competition_id FROM time_adjustments)"
    )


def _final_columns(c):
    _add_column(c, "competitions", "insertions_locked", "BOOLEAN DEFAULT 0")
    _add_column(c, "competitions", "final_ranking_json", "TEXT")
    _add_column(c, "competitions", "final_computed_at", "DATETIME")
    # Le gare "bloccate" con la versione precedente restano con gli inserimenti bloccati;
    # la loro classifica finale va calcolata di nuovo con il tasto apposito.
    columns = {row[1] for row in c.exec_driver_sql("PRAGMA table_info(competitions)")}
    if "final_locked" in columns:
        c.exec_driver_sql("UPDATE competitions SET insertions_locked = 1 WHERE final_locked = 1")


def _blackout_columns(c):
    _add_column(c, "competitions", "blackout_manual", "BOOLEAN")
    _add_column(c, "competitions", "blackout_manual_at", "FLOAT")


MIGRATIONS = [
    lambda c: _add_column(c, "displays", "text_scale", "INTEGER DEFAULT 3"),               # 1
    lambda c: _add_column(c, "competitions", "display_theme", "VARCHAR DEFAULT 'light'"),  # 2
    lambda c: _add_column(c, "submissions", "device_id", "VARCHAR(64)"),                   # 3
    _time_columns,                                                                         # 4
    _backfill_time_adjustments,                                                            # 5
    _final_columns,                                                                        # 6
    _blackout_columns,                                                                     # 7
    lambda c: _add_column(c, "competitions", "starting_score", "INTEGER"),                 # 8
    lambda c: _add_column(c, "competitions", "jolly_reveal", "VARCHAR(10) DEFAULT 'immediate'"),  # 9
    lambda c: _add_column(c, "submissions", "added_by_admin", "BOOLEAN DEFAULT 0"),          # 10
    # 11: accessi per dispositivo (tabella access_sessions, creata da create_all); il vecchio segreto
    # del cookie unico non serve più, e i dispositivi rifanno l'accesso una volta.
    lambda c: c.exec_driver_sql("DELETE FROM settings WHERE key = 'cookie_secret'"),          # 11
]
SCHEMA_VERSION = len(MIGRATIONS)


def _get_version(conn) -> int:
    return conn.exec_driver_sql("PRAGMA user_version").scalar()


def _set_version(conn, version: int):
    conn.exec_driver_sql(f"PRAGMA user_version = {int(version)}")


def backup(db_path: Path, from_version: int) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = db_path.with_name(f"gare-backup-{stamp}-schema{from_version}.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


def run(engine, db_path: Path, create_tables) -> str:
    """Porta il database allo schema corrente. Ritorna "nuovo", "invariato" o "aggiornato"."""
    with engine.connect() as conn:
        existed = conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'competitions'"
        ).first() is not None
        version = _get_version(conn)

    if version > SCHEMA_VERSION:
        raise SchemaTooNewError(
            "Le gare salvate sono state create da una versione più recente di Gare di Mate.\n\n"
            "Per usarle, installare la versione più recente del programma."
        )

    create_tables()  # crea solo le tabelle mancanti, non tocca quelle esistenti
    if not existed:
        with engine.begin() as conn:
            _set_version(conn, SCHEMA_VERSION)
        return "nuovo"
    if version == SCHEMA_VERSION:
        return "invariato"

    try:
        backup_path = backup(db_path, version)
    except Exception as e:
        log.exception("Backup del database non riuscito")
        raise MigrationError(
            "Non è stato possibile salvare una copia di sicurezza delle gare prima di aggiornarle, "
            "quindi non sono state modificate.\n\n"
            "Controllare che ci sia spazio libero sul disco e riaprire Gare di Mate."
        ) from e
    log.info("Migrazione schema %s -> %s (backup: %s)", version, SCHEMA_VERSION, backup_path)

    for target in range(version + 1, SCHEMA_VERSION + 1):
        try:
            with engine.begin() as conn:
                MIGRATIONS[target - 1](conn)
                _set_version(conn, target)
        except Exception as e:
            log.exception("Migrazione al passaggio %s non riuscita", target)
            raise MigrationError(
                "Non è stato possibile adattare le gare salvate alla nuova versione.\n\n"
                f"Nessun dato è andato perso: la copia di sicurezza è nel file\n{backup_path}"
            ) from e
    return "aggiornato"
