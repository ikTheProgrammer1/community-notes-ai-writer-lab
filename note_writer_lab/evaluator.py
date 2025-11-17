from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .models import Note, Tweet


URL_REGEX = re.compile(
    r"(https?://[^\s)]+)",
    flags=re.IGNORECASE,
)


@dataclass
class EvaluationResult:
    claim_opinion_score: float
    url_pass: bool
    raw_payload: Optional[Dict[str, Any]]
    url_count: int
    invalid_url_count: int


class NoteEvaluator:
    """
    Pre-scores notes before we even think about submitting.

    If you have X's official `evaluate_note` implementation available (e.g. via
    the Community Notes repo), you can plug it in here by wrapping it into this
    interface and populating `raw_payload` accordingly. By default we fall back
    to a lightweight heuristic for `claim_opinion_score` plus basic URL checks.
    """

    def __init__(self) -> None:
        self._external_evaluator = self._maybe_load_external_evaluator()

    def _maybe_load_external_evaluator(self):
        try:  # pragma: no cover - optional integration
            from communitynotes.evaluation import evaluate_note  # type: ignore[import]

            return evaluate_note
        except Exception:
            return None

    def evaluate(self, note: Note, tweet: Tweet) -> EvaluationResult:
        if self._external_evaluator is not None:
            return self._evaluate_with_external(note, tweet)
        return self._evaluate_with_heuristics(note, tweet)

    def _evaluate_with_external(self, note: Note, tweet: Tweet) -> EvaluationResult:
        # The exact call signature depends on the external library; you'll
        # likely need to adapt this to your local copy of the Community Notes
        # evaluation code.
        raw = self._external_evaluator(  # type: ignore[operator]
            note_text=note.text,
            tweet_text=tweet.text,
        )

        claim_opinion_score = float(
            raw.get("noteContent", {}).get("claimOpinionScore", 0.0)
        )
        has_url, url_count, invalid_url_count = self._basic_url_checks(note.text)
        url_pass = has_url and invalid_url_count == 0

        return EvaluationResult(
            claim_opinion_score=claim_opinion_score,
            url_pass=url_pass,
            raw_payload=raw,
            url_count=url_count,
            invalid_url_count=invalid_url_count,
        )

    def _evaluate_with_heuristics(self, note: Note, tweet: Tweet) -> EvaluationResult:
        """
        Very simple heuristic fallback:

        - Penalise subjective language (I, we, think, believe, should, must, etc.)
        - Reward mentions of sources, URLs, and specific verifiable claims.
        """
        lower = note.text.lower()

        subjective_tokens: List[str] = [
            "i think",
            "in my opinion",
            "we believe",
            "should",
            "must",
            "clearly",
            "obviously",
        ]

        subjective_hits = sum(lower.count(tok) for tok in subjective_tokens)

        # Basic structure/sourcing features
        has_url, url_count, invalid_url_count = self._basic_url_checks(note.text)
        has_numbers = bool(re.search(r"\b\d{2,}\b", note.text))
        has_quotes = '"' in note.text or "'" in note.text

        # Start from a neutral prior
        score = 0.6

        # Penalise subjective language
        score -= 0.05 * min(subjective_hits, 6)

        # Reward sourcing and specificity
        if has_url:
            score += 0.1
        if has_numbers:
            score += 0.05
        if has_quotes:
            score += 0.05

        # Penalty if many invalid-looking URLs
        if invalid_url_count >= 2:
            score -= 0.1

        score = max(0.0, min(1.0, score))

        # For URL pass, require at least one valid URL and no invalid URLs.
        url_pass = has_url and invalid_url_count == 0

        return EvaluationResult(
            claim_opinion_score=score,
            url_pass=url_pass,
            raw_payload=None,
            url_count=url_count,
            invalid_url_count=invalid_url_count,
        )

    @staticmethod
    def _basic_url_checks(text: str) -> tuple[bool, int, int]:
        urls = URL_REGEX.findall(text)
        url_count = len(urls)
        if not urls:
            return False, 0, 0

        invalid = 0
        for url in urls:
            # Very lightweight filter: ensure protocol and at least one dot
            if not url.lower().startswith(("http://", "https://")):
                invalid += 1
                continue
            if "." not in url.split("://", 1)[-1]:
                invalid += 1

        has_url = url_count > 0
        return has_url, url_count, invalid

