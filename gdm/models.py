import json
from datetime import datetime, timedelta
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from gdm.database import Base


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    date: Mapped[str] = mapped_column(String(20), default="")  # ISO date string; facoltativa: "" se non indicata

    # Scoring parameters
    initial_value: Mapped[int] = mapped_column(Integer, default=40)
    starting_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = 10 × numero di problemi
    n: Mapped[int] = mapped_column(Integer, default=2)
    k: Mapped[int] = mapped_column(Integer, default=1)
    first_delivery_bonuses_json: Mapped[str] = mapped_column(Text, default="[20,15,10,5,3]")
    full_bonuses_json: Mapped[str] = mapped_column(Text, default="[50,30,20,15,10]")

    # Timing parameters (in minutes)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90)
    jolly_time_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # Tempo massimo per le domande sul testo (minuti dalla partenza; None = non previsto; 30 di default nel
    # modulo di creazione). Non cambia nulla nella gara: il tempo rimanente si mostra all'Admin e agli
    # inseritori, solo se cade prima della fine della gara.
    questions_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Quando i jolly diventano pubblici nei display: 'immediate' (appena inseriti) o 'deadline'
    # (tutti insieme alla chiusura dei jolly; fino ad allora i display contano i punti senza jolly).
    jolly_reveal: Mapped[str] = mapped_column(String(10), default='immediate', server_default='immediate')
    threshold_minute: Mapped[int] = mapped_column(Integer)  # values stop growing after this many minutes from start
    blackout_minute: Mapped[int] = mapped_column(Integer)   # ranking hidden after this many minutes from start
    # Oscuramento impostato a mano dall'admin (None = automatico) e tempo di gara in cui è stato impostato.
    blackout_manual: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    blackout_manual_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Classification
    num_qualified: Mapped[int] = mapped_column(Integer, default=0)
    final_reveal_count: Mapped[int] = mapped_column(Integer, default=3)  # positions revealed one by one

    # State
    status: Mapped[str] = mapped_column(String(20), default="created")  # created|running|paused|ended
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_paused_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Tempo: avanzamenti manuali e ripresa dopo una chiusura del programma (vedi tempo.py)
    time_offset_seconds: Mapped[float] = mapped_column(Float, default=0.0)  # somma degli avanzamenti manuali
    last_alive_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # battito del server a gara in corso
    recovery_crash_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # ultimo battito prima della chiusura
    recovery_downtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)  # durata della chiusura, da mostrare all'admin

    # Display
    display_theme: Mapped[str] = mapped_column(String(10), default='light')  # dark|light

    # Final ranking reveal state
    revealed_positions: Mapped[int] = mapped_column(Integer, default=0)
    # A gara terminata: "fotografia" della classifica finale, ricalcolabile; è quella mostrata dai
    # display e rivelata dalla regia.
    # Vecchio blocco degli inserimenti, sostituito dall'archiviazione (vedi is_archived): resta mappato
    # solo perché nei database esistenti la colonna può essere NOT NULL senza default.
    insertions_locked_old: Mapped[bool] = mapped_column("insertions_locked", Boolean, default=False)
    # Gara archiviata: None = automatico (24 ore dopo la fine), True/False = scelto dall'Admin.
    archived_manual: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    final_ranking_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Non più usata (sostituita dai due campi sopra), ma resta mappata: nei database esistenti
    # è NOT NULL senza default, e senza mappatura la creazione di una gara fallirebbe.
    final_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    teams: Mapped[list["Team"]] = relationship("Team", back_populates="competition", cascade="all, delete-orphan")
    problems: Mapped[list["Problem"]] = relationship("Problem", back_populates="competition", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="competition", cascade="all, delete-orphan")
    jolly_choices: Mapped[list["JollyChoice"]] = relationship("JollyChoice", back_populates="competition", cascade="all, delete-orphan")
    penalties: Mapped[list["Penalty"]] = relationship("Penalty", back_populates="competition", cascade="all, delete-orphan")
    displays: Mapped[list["Display"]] = relationship("Display", back_populates="competition", cascade="all, delete-orphan")
    time_adjustments: Mapped[list["TimeAdjustment"]] = relationship(
        "TimeAdjustment", back_populates="competition", cascade="all, delete-orphan")

    @property
    def first_delivery_bonuses(self) -> list[int]:
        return json.loads(self.first_delivery_bonuses_json)

    @first_delivery_bonuses.setter
    def first_delivery_bonuses(self, value: list[int]):
        self.first_delivery_bonuses_json = json.dumps(value)

    @property
    def effective_starting_score(self) -> int:
        """Punteggio iniziale delle squadre: quello indicato, oppure 10 × numero di problemi."""
        return self.starting_score if self.starting_score is not None else 10 * len(self.problems)

    @property
    def final_ranking(self) -> list[dict] | None:
        """Classifica finale calcolata: [{id, number, name, city, is_guest, total}] in ordine."""
        return json.loads(self.final_ranking_json) if self.final_ranking_json else None

    @property
    def full_bonuses(self) -> list[int]:
        return json.loads(self.full_bonuses_json)

    @full_bonuses.setter
    def full_bonuses(self, value: list[int]):
        self.full_bonuses_json = json.dumps(value)

    def elapsed_seconds(self) -> float:
        """Secondi di gara trascorsi: tempo reale meno le pause, più gli avanzamenti manuali."""
        if self.started_at is None:
            return 0.0
        now = datetime.utcnow()
        if self.status == "ended" and self.ended_at:
            now = self.ended_at
        raw = (now - self.started_at).total_seconds()
        paused = self.total_paused_seconds
        if self.status == "paused" and self.paused_at:
            paused += (now - self.paused_at).total_seconds()
        return max(0.0, raw - paused + (self.time_offset_seconds or 0.0))

    def elapsed_minutes(self) -> float:
        return self.elapsed_seconds() / 60.0

    def jolly_public(self) -> bool:
        """I jolly (e il loro raddoppio dei punti) sono visibili nei display?"""
        return (self.jolly_reveal != "deadline" or self.status == "ended"
                or self.elapsed_seconds() >= self.jolly_time_minutes * 60)

    ARCHIVIA_DOPO = timedelta(hours=24)

    def archive_auto_at(self) -> datetime | None:
        """Quando la gara si archivia da sola: 24 ore dopo la fine (None se non è terminata)."""
        if self.status != "ended" or self.ended_at is None:
            return None
        return self.ended_at + self.ARCHIVIA_DOPO

    def is_archived(self) -> bool:
        """Gara archiviata: non accetta inserimenti e non compare agli inseritori e ai display.
        Solo una gara terminata può esserlo: da sola 24 ore dopo la fine, oppure per scelta dell'Admin
        (che può anche de-archiviarla: allora resta tale)."""
        if self.status != "ended":
            return False
        if self.archived_manual is not None:
            return self.archived_manual
        quando = self.archive_auto_at()
        return quando is not None and datetime.utcnow() >= quando

    @property
    def insertions_locked(self) -> bool:
        """Inserimenti chiusi: oggi solo per le gare archiviate (tutti i controlli passano da qui)."""
        return self.is_archived()

    def blackout_auto(self) -> bool:
        """Oscuramento automatico: dal minuto di oscuramento e sempre a gara terminata."""
        return self.status == "ended" or (
            self.status in ("running", "paused") and self.elapsed_seconds() >= self.blackout_minute * 60
        )

    def blackout_active(self) -> bool:
        """Classifica (ed elenco squadre, stato gara) nascosta nei display.

        L'admin può oscurare o mostrare a mano; gli scatti automatici successivi prevalgono:
        il minuto di oscuramento raggiunto dopo l'impostazione manuale, e "Termina" (che azzera
        l'impostazione manuale).
        """
        if self.blackout_manual is None:
            return self.blackout_auto()
        soglia = self.blackout_minute * 60
        if (self.blackout_manual_at or 0.0) < soglia <= self.elapsed_seconds() and self.status != "created":
            return True
        return self.blackout_manual


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    number: Mapped[int] = mapped_column(Integer)  # 1-based id within competition
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(200), default="")  # facoltativa: "" se non indicata
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)

    competition: Mapped["Competition"] = relationship("Competition", back_populates="teams")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="team")
    jolly_choices: Mapped[list["JollyChoice"]] = relationship("JollyChoice", back_populates="team")
    penalties: Mapped[list["Penalty"]] = relationship("Penalty", back_populates="team")


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    number: Mapped[int] = mapped_column(Integer)  # 1-based id within competition
    name: Mapped[str] = mapped_column(String(200))
    answer: Mapped[str] = mapped_column(String(4))  # always 4 digits with leading zeros

    competition: Mapped["Competition"] = relationship("Competition", back_populates="problems")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="problem")
    jolly_choices: Mapped[list["JollyChoice"]] = relationship("JollyChoice", back_populates="problem")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"))
    problem_id: Mapped[int] = mapped_column(Integer, ForeignKey("problems.id"))
    answer: Mapped[str] = mapped_column(String(4))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    is_post_game: Mapped[bool] = mapped_column(Boolean, default=False)
    # game_seconds: game time at submission (capped at duration for post-game)
    game_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # cookie del dispositivo che l'ha inserita
    # Aggiunta dall'Admin dallo storico con un tempo indicato a mano (lo vede solo l'Admin).
    added_by_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')

    competition: Mapped["Competition"] = relationship("Competition", back_populates="submissions")
    team: Mapped["Team"] = relationship("Team", back_populates="submissions")
    problem: Mapped["Problem"] = relationship("Problem", back_populates="submissions")


