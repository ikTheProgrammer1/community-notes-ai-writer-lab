from __future__ import annotations

from typing import Any, Dict, Optional

from xai_sdk import Client
from xai_sdk.chat import user, system

from .config import settings
from .models import Tweet, WriterConfig


class GrokClient:
    """
    Client for calling Grok / xAI using the official xai-sdk.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or settings.grok_api_key
        self.model = model or settings.grok_model or "grok-4-fast-reasoning"

        if not self.api_key:
            raise RuntimeError("GROK_API_KEY is required for GrokClient.")

        # Use official xAI SDK
        self._client = Client(
            api_key=self.api_key,
            timeout=60,  # 60 second timeout for reasoning models
        )

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        try:
            chat = self._client.chat.create(model=self.model)
            chat.append(system(system_prompt))
            chat.append(user(user_prompt))
            response = chat.sample()
            return response.content
        except Exception as exc:
            raise RuntimeError(f"Grok API Error: {exc}") from exc

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

    def generate_note_variants(self, tweet: Tweet) -> list[dict]:
        """
        Generates 3 variants of a note using different strategies.
        Returns a list of dicts: [{"strategy": "Neutral", "text": "..."}, ...]
        """
        from .prompts import NOTE_VARIANTS_PROMPT
        import json
        
        system_prompt = NOTE_VARIANTS_PROMPT
        user_prompt = f"Tweet Text: {tweet.text}"
        
        response = self._chat(system_prompt, user_prompt)
        
        # Parse JSON
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
            
        try:
            data = json.loads(cleaned.strip())
            return data.get("variants", [])
        except Exception:
            return []
