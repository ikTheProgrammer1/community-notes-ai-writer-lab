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
    from .simulator import BridgeRankSimulator
    from .researcher import GroundingClient
    
    simulator = BridgeRankSimulator(db=session, grok_client=grok_client)
    researcher = GroundingClient(grok_client=grok_client)

    max_notes = min(
        writer.max_notes_per_run, settings.max_notes_per_writer_per_run
    )

    eligible = x_client.fetch_eligible_tweets(max_results=max_notes)

    for tweet_data in eligible:
        tweet = upsert_tweet(session, tweet_data)
        session.flush()

        # Step 1: Architect - Generate 3 Variants
        variants = grok_client.generate_note_variants(tweet)
        if not variants:
            # Fallback to single note generation if variants fail
            text = grok_client.generate_note(tweet, writer)
            variants = [{"strategy": "Legacy", "text": text}]

        candidate_notes = []
        
        for variant in variants:
            strategy = variant.get("strategy", "Unknown")
            text = variant.get("text", "")
            
            # Create Draft Note
            draft_note = Note(
                writer=writer,
                tweet=tweet,
                stage="draft",
                text=text,
            )
            session.add(draft_note)
            session.flush()
            
            # Step 2: Grounding (Extract Claims & Verify)
            # For now, we just log claims, but in future we can use them to filter
            claims = researcher.extract_claims(text)
            # verify_url logic can be added here if note has links
            
            # Step 3: Simulation (The Council)
            simulation_run = simulator.run_simulation(draft_note)
            
            candidate_notes.append({
                "note": draft_note,
                "score": simulation_run.bridge_score,
                "run": simulation_run
            })

        # Step 4: Refinement
        # Identify lowest scored draft to refine
        if candidate_notes:
            candidate_notes.sort(key=lambda x: x["score"])
            worst_candidate = candidate_notes[0]
            
            # Refine the worst one
            refined_note = simulator.run_refiner(worst_candidate["note"], worst_candidate["run"])
            
            # Simulate the refined note
            refined_run = simulator.run_simulation(refined_note)
            
            candidate_notes.append({
                "note": refined_note,
                "score": refined_run.bridge_score,
                "run": refined_run
            })

        # Step 5: Selection & Submission
        # Pick the absolute best note
        candidate_notes.sort(key=lambda x: x["score"], reverse=True)
        best_candidate = candidate_notes[0]
        best_note = best_candidate["note"]
        best_score = best_candidate["score"]
        
        # Evaluate with legacy evaluator for metadata (url_pass etc)
        # We still need NoteScore for dashboard compatibility
        best_eval = evaluator.evaluate(best_note, tweet)
        best_note_score = NoteScore(
            note=best_note,
            claim_opinion_score=best_eval.claim_opinion_score, # Legacy score
            url_pass=best_eval.url_pass,
            raw_payload=best_eval.raw_payload,
        )
        session.add(best_note_score)
        session.flush()

        # Submit if BridgeScore is high enough (e.g. > 0.6)
        # Using a hardcoded threshold for M2 or writer config?
        # Let's use writer.submit_min_score but mapped to BridgeScore?
        # Or just use a fixed 0.6 for now as per blueprint "Likely Helpful"
        submit_threshold = 0.6
        
        if best_score >= submit_threshold:
            from .models import Submission  # local import to avoid cycle

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
            except Exception as exc:
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
