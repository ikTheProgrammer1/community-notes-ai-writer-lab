from __future__ import annotations

from typing import Any, Dict, List, Optional

import os
import re
import logging
import requests
from requests_oauthlib import OAuth1

from .config import settings
from .evaluator import URL_REGEX

logger = logging.getLogger(__name__)


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

    def search_tweets(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for recent tweets matching a query.
        Uses the /2/tweets/search/recent endpoint.
        """
        url = "https://api.twitter.com/2/tweets/search/recent"
        
        # Build query: exclude retweets and replies to get original content
        # Also ensure we get metrics and author info
        safe_query = f"{query} -is:retweet -is:reply lang:en"
        
        params = {
            "query": safe_query,
            "max_results": max_results,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "username,name,verified"
        }
        
        try:
            # Prefer Bearer token for search if available
            auth = None
            headers = {}
            if self._bearer_token:
                headers["Authorization"] = f"Bearer {self._bearer_token}"
            elif self._oauth1_auth:
                auth = self._oauth1_auth
            else:
                raise RuntimeError("No credentials for search.")

            response = self._session.get(url, params=params, auth=auth, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                tweets = data.get("data", [])
                includes = data.get("includes", {})
                users = {u["id"]: u for u in includes.get("users", [])}
                
                # Enrich tweets with user info
                enriched_tweets = []
                for t in tweets:
                    author_id = t.get("author_id")
                    if author_id and author_id in users:
                        t["author"] = users[author_id]
                    enriched_tweets.append(t)
                    
                return enriched_tweets
            else:
                logger.warning(f"Search failed: {response.status_code} {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error searching tweets: {e}")
            return []

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

    @staticmethod
    def parse_admission_scores(api_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses the raw API response from a test_mode submission to extract
        admission-relevant scores.
        """
        # Default safe values
        scores = {
            "url_validity_score": 0.0,
            "claim_opinion_score": 0.0,
            "harassment_abuse_score": 0.0,
            "api_feedback_raw": api_response
        }

        # Try to extract from likely paths (adjust based on actual API response)
        # Path 1: Root level keys (common in some endpoints)
        if "url_validity_score" in api_response:
            scores["url_validity_score"] = float(api_response.get("url_validity_score", 0.0))
        
        if "claim_opinion_score" in api_response:
            scores["claim_opinion_score"] = float(api_response.get("claim_opinion_score", 0.0))

        if "harassment_abuse_score" in api_response:
            scores["harassment_abuse_score"] = float(api_response.get("harassment_abuse_score", 0.0))

        # Path 2: Nested in 'note_evaluation' or similar
        eval_data = api_response.get("note_evaluation", {}) or api_response.get("evaluation", {})
        if eval_data:
            if "urlValidity" in eval_data:
                 scores["url_validity_score"] = float(eval_data.get("urlValidity", 0.0))
            if "claimOpinion" in eval_data:
                 scores["claim_opinion_score"] = float(eval_data.get("claimOpinion", 0.0))
            if "harassmentAbuse" in eval_data:
                 scores["harassment_abuse_score"] = float(eval_data.get("harassmentAbuse", 0.0))

        return scores

    @staticmethod
    def extract_tweet_id(url: str) -> Optional[str]:
        """
        Extracts the Tweet ID from a standard X/Twitter URL.
        Supports:
        - https://x.com/user/status/123456789
        - https://twitter.com/user/status/123456789
        """
        match = re.search(r"status/(\d+)", url)
        if match:
            return match.group(1)
        return None

    def fetch_tweet_text(self, tweet_id: str) -> Optional[str]:
        """
        Fetches the text of a tweet by its ID.
        """
        if not self._oauth1_auth and not self._bearer_token:
             logger.warning("No credentials for fetching tweet text.")
             return None
             
        url = f"https://api.twitter.com/2/tweets/{tweet_id}"
        params = {"tweet.fields": "text"}
        
        try:
            # Prefer Bearer token for read-only if available, else OAuth1
            auth = None
            headers = {}
            if self._bearer_token:
                headers["Authorization"] = f"Bearer {self._bearer_token}"
            elif self._oauth1_auth:
                auth = self._oauth1_auth
                
            response = self._session.get(url, params=params, auth=auth, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("text")
            else:
                logger.warning(f"Failed to fetch tweet {tweet_id}: {response.status_code} {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error fetching tweet {tweet_id}: {e}")
            return None

    def evaluate_note(self, tweet_id: str, note_text: str) -> Dict[str, Any]:
        """
        Calls the official evaluate_note endpoint (Practice Mode).
        """
        # Note: The actual endpoint URL might vary. We'll assume a standard one or use a configured one.
        # For this lab, we might need to assume it's available or mock it if strictly not present.
        # The user said "evaluate_note API endpoint". We'll assume it's at /2/notes/evaluate or similar.
        # If not configured, we'll try to use the submit_url base but change the endpoint.
        # User-specified configuration:
        # URL: https://api.x.com/2/evaluate_note
        # Auth: Bearer Token (X_BEARER_TOKEN)
        self._bearer_token = os.getenv("X_BEARER_TOKEN") or os.getenv("X_API_BEARER_TOKEN")
        # Payload: {"note_text": ..., "post_id": ...}

        # 1) Explicit override
        configured_url = getattr(settings, "x_evaluate_note_url", None)

        ordered_candidates = [
            "https://api.x.com/2/evaluate_note",
            "https://api.twitter.com/2/evaluate_note"
        ]
        
        # Add others as fallback
        if configured_url:
            ordered_candidates.append(configured_url.rstrip("/"))
            
        # Payload as specified
        payload = {
            "note_text": note_text,
            "post_id": tweet_id,
        }

        # Build auth attempts: try bearer first (as per docs), then OAuth1 if present.
        auth_attempts: list[dict[str, Any]] = []
        if self._bearer_token:
            auth_attempts.append({"auth": None, "headers": {"Authorization": f"Bearer {self._bearer_token}"}, "label": "bearer"})
        if self._oauth1_auth:
            auth_attempts.append({"auth": self._oauth1_auth, "headers": {}, "label": "oauth1"})
        
        if not auth_attempts:
             raise RuntimeError("X credentials required for evaluate_note (Bearer or OAuth1).")

        errors: list[str] = []
        for evaluate_url in ordered_candidates:
            try:
                for attempt in auth_attempts:
                    response = self._session.post(
                        evaluate_url,
                        json=payload,
                        auth=attempt["auth"],
                        headers=attempt["headers"],
                        timeout=30
                    )
                    if response.status_code == 404:
                        # Try next endpoint; 404 is often a product/host mismatch.
                        errors.append(f"{evaluate_url} ({attempt['label']}) → 404")
                        break
                    if response.status_code in (401, 403) and attempt is not auth_attempts[-1]:
                        # Try the next auth mode before failing the endpoint.
                        errors.append(f"{evaluate_url} ({attempt['label']}) → {response.status_code}")
                        continue
                    response.raise_for_status()
                    return response.json()
            except requests.HTTPError:
                # For non-404 errors, bail out immediately to surface the real failure.
                raise
            except Exception as e:  # pragma: no cover - defensive network handling
                errors.append(f"{evaluate_url} → {e}")
                continue

        raise requests.HTTPError(
            f"All evaluate_note endpoints failed. Tried: {', '.join(errors) or 'none'}"
        )
