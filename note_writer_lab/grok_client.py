from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .config import settings
from .models import Tweet, WriterConfig


class GrokClient:
    """
    Minimal client for calling Grok / xAI.

    The default payload is compatible with OpenAI-style chat completions APIs.
    Adjust GROK_API_URL / GROK_MODEL or the payload shape as needed.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or settings.grok_api_key
        self.api_url = api_url or settings.grok_api_url
        self.model = model or settings.grok_model

        if not self.api_key:
            raise RuntimeError("GROK_API_KEY is required for GrokClient.")

        # Use a plain client and always POST to the full api_url so we match
        # the curl example exactly (no extra trailing slash, etc.).
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        response = self._client.post(self.api_url, json=payload)
        response.raise_for_status()
        data = response.json()

        # OpenAI-style response shape
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Unexpected Grok response: {data}") from exc

    def build_note_prompt(self, tweet: Tweet, writer: WriterConfig) -> str:
        return writer.prompt.format(
            tweet_text=tweet.text,
            tweet_id=tweet.tweet_id,
            author_handle=tweet.author_handle or "",
        )

    def build_rewrite_prompt(
        self,
        tweet: Tweet,
        writer: WriterConfig,
        current_note: str,
        weakness_summary: str,
    ) -> str:
        if writer.rewrite_prompt:
            return writer.rewrite_prompt.format(
                tweet_text=tweet.text,
                tweet_id=tweet.tweet_id,
                author_handle=tweet.author_handle or "",
                current_note=current_note,
                weakness_summary=weakness_summary,
            )

        # Simple fallback rewrite prompt
        return (
            "You are a careful Community Notes contributor. "
            "Rewrite the note to be more neutral, grounded in verifiable facts, "
            "and aligned with Community Notes guidelines.\n\n"
            f"Original Community Note draft:\n{current_note}\n\n"
            f"Tweet:\n{tweet.text}\n\n"
            f"Weaknesses to fix:\n{weakness_summary}"
        )

    def generate_note(self, tweet: Tweet, writer: WriterConfig) -> str:
        system_prompt = (
            "You are an expert Community Notes contributor. "
            "You write concise, neutral, well-sourced notes that help readers "
            "better understand context and verify claims. "
            "Your response must be a single paragraph of plain English text with "
            "no markdown, no headings or titles, no bullet points, and no code blocks."
        )
        user_prompt = self.build_note_prompt(tweet, writer)
        return self._chat(system_prompt, user_prompt).strip()

    def rewrite_note(
        self,
        tweet: Tweet,
        writer: WriterConfig,
        current_note: str,
        weakness_summary: str,
    ) -> str:
        system_prompt = (
            "You are an expert Community Notes editor. "
            "Your job is to improve an existing note while preserving factual accuracy. "
            "Your response must be a single paragraph of plain English text with "
            "no markdown, no headings or titles, no bullet points, and no code blocks."
        )
        user_prompt = self.build_rewrite_prompt(
            tweet=tweet,
            writer=writer,
            current_note=current_note,
            weakness_summary=weakness_summary,
        )
        return self._chat(system_prompt, user_prompt).strip()
