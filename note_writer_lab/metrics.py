from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import Note, NoteScore, Submission, WriterConfig


@dataclass
class AdmissionMetrics:
    high_score_pct: float
    low_score_pct: float
    url_pass_pct: float
    sample_size: int


@dataclass
class LabMetrics:
    avg_score: Optional[float]
    pct_above_submit_threshold: float
    rewrite_count: int
    total_notes: int


@dataclass
class WriterDashboard:
    writer: WriterConfig
    admission: AdmissionMetrics
    lab: LabMetrics
    recent_notes: List[Note]


def compute_admission_metrics(session: Session, writer: WriterConfig) -> AdmissionMetrics:
    submissions = list(
        session.scalars(
            select(Submission)
            .where(
                Submission.writer_id == writer.id,
                Submission.test_mode.is_(True),
            )
            .order_by(Submission.created_at.desc())
            .limit(50)
        )
    )

    scores: list[NoteScore] = [
        s.note.score  # type: ignore[union-attr]
        for s in submissions
        if s.note is not None and s.note.score is not None
    ]
    n = len(scores)

    if n == 0:
        return AdmissionMetrics(
            high_score_pct=0.0,
            low_score_pct=0.0,
            url_pass_pct=0.0,
            sample_size=0,
        )

    high = sum(
        1
        for sc in scores
        if sc.claim_opinion_score >= writer.submit_min_score
    )
    low = n - high
    url_pass = sum(1 for sc in scores if sc.url_pass)

    return AdmissionMetrics(
        high_score_pct=100.0 * high / n,
        low_score_pct=100.0 * low / n,
        url_pass_pct=100.0 * url_pass / n,
        sample_size=n,
    )


def compute_lab_metrics(session: Session, writer: WriterConfig) -> LabMetrics:
    stmt = (
        select(
            func.count(NoteScore.id),
            func.avg(NoteScore.claim_opinion_score),
            func.sum(
                case(
                    (NoteScore.claim_opinion_score >= writer.submit_min_score, 1),
                    else_=0,
                )
            ),
        )
        .join(Note, NoteScore.note_id == Note.id)
        .where(Note.writer_id == writer.id)
    )
    total_scores, avg_score, above_threshold = session.execute(stmt).one()

    total_scores = int(total_scores or 0)
    above_threshold = int(above_threshold or 0)

    rewrite_count = int(
        session.scalar(
            select(func.count(Note.id)).where(
                Note.writer_id == writer.id,
                Note.stage == "rewrite",
            )
        )
        or 0
    )

    pct_above = (
        100.0 * above_threshold / total_scores if total_scores > 0 else 0.0
    )

    return LabMetrics(
        avg_score=float(avg_score) if avg_score is not None else None,
        pct_above_submit_threshold=pct_above,
        rewrite_count=rewrite_count,
        total_notes=total_scores,
    )


def build_writer_dashboard(
    session: Session, writer: WriterConfig, recent_limit: int = 20
) -> WriterDashboard:
    admission = compute_admission_metrics(session, writer)
    lab = compute_lab_metrics(session, writer)

    recent_notes = list(
        session.scalars(
            select(Note)
            .where(Note.writer_id == writer.id)
            .order_by(Note.created_at.desc())
            .limit(recent_limit)
        )
    )

    return WriterDashboard(
        writer=writer,
        admission=admission,
        lab=lab,
        recent_notes=recent_notes,
    )


def calculate_bridge_score(scores: List[float], penalty_factor: float = 1.5) -> float:
    """
    Calculates the BridgeScore based on the formula:
    Score = Mean(Ratings) - (Penalty_Factor * Standard_Deviation)
    
    Args:
        scores: List of float scores (0.0 - 1.0)
        penalty_factor: Factor to penalize variance (default 1.5)
        
    Returns:
        float: The calculated BridgeScore (clamped 0.0 - 1.0)
    """
    if not scores:
        return 0.0
        
    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    std_dev = variance ** 0.5
    
    raw_score = mean - (penalty_factor * std_dev)
    return max(0.0, min(1.0, raw_score))
