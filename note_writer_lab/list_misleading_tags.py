from __future__ import annotations

"""
Quick helper to probe the /2/notes API for the allowed
`info.misleading_tags` enum values.

It sends an intentionally invalid tag and then tries to parse the error
message, which (for other enums) includes an
`enumeration [value_a, value_b, ...]` fragment.

Usage (from repo root, with env vars set and a known-eligible tweet id):

    python -m note_writer_lab.list_misleading_tags <tweet_id>
"""

from typing import List

import json
import sys

import requests
from requests_oauthlib import OAuth1

from .config import settings


def _build_oauth1() -> OAuth1:
    if not (
        settings.x_api_key
        and settings.x_api_secret
        and settings.x_access_token
        and settings.x_access_token_secret
    ):
        raise RuntimeError(
            "OAuth1 credentials are required: set X_API_KEY, X_API_SECRET, "
            "X_ACCESS_TOKEN, and X_ACCESS_TOKEN_SECRET."
        )

    return OAuth1(
        settings.x_api_key,
        settings.x_api_secret,
        settings.x_access_token,
        settings.x_access_token_secret,
    )


def _extract_enum_values(error_payload: dict) -> List[str]:
    """
    Search error messages for fragments like:
      'enumeration [missing_important_context, ...]'
    and return the values as a list.
    """
    values: set[str] = set()

    def scan_text(text: str) -> None:
        marker = "enumeration ["
        idx = text.find(marker)
        if idx == -1:
            return
        start = idx + len(marker)
        end = text.find("]", start)
        if end == -1:
            return
        inner = text[start:end]
        for part in inner.split(","):
            val = part.strip().strip('"').strip("'")
            if val:
                values.add(val)

    for err in error_payload.get("errors", []):
        msg = str(err.get("message", ""))
        if msg:
            scan_text(msg)
        detail = str(err.get("detail", ""))
        if detail:
            scan_text(detail)

    # Also scan top-level detail/title just in case
    top_detail = str(error_payload.get("detail", ""))
    if top_detail:
        scan_text(top_detail)

    return sorted(values)


def fetch_misleading_tags_enum(tweet_id: str) -> None:
    if not settings.x_submit_note_url:
        raise RuntimeError(
            "X_COMMUNITY_NOTES_SUBMIT_URL is not set; cannot call /2/notes."
        )

    auth = _build_oauth1()

    payload = {
        "info": {
            "classification": "misinformed_or_potentially_misleading",
            # Intentionally invalid tag to trigger an enum error.
            "misleading_tags": ["totally_invalid_misleading_tag_enum_value"],
            "text": "Test note for misleading_tags https://example.com",
            "trustworthy_sources": True,
        },
        "post_id": tweet_id,
        "test_mode": True,
    }

    resp = requests.post(
        settings.x_submit_note_url,
        json=payload,
        auth=auth,
        timeout=30,
    )

    print("HTTP status:", resp.status_code)
    try:
        data = resp.json()
    except Exception:
        print("Non-JSON response body:")
        print(resp.text)
        return

    print("Raw error payload:")
    print(json.dumps(data, indent=2))

    enum_values = _extract_enum_values(data)
    if enum_values:
        print("\nParsed misleading_tags enum values:")
        for v in enum_values:
            print("-", v)
    else:
        print("\nNo enumeration[] fragment found in error; "
              "the API may not be exposing the enum here.")


def main(argv: list[str] | None = None) -> None:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python -m note_writer_lab.list_misleading_tags <tweet_id>")
        raise SystemExit(1)

    tweet_id = args[0].strip()
    fetch_misleading_tags_enum(tweet_id)


if __name__ == "__main__":
    main()

