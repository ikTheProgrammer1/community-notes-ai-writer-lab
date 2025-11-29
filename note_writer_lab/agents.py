import os
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from .rag_engine import RAGEngine

logger = logging.getLogger(__name__)

class ResearcherAgent:
    def __init__(self):
        self.api_key = os.getenv("GROK_API_KEY")
        self.base_url = "https://api.x.ai/v1"
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.model = "grok-4" # Updated to grok-4 per user request

    def find_sources(self, claim: str) -> List[str]:
        """
        Uses Grok to find URLs that support or refute a claim.
        """
        if not claim:
            return []

        system_prompt = """
        You are an expert researcher for Community Notes. 
        Your goal is to find 1-2 high-quality, reliable URLs that provide context for the given claim.
        Return ONLY the URLs, one per line. Do not add conversational text.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Find sources for this claim: {claim}"}
                ],
                temperature=0.3
            )
            content = response.choices[0].message.content
            urls = [line.strip() for line in content.splitlines() if line.startswith("http")]
            return urls
        except Exception as e:
            logger.error(f"ResearcherAgent Error: {e}")
            return []

class FixerAgent:
    def __init__(self):
        self.api_key = os.getenv("GROK_API_KEY")
        self.base_url = "https://api.x.ai/v1"
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.model = "grok-4"
        self.rag = RAGEngine()

    def fix_note(self, draft: str, critique: str = "") -> str:
        """
        Rewrites a draft note to be more helpful, using RAG for style and tone.
        """
        # 1. Get RAG Context
        similar_notes = self.rag.find_similar_notes(draft, n_results=3)
        examples = "\n\n".join([f"Example {i+1}:\n{n['note_text']}" for i, n in enumerate(similar_notes)])

        system_prompt = f"""
        You are a Community Notes Editor. Your goal is to rewrite the user's draft to make it "Helpful".
        
        GUIDELINES:
        - Neutral, objective tone.
        - No snark or partisan language.
        - Cite sources if provided (or placeholders if not).
        - Clear and concise.
        
        LEARN FROM THESE SUCCESSFUL EXAMPLES:
        {examples}
        
        CRITIQUE TO ADDRESS:
        {critique}
        
        Return ONLY the rewritten note text.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Draft: {draft}"}
                ],
                temperature=0.4
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"FixerAgent Error: {e}")
            return draft # Return original on error