class JollyChoice(Base):
    __tablename__ = "jolly_choices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"))
    problem_id: Mapped[int] = mapped_column(Integer, ForeignKey("problems.id"))
    game_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    competition: Mapped["Competition"] = relationship("Competition", back_populates="jolly_choices")
    team: Mapped["Team"] = relationship("Team", back_populates="jolly_choices")
    problem: Mapped["Problem"] = relationship("Problem", back_populates="jolly_choices")


class Penalty(Base):
    __tablename__ = "penalties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"))
    value: Mapped[int] = mapped_column(Integer)  # negative = deduction, positive = bonus
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    competition: Mapped["Competition"] = relationship("Competition", back_populates="penalties")
    team: Mapped["Team"] = relationship("Team", back_populates="penalties")


class TimeAdjustment(Base):
    """Un avanzamento del tempo di gara (la somma è Competition.time_offset_seconds)."""
    __tablename__ = "time_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    seconds: Mapped[float] = mapped_column(Float)  # secondi di gara aggiunti
    game_seconds_at: Mapped[float] = mapped_column(Float)  # tempo di gara subito prima dell'avanzamento
    reason: Mapped[str] = mapped_column(String(20), default="manuale")  # manuale | ripresa (dopo una chiusura)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    competition: Mapped["Competition"] = relationship("Competition", back_populates="time_adjustments")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Display(Base):
    __tablename__ = "displays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    name: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String(50), default="")
    current_view: Mapped[str] = mapped_column(String(50), default="test")
    # test|ranking|team_list|problem_values|competition_status|matrix|final_ranking
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    text_scale: Mapped[int] = mapped_column(Integer, default=3)  # 1=minimo … 7=massimo
    # Schermo interno (es. sala dello staff), scelto dalla regia: ignora l'oscuramento e mostra
    # sempre classifica e punteggi. Non va usato per schermi visibili al pubblico.
    internal: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    # Più viste che si alternano ogni rotation_seconds secondi (scelte dalla regia). La vista del
    # momento la calcola il server dall'orologio (Display.view_now), così gli schermi con le stesse
    # impostazioni cambiano insieme anche a regia chiusa.
    rotation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    rotation_views_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rotation_seconds: Mapped[int] = mapped_column(Integer, default=15, server_default='15')

    competition: Mapped["Competition"] = relationship("Competition", back_populates="displays")

    @property
    def rotation_views(self) -> list[str]:
        try:
            return json.loads(self.rotation_views_json) if self.rotation_views_json else []
        except ValueError:
            return []

    def view_now(self, now: float | None = None) -> str:
        """Vista da mostrare adesso: quella scelta, oppure quella del turno se le viste si alternano."""
        views = self.rotation_views
        if not self.rotation_enabled or not views:
            return self.current_view
        import time
        secondi = max(1, self.rotation_seconds or 15)
        return views[int((now if now is not None else time.time()) // secondi) % len(views)]


class AccessSession(Base):
    """Un accesso di un dispositivo della rete: uno per ogni login riuscito, revocabile dall'Admin.

    Il browser conserva solo il token casuale; qui c'è la sua impronta SHA-256, quindi chi legge
    il database non può usare i token. `role` e `scope` preparano gli accessi parziali futuri
    (es. solo display, o solo alcuni display): oggi ogni accesso con la password è 'completo'.
    """
    __tablename__ = "access_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="completo")
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON, per accessi parziali
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ip: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
