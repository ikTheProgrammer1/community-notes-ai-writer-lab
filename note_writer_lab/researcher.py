import logging
import json
from typing import List, Dict, Any, Optional
import requests
from note_writer_lab.grok_client import GrokClient
from note_writer_lab.prompts import CLAIMS_EXTRACTION_PROMPT, FIXER_RESEARCHER_PROMPT

logger = logging.getLogger(__name__)

class GroundingClient:
    def __init__(self, grok_client: GrokClient):
        self.grok = grok_client

    def extract_claims(self, note_text: str) -> List[str]:
        """
        Uses Grok to extract verifiable claims from the note text.
        """
        try:
            response = self.grok._chat(
                system_prompt=CLAIMS_EXTRACTION_PROMPT,
                user_prompt=f"Note Text: {note_text}"
            )
            # Parse JSON response
            # Expected format: {"claims": ["claim 1", "claim 2"]}
            # We need to handle potential markdown code blocks if Grok adds them
            cleaned_response = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned_response)
            return data.get("claims", [])
        except Exception as e:
            logger.error(f"Error extracting claims: {e}")
            return []

    def verify_url(self, url: str) -> bool:
        """
        Checks if a URL is reachable and returns a 200 OK status.
        Simple check for dead links.
        """
        try:
            # Set a user agent to avoid being blocked by some sites
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; BridgeRankBot/1.0; +http://example.com)"
            }
            response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                return True
            # Fallback to GET if HEAD fails (some servers block HEAD)
            response = requests.get(url, headers=headers, timeout=5, stream=True)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"URL verification failed for {url}: {e}")
            return False

    def find_evidence(self, claim: str) -> List[Dict[str, str]]:
        """
        Mock implementation for finding evidence.
        In a real production system, this would call Tavily or Google Search API.
        """
        # Mock response for stability during hackathon
        return [
            {
                "title": f"Evidence for: {claim[:20]}...",
                "url": "https://example.com/evidence",
                "snippet": "This is a mock snippet supporting the claim."
            },
            {
                "title": "Another Source",
                "url": "https://wikipedia.org",
                "snippet": "Wikipedia entry related to the topic."
            }
        ]

    def find_better_url(self, note_text: str) -> Optional[str]:
        """
        Uses Grok (Researcher Persona) to find a better URL for the note.
        """
        try:
            response = self.grok._chat(
                system_prompt=FIXER_RESEARCHER_PROMPT,
                user_prompt=f"Note Text: {note_text}"
            )
            cleaned = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            return data.get("found_url")
        except Exception as e:
            logger.error(f"Error finding better URL: {e}")
            return None
