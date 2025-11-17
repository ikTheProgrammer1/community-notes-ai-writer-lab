from __future__ import annotations

import json
from typing import List

from .grok_client import GrokClient
from .models import Note, Tweet

MISLEADING_TAGS_ENUM: List[str] = [
    "disputed_claim_as_fact",
    "factual_error",
    "manipulated_media",
    "misinterpreted_satire",
    "missing_important_context",
    "other",
    "outdated_information",
]


def _default_tags() -> List[str]:
    """Fallback when we cannot confidently classify."""
    return ["missing_important_context"]


def _extract_json_object(text: str) -> str:
    """
    Best-effort extraction of a JSON object from an LLM response.

    We ask Grok to return pure JSON, but this makes the helper more robust to
    accidental prose or code fences.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        # Strip simple ```json ... ``` wrappers
        stripped = stripped.strip("`")
        # After stripping backticks, try again from the first brace.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return stripped
    return stripped[start : end + 1]


def choose_misleading_tags(tweet: Tweet, note: Note) -> List[str]:
    """
    LLM-based selector for /2/notes `info.misleading_tags`.

    Uses Grok to pick one or more enum values from MISLEADING_TAGS_ENUM based
    on the tweet + final note text. If anything goes wrong (API error, parse
    error, or empty/invalid tags), falls back to `["missing_important_context"]`.
    """
    try:
        client = GrokClient()
    except Exception:
        return _default_tags()

    allowed_list = ", ".join(MISLEADING_TAGS_ENUM)
    system_prompt = (
        "You are assisting a Community Notes contributor.\n"
        "Your task is to label why a tweet is misleading or incomplete, "
        "based on a Community Note that explains the issue.\n\n"
        "You MUST choose one or more reasons strictly from this enum list:\n"
        f"{allowed_list}\n\n"
        'Return ONLY a single JSON object of the form:\n'
        '{"misleading_tags": ["tag1", "tag2"]}\n'
        "Do not include any extra text, comments, or explanation."
    )

    user_prompt = (
        "Tweet text:\n"
        f"{tweet.text}\n\n"
        "Community Note:\n"
        f"{note.text}\n\n"
        "Pick the most appropriate misleading_tags values from the enum list."
    )

    try:
        raw = client._chat(system_prompt, user_prompt)
    except Exception:
        return _default_tags()

    try:
        json_text = _extract_json_object(raw)
        data = json.loads(json_text)
        tags = data.get("misleading_tags", [])
        if not isinstance(tags, list):
            return _default_tags()
        filtered = [t for t in tags if isinstance(t, str) and t in MISLEADING_TAGS_ENUM]
        return filtered or _default_tags()
    except Exception:
        return _default_tags()

