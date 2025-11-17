from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import session_scope
from .evaluator import NoteEvaluator
from .grok_client import GrokClient
from .models import Note, NoteScore, Tweet, WriterConfig
from .x_client import XClient
from .tags import choose_misleading_tags


def upsert_tweet(session: Session, tweet_data: dict) -> Tweet:
    tweet_id = str(tweet_data.get("id") or tweet_data.get("tweet_id"))
    if not tweet_id:
        raise ValueError("Tweet data missing id field.")

    result = session.execute(
        select(Tweet).where(Tweet.tweet_id == tweet_id)
    ).scalar_one_or_none()

    if result is not None:
        return result

    text = tweet_data.get("text") or ""
    author = tweet_data.get("author", {}) or {}
    author_id = author.get("id")
    author_handle = author.get("username") or author.get("handle")

    tweet = Tweet(
        tweet_id=tweet_id,
        text=text,
        author_id=author_id,
        author_handle=author_handle,
    )
    session.add(tweet)
    session.flush()
    return tweet


def run_lab_once() -> None:
    """
    Single pass of the lab:

    - For each enabled writer:
      - Pull eligible posts
      - Draft notes with Grok
      - Pre-score (claim_opinion_score + URL checks)
      - Optionally rewrite weak notes
      - Submit strong notes in test_mode
      - Persist everything to SQLite
    """
    with session_scope() as session:
        writers: List[WriterConfig] = list(
            session.scalars(
                select(WriterConfig).where(WriterConfig.enabled.is_(True))
            )
        )

        if not writers:
            return

        x_client = XClient()
        grok_client = GrokClient()
        evaluator = NoteEvaluator()

        for writer in writers:
            _run_for_writer(
                session=session,
                writer=writer,
                x_client=x_client,
                grok_client=grok_client,
                evaluator=evaluator,
            )


def _run_for_writer(
    session: Session,
    writer: WriterConfig,
    x_client: XClient,
    grok_client: GrokClient,
    evaluator: NoteEvaluator,
) -> None:
    max_notes = min(
        writer.max_notes_per_run, settings.max_notes_per_writer_per_run
    )

    eligible = x_client.fetch_eligible_tweets(max_results=max_notes)

    for tweet_data in eligible:
        tweet = upsert_tweet(session, tweet_data)
        session.flush()

        draft_text = grok_client.generate_note(tweet=tweet, writer=writer)

        draft_note = Note(
            writer=writer,
            tweet=tweet,
            stage="draft",
            text=draft_text,
        )
        session.add(draft_note)
        session.flush()

        draft_eval = evaluator.evaluate(draft_note, tweet)
        draft_score = NoteScore(
            note=draft_note,
            claim_opinion_score=draft_eval.claim_opinion_score,
            url_pass=draft_eval.url_pass,
            raw_payload=draft_eval.raw_payload,
        )
        session.add(draft_score)
        session.flush()

        best_note = draft_note
        best_eval = draft_eval

        if (
            writer.rewrite_min_score is not None
            and draft_eval.claim_opinion_score < writer.submit_min_score
            and draft_eval.claim_opinion_score >= writer.rewrite_min_score
        ):
            weakness = (
                f"Initial claim_opinion_score={draft_eval.claim_opinion_score:.2f}, "
                f"url_pass={draft_eval.url_pass} "
                f"(urls={draft_eval.url_count}, invalid={draft_eval.invalid_url_count})."
            )
            rewrite_text = grok_client.rewrite_note(
                tweet=tweet,
                writer=writer,
                current_note=draft_note.text,
                weakness_summary=weakness,
            )

            rewrite_note = Note(
                writer=writer,
                tweet=tweet,
                stage="rewrite",
                text=rewrite_text,
                parent_note=draft_note,
            )
            session.add(rewrite_note)
            session.flush()

            rewrite_eval = evaluator.evaluate(rewrite_note, tweet)
            rewrite_score = NoteScore(
                note=rewrite_note,
                claim_opinion_score=rewrite_eval.claim_opinion_score,
                url_pass=rewrite_eval.url_pass,
                raw_payload=rewrite_eval.raw_payload,
            )
            session.add(rewrite_score)
            session.flush()

            if rewrite_eval.claim_opinion_score > best_eval.claim_opinion_score:
                best_note = rewrite_note
                best_eval = rewrite_eval

        if (
            best_eval.claim_opinion_score >= writer.submit_min_score
            and best_eval.url_pass
            and best_eval.url_count > 0
        ):
            from .models import Submission  # local import to avoid cycle

            # Choose misleading_tags based on the final tweet + note.
            tags = choose_misleading_tags(tweet=tweet, note=best_note)

            try:
                resp = x_client.submit_note(
                    tweet_id=tweet.tweet_id,
                    note_text=best_note.text,
                    test_mode=True,
                    writer_name=writer.name,
                    misleading_tags=tags,
                )
                submission = Submission(
                    note=best_note,
                    writer=writer,
                    tweet=tweet,
                    test_mode=True,
                    status="submitted",
                    api_response=resp,
                )
            except Exception as exc:  # pragma: no cover - network failure path
                # Capture both the high-level error and any response body to
                # make debugging payload issues easier.
                body = ""
                response = getattr(exc, "response", None)
                if response is not None:
                    try:
                        body = response.text
                    except Exception:
                        body = ""
                submission = Submission(
                    note=best_note,
                    writer=writer,
                    tweet=tweet,
                    test_mode=True,
                    status="failed",
                    error_message=f"{exc} | body={body}",
                )

            session.add(submission)
            session.flush()
