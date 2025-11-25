import json
import logging
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from .grok_client import GrokClient
from .x_client import XClient
from .researcher import GroundingClient
from .models import Note
from .prompts import FIXER_EDITOR_PROMPT

logger = logging.getLogger(__name__)

class AdmissionEngine:
    def __init__(self, db: Session, grok_client: Optional[GrokClient] = None, x_client: Optional[XClient] = None):
        self.db = db
        self.grok = grok_client or GrokClient()
        self.x_client = x_client or XClient()
        self.researcher = GroundingClient(self.grok)

    def run_practice(self, note: Note, tweet_id: str) -> Dict[str, Any]:
        """
        Practice Mode: Calls evaluate_note to grade the draft without submitting.
        Falls back to Grok simulation if official API fails.
        """
        logger.info(f"Running Practice Mode for note {note.id}...")
        
        scores = {}
        used_fallback = False
        error_msg = None
        
        try:
            # Try Official API first
            response = self.x_client.evaluate_note(
                tweet_id=tweet_id,
                note_text=note.text
            )
            eval_data = response.get("noteContent", {})
            scores["claim_opinion_score"] = float(eval_data.get("claimOpinionScore", 0.0))
            
        except Exception as e:
            logger.warning(f"Official evaluate_note failed ({e}), falling back to Grok simulation.")
            used_fallback = True
            error_msg = str(e)
            
            # Fallback: Use Grok to estimate score
            try:
                # Need tweet text for context
                tweet_text = self.x_client.fetch_tweet_text(tweet_id) or "Tweet text unavailable"
                
                from .prompts import EVALUATOR_PROMPT
                response = self.grok._chat(
                    system_prompt=EVALUATOR_PROMPT,
                    user_prompt=f"Tweet: {tweet_text}\nNote: {note.text}"
                )
                cleaned = response.replace("```json", "").replace("```", "").strip()
                data = json.loads(cleaned)
                scores["claim_opinion_score"] = float(data.get("claimOpinionScore", 0.5))
                
            except Exception as e2:
                logger.error(f"Fallback simulation also failed: {e2}")
                return {
                    "mode": "practice",
                    "passed": False,
                    "failure_reasons": ["System Error"],
                    "error": f"API Error: {error_msg}. Simulation Error: {e2}",
                    "scores": {}
                }

        # Determine Status (same logic)
        passed = True
        failure_reasons = []
        
        if scores.get("claim_opinion_score", 0.0) < 0.3:
            passed = False
            failure_reasons.append("ClaimOpinion")
            
        result = {
            "mode": "practice",
            "passed": passed,
            "failure_reasons": failure_reasons,
            "scores": scores,
            "is_fallback": used_fallback,
            "error": error_msg if used_fallback else None
        }
        return result

    def submit_final(self, note: Note, tweet_id: str) -> Dict[str, Any]:
        """
        Exam Mode: Submits the note to X API (test_mode) and analyzes the result.
        Only allowed if Practice checks passed (enforced by UI/Caller).
        """
        logger.info(f"Submitting Final Note {note.id} to Admission Engine...")
        
        try:
            # Submit to X API
            response = self.x_client.submit_note(
                tweet_id=tweet_id,
                note_text=note.text,
                test_mode=True
            )
            
            # Parse scores
            scores = self.x_client.parse_admission_scores(response)
            
            # Determine status
            url_score = scores.get("url_validity_score", 0.0)
            claim_score = scores.get("claim_opinion_score", 0.0)
            abuse_score = scores.get("harassment_abuse_score", 0.0)
            
            passed = True
            failure_reasons = []
            
            if url_score < 0.95:
                passed = False
                failure_reasons.append("UrlValidity")
                
            if claim_score < 0.3:
                passed = False
                failure_reasons.append("ClaimOpinion")
                
            if abuse_score < 0.98:
                passed = False
                failure_reasons.append("HarassmentAbuse")
                
            result = {
                "mode": "exam",
                "passed": passed,
                "failure_reasons": failure_reasons,
                "scores": scores,
                "raw_response": response
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error submitting note: {e}")
            return {
                "mode": "exam",
                "passed": False,
                "failure_reasons": ["API Error"],
                "error": str(e),
                "scores": {}
            }

    def fix_note(self, note: Note, failure_reasons: list[str]) -> str:
        """
        Triggers the appropriate fixer agent based on failure reasons.
        Returns the fixed note text.
        """
        current_text = note.text
        
        # Priority 1: Fix URL (Researcher)
        if "UrlValidity" in failure_reasons:
            logger.info("Triggering Researcher to fix URL...")
            new_url = self.researcher.find_better_url(current_text)
            if new_url:
                # Replace the old URL or append the new one
                # Simple heuristic: append if not present
                if new_url not in current_text:
                    current_text += f" Source: {new_url}"
                # In a real scenario, we might want to replace the bad URL
                
        # Priority 2: Fix Content (Editor)
        if "ClaimOpinion" in failure_reasons or "HarassmentAbuse" in failure_reasons:
            logger.info("Triggering Editor to fix content...")
            try:
                response = self.grok._chat(
                    system_prompt=FIXER_EDITOR_PROMPT,
                    user_prompt=f"Note Text: {current_text}\nFailures: {', '.join(failure_reasons)}"
                )
                cleaned = response.replace("```json", "").replace("```", "").strip()
                data = json.loads(cleaned)
                rewritten = data.get("rewritten_note")
                if rewritten:
                    current_text = rewritten
            except Exception as e:
                logger.error(f"Error running Editor: {e}")
                
        return current_text
