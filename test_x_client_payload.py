from __future__ import annotations

from typing import Any, Dict

from note_writer_lab.x_client import XClient


class DummyResponse:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:  # pragma: no cover - trivial
        return

    def json(self) -> Dict[str, Any]:
        return self._payload


def make_test_client(captured: Dict[str, Any]) -> XClient:
    """
    Build an XClient instance whose HTTP calls are captured instead of
    hitting the real network.
    """
    client = XClient(
        bearer_token="TEST",
        eligible_url="https://example.com/eligible",
        submit_url="https://example.com/notes",
    )

    # Avoid needing real OAuth credentials for tests.
    client._oauth1_auth = object()  # type: ignore[assignment]

    class DummySession:
        def __init__(self, sink: Dict[str, Any]) -> None:
            self.sink = sink

        def post(
            self,
            url: str,
            json: Dict[str, Any] | None = None,  # type: ignore[override]
            auth: Any | None = None,
            timeout: float | int | None = None,
        ) -> DummyResponse:
            self.sink["url"] = url
            self.sink["json"] = json
            self.sink["auth"] = auth
            self.sink["timeout"] = timeout
            return DummyResponse({"ok": True})

    client._session = DummySession(captured)  # type: ignore[assignment]
    return client


def test_submit_note_uses_provided_tags_and_schema() -> None:
    captured: Dict[str, Any] = {}
    client = make_test_client(captured)

    client.submit_note(
        tweet_id="123",
        note_text="This is a test note with a URL https://example.com",
        test_mode=True,
        writer_name="Writer",
        misleading_tags=["factual_error"],
    )

    payload = captured["json"]
    info = payload["info"]

    assert payload["post_id"] == "123"
    assert payload["test_mode"] is True
    assert info["classification"] == "misinformed_or_potentially_misleading"
    assert info["misleading_tags"] == ["factual_error"]
    assert "https://example.com" in info["text"]
    assert info["trustworthy_sources"] is True
    assert 1 <= len(info["text"]) <= 280


def test_submit_note_defaults_tags_when_none_provided() -> None:
    captured: Dict[str, Any] = {}
    client = make_test_client(captured)

    client.submit_note(
        tweet_id="123",
        note_text="Note with URL https://example.com",
        test_mode=True,
        writer_name="Writer",
    )

    payload = captured["json"]
    info = payload["info"]

    assert info["misleading_tags"] == ["missing_important_context"]


def test_submit_note_truncates_long_text_but_keeps_url() -> None:
    # Build a note that is definitely longer than 280 characters.
    long_prefix = "A" * 400
    note_text = f"{long_prefix} https://example.com extra text that may be trimmed."

    captured: Dict[str, Any] = {}
    client = make_test_client(captured)

    client.submit_note(
        tweet_id="123",
        note_text=note_text,
        test_mode=True,
        writer_name="Writer",
        misleading_tags=["other"],
    )

    text = captured["json"]["info"]["text"]
    assert len(text) <= 280
    assert "https://example.com" in text


def test_normalize_note_text_strips_headings_and_markdown_links() -> None:
    raw = """### Claim
The tweet implies that something is true.

### Sources
- [Source Name](https://example.com/source)
"""

    # Use the static normalizer directly.
    normalized = XClient._normalize_note_text(raw)

    # Heading markers like "### Claim"/"### Sources" should be gone.
    assert "### Claim" not in normalized
    assert "### Sources" not in normalized

    # Core sentence and URL should remain.
    assert "The tweet implies that something is true." in normalized
    assert "https://example.com/source" in normalized

    # Markdown link syntax should be simplified (no "[" or "](" combos).
    assert "[" not in normalized
    assert "](" not in normalized


def test_validate_note_text_accepts_simple_paragraph() -> None:
    text = (
        "This tweet is missing important context; "
        "see https://example.com for background."
    )
    assert XClient._validate_note_text_for_submission(text) is True


def test_validate_note_text_rejects_invalid_formats() -> None:
    # Missing URL
    assert (
        XClient._validate_note_text_for_submission(
            "This note has no URL at all."
        )
        is False
    )

    # Newline → multiple paragraphs
    assert (
        XClient._validate_note_text_for_submission(
            "First line https://example.com\nSecond line"
        )
        is False
    )

    # Markdown heading
    assert (
        XClient._validate_note_text_for_submission(
            "# Heading https://example.com"
        )
        is False
    )

    # Bullet-style prefix
    assert (
        XClient._validate_note_text_for_submission(
            "- Bullet text https://example.com"
        )
        is False
    )

    # Markdown link syntax
    assert (
        XClient._validate_note_text_for_submission(
            "See [source](https://example.com) for details."
        )
        is False
    )

    # Overly long text
    long_text = "A" * 300 + " https://example.com"
    assert XClient._validate_note_text_for_submission(long_text) is False
