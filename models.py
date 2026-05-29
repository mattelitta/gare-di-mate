import json
from datetime import datetime
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    date: Mapped[str] = mapped_column(String(20))  # ISO date string

    # Scoring parameters
    initial_value: Mapped[int] = mapped_column(Integer, default=40)
    n: Mapped[int] = mapped_column(Integer, default=2)
    k: Mapped[int] = mapped_column(Integer, default=1)
    first_delivery_bonuses_json: Mapped[str] = mapped_column(Text, default="[20,15,10,5,3]")
    full_bonuses_json: Mapped[str] = mapped_column(Text, default="[50,30,20,15,10]")

    # Timing parameters (in minutes)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90)
    jolly_time_minutes: Mapped[int] = mapped_column(Integer, default=30)
    threshold_minute: Mapped[int] = mapped_column(Integer)  # values stop growing after this many minutes from start
    blackout_minute: Mapped[int] = mapped_column(Integer)   # ranking hidden after this many minutes from start

    # Classification
    num_qualified: Mapped[int] = mapped_column(Integer, default=0)
    final_reveal_count: Mapped[int] = mapped_column(Integer, default=3)  # positions revealed one by one

    # Auth
    password: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # State
    status: Mapped[str] = mapped_column(String(20), default="created")  # created|running|paused|ended
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_paused_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Final ranking reveal state
    revealed_positions: Mapped[int] = mapped_column(Integer, default=0)
    final_locked: Mapped[bool] = mapped_column(Boolean, default=False)  # True when insertions closed

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    teams: Mapped[list["Team"]] = relationship("Team", back_populates="competition", cascade="all, delete-orphan")
    problems: Mapped[list["Problem"]] = relationship("Problem", back_populates="competition", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="competition", cascade="all, delete-orphan")
    jolly_choices: Mapped[list["JollyChoice"]] = relationship("JollyChoice", back_populates="competition", cascade="all, delete-orphan")
    penalties: Mapped[list["Penalty"]] = relationship("Penalty", back_populates="competition", cascade="all, delete-orphan")
    displays: Mapped[list["Display"]] = relationship("Display", back_populates="competition", cascade="all, delete-orphan")

    @property
    def first_delivery_bonuses(self) -> list[int]:
        return json.loads(self.first_delivery_bonuses_json)

    @first_delivery_bonuses.setter
    def first_delivery_bonuses(self, value: list[int]):
        self.first_delivery_bonuses_json = json.dumps(value)

    @property
    def full_bonuses(self) -> list[int]:
        return json.loads(self.full_bonuses_json)

    @full_bonuses.setter
    def full_bonuses(self, value: list[int]):
        self.full_bonuses_json = json.dumps(value)

    def elapsed_seconds(self, at: datetime | None = None) -> float:
        """Seconds of actual game time elapsed (excluding pauses)."""
        if self.started_at is None:
            return 0.0
        now = at or datetime.utcnow()
        if self.status == "ended" and self.ended_at:
            now = self.ended_at
        raw = (now - self.started_at).total_seconds()
        paused = self.total_paused_seconds
        if self.status == "paused" and self.paused_at:
            paused += (now - self.paused_at).total_seconds()
        return max(0.0, raw - paused)

    def elapsed_minutes(self, at: datetime | None = None) -> float:
        return self.elapsed_seconds(at) / 60.0

    def game_second_for(self, wall_time: datetime) -> float:
        """Convert a wall-clock time to game seconds elapsed at that moment."""
        if self.started_at is None or wall_time < self.started_at:
            return 0.0
        return self.elapsed_seconds(at=wall_time)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    number: Mapped[int] = mapped_column(Integer)  # 1-based id within competition
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(200))
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


class Display(Base):
    __tablename__ = "displays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("competitions.id"))
    name: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String(50), default="")
    current_view: Mapped[str] = mapped_column(String(50), default="test")
    # test|ranking|team_list|problem_values|competition_status|final_ranking
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    text_scale: Mapped[int] = mapped_column(Integer, default=3)  # 1=minimo … 5=massimo

    competition: Mapped["Competition"] = relationship("Competition", back_populates="displays")
