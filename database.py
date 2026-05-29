from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, selectinload

DATABASE_URL = "sqlite:///./gare.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from models import Competition, Team, Problem, Submission, JollyChoice, Penalty, Display  # noqa
    Base.metadata.create_all(bind=engine)
    _migrate_db()


def _migrate_db():
    """Aggiunge colonne mancanti per migrazioni incrementali (idempotente)."""
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE displays ADD COLUMN text_scale INTEGER DEFAULT 3",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # colonna già presente


def load_comp_full(comp_id: int, db):
    """Carica una gara con tutte le relazioni in una sola query (eager loading).
    Evita il problema N+1 query del lazy loading di SQLAlchemy."""
    from models import Competition
    return (
        db.query(Competition)
        .options(
            selectinload(Competition.teams),
            selectinload(Competition.problems),
            selectinload(Competition.submissions),
            selectinload(Competition.jolly_choices),
            selectinload(Competition.penalties),
            selectinload(Competition.displays),
        )
        .filter(Competition.id == comp_id)
        .first()
    )
