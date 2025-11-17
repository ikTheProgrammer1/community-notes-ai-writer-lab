from __future__ import annotations

from typing import Any, Dict, List, Optional

import os
import re
import requests
from requests_oauthlib import OAuth1

from .config import settings
from .evaluator import URL_REGEX


NOTE_TEXT_URL_PATTERN = re.compile(r"https?://\S+")


class XClient:
    """
    Thin wrapper around X's official APIs.

    Supports two auth modes:
    - OAuth1 user-context (preferred for Community Notes endpoints):
      uses X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET.
    - Bearer token (app-only) using X_BEARER_TOKEN.

    URLs are configurable via:
    - X_COMMUNITY_NOTES_ELIGIBLE_URL
    - X_COMMUNITY_NOTES_SUBMIT_URL
    """

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        eligible_url: Optional[str] = None,
        submit_url: Optional[str] = None,
    ) -> None:
        self.eligible_url = eligible_url or settings.x_eligible_notes_url
        self.submit_url = submit_url or settings.x_submit_note_url

        if not self.eligible_url or not self.submit_url:
            raise RuntimeError(
                "Both X_COMMUNITY_NOTES_ELIGIBLE_URL and "
                "X_COMMUNITY_NOTES_SUBMIT_URL must be set."
            )

        # Auth configuration
        has_oauth1_creds = (
            settings.x_api_key
            and settings.x_api_secret
            and settings.x_access_token
            and settings.x_access_token_secret
        )
        self._bearer_token: Optional[str] = bearer_token or settings.x_bearer_token

        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

        # Per Community Notes docs:
        # - GET /2/notes/search/posts_eligible_for_notes → OAuth1 user-context
        # - POST /2/notes → OAuth2 bearer (Authorization: Bearer <token>)
        #
        # So we maintain both where possible.
        self._oauth1_auth: Optional[OAuth1] = None
        if has_oauth1_creds:
            self._oauth1_auth = OAuth1(
                settings.x_api_key,
                settings.x_api_secret,
                settings.x_access_token,
                settings.x_access_token_secret,
            )

        if not self._oauth1_auth and not self._bearer_token:
            raise RuntimeError(
                "X credentials missing: provide OAuth1 user tokens "
                "(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, "
                "X_ACCESS_TOKEN_SECRET) and/or set X_BEARER_TOKEN."
            )

        # Optional debugging flag: when LAB_DEBUG_NOTE_TEXT=1, we will print
        # the normalized and final note text before submitting.
        self._debug_note_text = os.getenv("LAB_DEBUG_NOTE_TEXT") == "1"

    @staticmethod
    def _looks_simple_note(text: str) -> bool:
        """
        Heuristic: returns True when the note text already looks like a
        single-paragraph, plain sentence without obvious markdown or
        structural formatting.
        """
        if "\n" in text:
            return False

        lowered = text.lower()
        noisy_markers = [
            "claim:",
            "summary:",
            "context:",
            "tweet:",
            "sources:",
            "- ",
            "* ",
            "• ",
        ]
        return not any(marker in lowered for marker in noisy_markers)

    @staticmethod
    def _normalize_note_text(raw: str) -> str:
        """
        Best-effort normalizer to convert multi-line, markdown-like Grok
        output into a single plain paragraph that better matches typical
        Community Notes style:

        - Strip markdown headings like "Claim:" or "Summary:".
        - Remove bullet markers ("- ", "* ", numbered lists) while keeping content.
        - Collapse whitespace and newlines into single spaces.
        """
        # Fast path: already looks simple.
        if XClient._looks_simple_note(raw):
            return raw.strip()

        lines = raw.splitlines()
        cleaned_parts: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Skip code fences entirely.
            if stripped.startswith("```"):
                continue

            # Handle markdown-style headings, e.g. "### Claim" or "# Context".
            if stripped.startswith("#"):
                heading_body = stripped.lstrip("#").strip().lower()
                for heading in (
                    "claim",
                    "summary",
                    "context",
                    "tweet",
                    "note",
                    "analysis",
                    "sources",
                ):
                    if heading_body.startswith(heading):
                        # Pure heading line → skip it.
                        stripped = ""
                        break
                if not stripped:
                    continue

            lower = stripped.lower()

            # Remove common heading prefixes but keep the rest of the line so
            # we don't accidentally drop URLs or useful context.
            for heading in ("claim:", "summary:", "context:", "tweet:", "note:", "analysis:"):
                if lower.startswith(heading):
                    stripped = stripped[len(heading) :].lstrip(" -:")
                    lower = stripped.lower()
                    break

            if not stripped:
                continue

            # Strip markdown bullets like "- text", "* text", "• text".
            if stripped[0] in "-*•" and len(stripped) > 1 and stripped[1] == " ":
                stripped = stripped[2:].lstrip()

            # Strip simple numbered list prefixes like "1. text".
            if len(stripped) > 3 and stripped[0].isdigit() and stripped[1:3] == ". ":
                stripped = stripped[3:].lstrip()

            if stripped:
                cleaned_parts.append(stripped)

        # Collapse all remaining content into a single paragraph.
        text = " ".join(cleaned_parts).strip()

        # Simplify markdown links of the form [label](https://example.com)
        # into "label (https://example.com)" so we keep URLs but avoid
        # markdown-specific syntax that the API might reject.
        text = re.sub(
            r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
            r"\1 (\2)",
            text,
        )

        return text

    @staticmethod
    def _validate_note_text_for_submission(text: str) -> bool:
        """
        Final guardrail to ensure the note text we send to /2/notes matches
        the simple, API-friendly contract:

        - 1–280 characters.
        - Single paragraph (no newlines).
        - Contains at least one https?:// URL.
        - No obvious markdown markers like headings or link syntax.
        """
        stripped = text.strip()
        if not stripped or len(stripped) > 280:
            return False
        if "\n" in stripped:
            return False
        if NOTE_TEXT_URL_PATTERN.search(stripped) is None:
            return False

        # Reject very obvious markdown / heading prefixes.
        leading = stripped.lstrip()
        if leading.startswith("#") or leading.startswith("*") or leading.startswith("- "):
            return False

        # Reject leftover markdown link syntax like [label](url).
        if re.search(r"\[[^\]]+\]\(", stripped):
            return False

        return True

    def fetch_eligible_tweets(self, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch posts that are currently eligible for Community Notes.

        The exact response shape depends on the underlying endpoint you configure.
        This method returns a list of raw tweet objects (dicts).
        """
        params = {
            "max_results": max_results,
            # Community Notes docs require test_mode=true for the
            # posts_eligible_for_notes search endpoint.
            "test_mode": "true",
        }

        if not self._oauth1_auth:
            raise RuntimeError(
                "OAuth1 credentials are required for posts_eligible_for_notes. "
                "Set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, and "
                "X_ACCESS_TOKEN_SECRET."
            )

        response = self._session.get(
            self.eligible_url,
            params=params,
            auth=self._oauth1_auth,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Assume a top-level "data" list; let callers adapt if their shape differs.
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    def submit_note(
        self,
        tweet_id: str,
        note_text: str,
        test_mode: bool = True,
        writer_name: Optional[str] = None,
        misleading_tags: Optional[List[str]] = None,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Submit a Community Note in test_mode.

        The payload is shaped to match the Community Notes API schema:

        {
          "info": {
            "classification": "<enum>",
            "misleading_tags": ["<enum>", ...],
            "text": "<note>",
            "trustworthy_sources": true|false
          },
          "post_id": "<tweet id>",
          "test_mode": true|false
        }
        """
        if not self._oauth1_auth:
            raise RuntimeError(
                "OAuth1 user-context credentials are required for submitting "
                "notes to /2/notes. Set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, "
                "and X_ACCESS_TOKEN_SECRET."
            )

        # Very simple heuristics for required fields:
        # - classification: assume a generic 'MISLEADING' classification
        # - misleading_tags: non-empty list; default to a safe enum value
        # - trustworthy_sources: true if we see at least one HTTP(S) URL
        normalized_text = self._normalize_note_text(note_text)
        has_url = "http://" in normalized_text or "https://" in normalized_text

        # Enforce rough length constraints from the API:
        # "Note should contain at least 1 and at most 280 characters
        #  (urls count as a single character)".
        text = normalized_text.strip()
        if len(text) > 280:
            if has_url:
                match = URL_REGEX.search(text)
                if match:
                    start = max(0, match.start() - 200)
                    text = text[start : start + 280]
                else:
                    text = text[:280]
            else:
                text = text[:280]

        if self._debug_note_text:
            print(
                "[XClient] Normalized note text:",
                normalized_text.replace("\n", "\\n"),
            )
            print("[XClient] Final note text:", text)

        # Enforce the final output contract; if the text still does not meet
        # basic rules, fail fast rather than sending an invalid payload.
        if not self._validate_note_text_for_submission(text):
            raise ValueError(
                "Normalized note text failed validation for /2/notes submission."
            )

        # If the caller supplied tags, filter out empties; otherwise fall back
        # to a safe, known-good default that the API accepts.
        effective_tags: List[str] = (
            [tag for tag in (misleading_tags or []) if tag]
            or ["missing_important_context"]
        )

        info: Dict[str, Any] = {
            # Community Notes API docs list the classification enum as:
            # [misinformed_or_potentially_misleading, not_misleading].
            # For this lab we assume we're targeting misinformed/potentially
            # misleading content by default.
            "classification": "misinformed_or_potentially_misleading",
            # The API rejects an empty misleading_tags list for this
            # classification. Use a safe, generic tag that matches the
            # official enum and works in practice by default, but allow
            # callers to override when they know a more specific tag.
            "misleading_tags": effective_tags,
            "text": text,
            "trustworthy_sources": bool(has_url),
        }

        payload: Dict[str, Any] = {
            "info": info,
            "post_id": tweet_id,
            "test_mode": bool(test_mode),
        }

        if extra_payload:
            payload.update(extra_payload)

        response = self._session.post(
            self.submit_url,
            json=payload,
            auth=self._oauth1_auth,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
