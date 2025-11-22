from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class WriterConfig(Base):
    __tablename__ = "writers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    rewrite_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rewrite_min_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.4
    )
    submit_min_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.75
    )

    max_notes_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    notes: Mapped[list["Note"]] = relationship(
        back_populates="writer", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="writer", cascade="all, delete-orphan"
    )


class Tweet(Base):
    __tablename__ = "tweets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tweet_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    author_handle: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    tweet_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    notes: Mapped[list["Note"]] = relationship(
        back_populates="tweet", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="tweet", cascade="all, delete-orphan"
    )


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    writer_id: Mapped[int] = mapped_column(
        ForeignKey("writers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tweet_id: Mapped[int] = mapped_column(
        ForeignKey("tweets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # "draft" for first pass, "rewrite" for improved ones
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    text: Mapped[str] = mapped_column(Text, nullable=False)

    parent_note_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("notes.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    writer: Mapped[WriterConfig] = relationship(back_populates="notes")
    tweet: Mapped[Tweet] = relationship(back_populates="notes")
    parent_note: Mapped[Optional["Note"]] = relationship(remote_side=[id])

    score: Mapped[Optional["NoteScore"]] = relationship(
        back_populates="note", uselist=False, cascade="all, delete-orphan"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )
    simulations: Mapped[list["Simulation"]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )
    simulation_runs: Mapped[list["SimulationRun"]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )


class NoteScore(Base):
    __tablename__ = "note_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    claim_opinion_score: Mapped[float] = mapped_column(Float, nullable=False)
    url_pass: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Optional raw evaluation payload, e.g. from official evaluate_note
    raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    note: Mapped[Note] = relationship(back_populates="score")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    writer_id: Mapped[int] = mapped_column(
        ForeignKey("writers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tweet_id: Mapped[int] = mapped_column(
        ForeignKey("tweets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    test_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="submitted"
    )  # submitted / failed

    api_response: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    note: Mapped[Note] = relationship(back_populates="submissions")
    writer: Mapped[WriterConfig] = relationship(back_populates="submissions")
    tweet: Mapped[Tweet] = relationship(back_populates="submissions")


class GoldStandardCase(Base):
    """
    A 'ground truth' case from Community Notes history used for calibration.
    """
    __tablename__ = "gold_standard_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tweet_id: Mapped[str] = mapped_column(String(32), nullable=False)
    tweet_text: Mapped[str] = mapped_column(Text, nullable=False)
    note_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)  # HELPFUL, NOT_HELPFUL
    original_rating_status: Mapped[str] = mapped_column(String(64), nullable=True) # e.g. "HELPFUL_INFORMED"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SimulationRun(Base):
    """
    M2: A full run of the BridgeRank simulator on a note.
    Replaces/Enhances the M1 'Simulation' concept.
    """
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    bridge_score: Mapped[float] = mapped_column(Float, nullable=False)
    consensus_status: Mapped[str] = mapped_column(String(32), nullable=True) # e.g. "LIKELY_HELPFUL"
    
    # Metadata about the run
    model_used: Mapped[str] = mapped_column(String(64), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    note: Mapped["Note"] = relationship(back_populates="simulation_runs")
    persona_feedbacks: Mapped[list["PersonaFeedback"]] = relationship(
        back_populates="simulation_run", cascade="all, delete-orphan"
    )


class PersonaFeedback(Base):
    """
    Individual critique from a specific persona in a simulation run.
    """
    __tablename__ = "persona_feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    persona_name: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False) # 0.0 - 1.0
    critique: Mapped[str] = mapped_column(Text, nullable=False)
    missing_context: Mapped[bool] = mapped_column(Boolean, default=False)
    
    strengths: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    weaknesses: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    simulation_run: Mapped["SimulationRun"] = relationship(back_populates="persona_feedbacks")


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    bridge_score: Mapped[float] = mapped_column(Float, nullable=False)
    architect_dump: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    critiques_dump: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    note: Mapped[Note] = relationship(back_populates="simulations")

