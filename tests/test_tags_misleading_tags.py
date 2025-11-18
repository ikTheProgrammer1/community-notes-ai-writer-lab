from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from note_writer_lab import tags


class DummyTweet(SimpleNamespace):
    pass


class DummyNote(SimpleNamespace):
    pass


def test_choose_misleading_tags_uses_llm_and_filters(monkeypatch: Any) -> None:
    """LLM returns valid + invalid tags; function should filter to enum."""

    class DummyGrokClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def _chat(self, system_prompt: str, user_prompt: str) -> str:
            # Contains 2 valid tags and 1 invalid one.
            return '{"misleading_tags": ["factual_error", "other", "not_a_real_tag"]}'

    monkeypatch.setattr(tags, "GrokClient", DummyGrokClient)

    tweet = DummyTweet(text="Some misleading tweet text")
    note = DummyNote(text="A note explaining why this is factually wrong, with sources.")

    result = tags.choose_misleading_tags(tweet=tweet, note=note)

    # Only the valid enum values should survive.
    assert set(result) == {"factual_error", "other"}


def test_choose_misleading_tags_falls_back_on_bad_json(monkeypatch: Any) -> None:
    """If LLM returns non-JSON, we fall back to the default tag."""

    class DummyGrokClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def _chat(self, system_prompt: str, user_prompt: str) -> str:
            return "this is not json at all"

    monkeypatch.setattr(tags, "GrokClient", DummyGrokClient)

    tweet = DummyTweet(text="Some tweet")
    note = DummyNote(text="Some note")

    result = tags.choose_misleading_tags(tweet=tweet, note=note)
    assert result == ["missing_important_context"]


def test_choose_misleading_tags_falls_back_when_client_fails(monkeypatch: Any) -> None:
    """If GrokClient cannot be constructed, we fall back safely."""

    class FailingGrokClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(tags, "GrokClient", FailingGrokClient)

    tweet = DummyTweet(text="Some tweet")
    note = DummyNote(text="Some note")

    result = tags.choose_misleading_tags(tweet=tweet, note=note)
    assert result == ["missing_important_context"]

