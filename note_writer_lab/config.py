import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# Load environment variables from a .env file at the project root
#
# This runs as soon as the config module is imported, so anything that
# instantiates Settings will see values from your .env (unless they are
# already set in the real environment, which take precedence).
project_root = Path(__file__).resolve().parents[1]
env_path = project_root / ".env"
load_dotenv(env_path, override=False)


def getenv_str(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value is not None else default


def getenv_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(slots=True)
class Settings:
    # SQLite database
    database_url: str = getenv_str(
        "LAB_DATABASE_URL", "sqlite:///./lab.sqlite3"
    )

    # X / Twitter Community Notes API
    # App / bearer token mode
    x_bearer_token: Optional[str] = getenv_str("X_BEARER_TOKEN")

    # OAuth1 user-context mode (preferred for Community Notes endpoints that
    # require a user token). All four must be present to use this mode:
    # - X_API_KEY
    # - X_API_SECRET
    # - X_ACCESS_TOKEN
    # - X_ACCESS_TOKEN_SECRET
    x_api_key: Optional[str] = getenv_str("X_API_KEY")
    x_api_secret: Optional[str] = getenv_str("X_API_SECRET")
    x_access_token: Optional[str] = getenv_str("X_ACCESS_TOKEN")
    x_access_token_secret: Optional[str] = getenv_str("X_ACCESS_TOKEN_SECRET")
    x_eligible_notes_url: Optional[str] = getenv_str(
        "X_COMMUNITY_NOTES_ELIGIBLE_URL"
    )
    x_submit_note_url: Optional[str] = getenv_str(
        "X_COMMUNITY_NOTES_SUBMIT_URL"
    )

    # Grok / xAI
    # Prefer GROK_API_KEY, but also accept XAI_API_KEY for compatibility.
    grok_api_key: Optional[str] = (
        getenv_str("GROK_API_KEY") or getenv_str("XAI_API_KEY")
    )
    grok_api_url: str = getenv_str(
        "GROK_API_URL",
        "https://api.x.ai/v1/chat/completions",
    )
    # Default to grok-4-fast-reasoning, but allow override via GROK_MODEL.
    grok_model: str = getenv_str("GROK_MODEL", "grok-4-fast-reasoning")

    # Lab behaviour
    max_notes_per_writer_per_run: int = getenv_int(
        "LAB_MAX_NOTES_PER_WRITER_PER_RUN", 5
    )
    # Minimum score at which we even consider submitting a note
    default_submit_min_score: float = float(
        getenv_str("LAB_DEFAULT_SUBMIT_MIN_SCORE", "0.75")  # type: ignore[arg-type]
    )
    # Minimum score at which we are willing to spend a rewrite on a weak note
    default_rewrite_min_score: float = float(
        getenv_str("LAB_DEFAULT_REWRITE_MIN_SCORE", "0.4")  # type: ignore[arg-type]
    )


settings = Settings()
