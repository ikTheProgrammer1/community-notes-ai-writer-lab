from __future__ import annotations

import argparse

import uvicorn

from .config import settings
from .db import engine, session_scope
from .lab_runner import run_lab_once
from .models import Base, WriterConfig
from .web import app as fastapi_app


def init_db(with_example_writers: bool = True) -> None:
    Base.metadata.create_all(bind=engine)

    if not with_example_writers:
        return

    with session_scope() as session:
        existing = session.query(WriterConfig).count()
        if existing:
            return

        conservative = WriterConfig(
            name="Grok Conservative",
            description=(
                "High-precision writer aimed at only submitting very strong, "
                "well-sourced notes."
            ),
            prompt=(
                "You are drafting a Community Note on X.\n\n"
                "Tweet:\n{tweet_text}\n\n"
                "Write a concise, neutral note that:\n"
                "- Focuses on verifiable claims in the tweet\n"
                "- Provides citations or URLs to high-quality sources\n"
                "- Avoids editorialising, personal opinions, or insults\n"
                "- Uses clear, simple language and fits comfortably within a 280-character Community Note limit."
            ),
            rewrite_prompt=(
                "You are editing a Community Note that is not strong enough yet.\n\n"
                "Tweet:\n{tweet_text}\n\n"
                "Current note:\n{current_note}\n\n"
                "Weaknesses:\n{weakness_summary}\n\n"
                "Rewrite the note to be:\n"
                "- More clearly tied to specific claims in the tweet\n"
                "- Better sourced, with at least one high-quality URL if possible\n"
                "- Neutral in tone and free of opinion language.\n"
                "Keep it concise enough to fit within 280 characters."
            ),
            rewrite_min_score=settings.default_rewrite_min_score,
            submit_min_score=settings.default_submit_min_score,
            max_notes_per_run=settings.max_notes_per_writer_per_run,
        )

        exploratory = WriterConfig(
            name="Grok Exploratory",
            description=(
                "More exploratory writer that takes swings on borderline notes "
                "to learn about thresholds."
            ),
            prompt=(
                "You are drafting a Community Note for this tweet:\n\n"
                "{tweet_text}\n\n"
                "Write a note that:\n"
                "- Identifies the main factual claim or implication\n"
                "- Provides context or counter-evidence from credible sources\n"
                "- Mentions limitations or uncertainty where appropriate\n"
                "- Stays neutral, focuses on what readers should know, and remains within a 280-character Community Note length."
            ),
            rewrite_prompt=None,
            rewrite_min_score=settings.default_rewrite_min_score,
            submit_min_score=max(settings.default_submit_min_score - 0.1, 0.5),
            max_notes_per_run=settings.max_notes_per_writer_per_run,
        )

        session.add_all([conservative, exploratory])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Community Notes AI Writer Lab"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create the SQLite DB and seed writers.")
    sub.add_parser("run-once", help="Run one lab cycle for all writers.")

    serve_parser = sub.add_parser(
        "serve", help="Run the FastAPI dashboard with Uvicorn."
    )
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind."
    )
    serve_parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind."
    )

    args = parser.parse_args(argv)

    if args.command == "init-db":
        init_db(with_example_writers=True)
    elif args.command == "run-once":
        run_lab_once()
    elif args.command == "serve":
        uvicorn.run(
            fastapi_app,
            host=args.host,
            port=args.port,
        )
    else:  # pragma: no cover - defensive
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover - convenience entrypoint
    main()
