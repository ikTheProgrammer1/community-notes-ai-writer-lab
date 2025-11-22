import json
import logging
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from .grok_client import GrokClient
from .models import Note, SimulationRun, PersonaFeedback, Tweet
from .prompts import (
    ARCHITECT_SYSTEM_PROMPT,
    REFINER_SYSTEM_PROMPT,
    PERSONA_PROMPTS,
)
from .schemas import ArchitectOutput, RefinementOutput
from .metrics import calculate_bridge_score

logger = logging.getLogger(__name__)


class BridgeRankSimulator:
    def __init__(self, db: Session, grok_client: Optional[GrokClient] = None):
        self.db = db
        self.grok = grok_client or GrokClient()

    def _parse_json_response(self, response_text: str) -> dict:
        """Helper to robustly parse JSON from LLM response."""
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {cleaned}")
            return {}

    def run_architect(self, tweet_text: str) -> ArchitectOutput:
        """Step 1: Analyze tweet and generate personas (Legacy/Optional in M2)."""
        logger.info("Running Architect on tweet...")
        response = self.grok._chat(
            system_prompt=ARCHITECT_SYSTEM_PROMPT,
            user_prompt=f"Tweet Text: {tweet_text}",
        )
        data = self._parse_json_response(response)
        return ArchitectOutput(**data)

    def run_simulation(self, note: Note) -> SimulationRun:
        """Step 2: Run the simulation with the Council (5 Personas)."""
        logger.info(f"Running Simulation for note {note.id} with The Council...")
        
        feedbacks = []
        scores = []

        for name, system_prompt in PERSONA_PROMPTS.items():
            user_prompt = f"Draft Note: {note.text}"
            
            try:
                response = self.grok._chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                data = self._parse_json_response(response)
                
                score = float(data.get("score", 0.0))
                critique = data.get("reasoning", "No reasoning provided.")
                missing_context = data.get("missing_context", False)
                strengths = data.get("strengths", [])
                weaknesses = data.get("weaknesses", [])
                
                feedback = PersonaFeedback(
                    persona_name=name,
                    score=score,
                    critique=critique,
                    missing_context=missing_context,
                    strengths=strengths,
                    weaknesses=weaknesses
                )
                feedbacks.append(feedback)
                scores.append(score)
            except Exception as e:
                logger.error(f"Error simulating persona {name}: {e}")
                # Add a default failure feedback to avoid crashing
                feedbacks.append(PersonaFeedback(
                    persona_name=name,
                    score=0.0,
                    critique="Error during simulation.",
                    missing_context=True
                ))
                scores.append(0.0)

        # Calculate BridgeScore
        bridge_score = calculate_bridge_score(scores, penalty_factor=1.0)
        
        consensus_status = "LIKELY_HELPFUL" if bridge_score > 0.6 else "NEEDS_WORK"
        if bridge_score < 0.4:
            consensus_status = "NOT_HELPFUL"

        # Save to DB
        simulation_run = SimulationRun(
            note_id=note.id,
            bridge_score=bridge_score,
            consensus_status=consensus_status,
            model_used=self.grok.model,
            persona_feedbacks=feedbacks
        )
        self.db.add(simulation_run)
        self.db.commit()
        self.db.refresh(simulation_run)
        
        return simulation_run

    def run_refiner(self, note: Note, simulation_run: SimulationRun) -> Note:
        """Step 3: Auto-refine the note based on critiques."""
        logger.info(f"Running Refiner for note {note.id}...")
        
        # Find the harshest critique
        sorted_feedbacks = sorted(simulation_run.persona_feedbacks, key=lambda x: x.score)
        harshest = sorted_feedbacks[0] if sorted_feedbacks else None
        
        critiques_text = ""
        if harshest:
             critiques_text = f"Major Critique from {harshest.persona_name}: {harshest.critique}"
        
        # Include all critiques for context
        full_critiques = "\n".join(
            [f"- {f.persona_name}: {f.critique} (Score: {f.score})" 
             for f in simulation_run.persona_feedbacks]
        )
        
        user_prompt = (
            f"Original Note: {note.text}\n\n"
            f"Critiques:\n{full_critiques}\n\n"
            f"Focus specifically on addressing this critique: {critiques_text}"
        )
        
        response = self.grok._chat(
            system_prompt=REFINER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        
        data = self._parse_json_response(response)
        refinement = RefinementOutput(**data)
        
        # Create new Note
        new_note = Note(
            writer_id=note.writer_id,
            tweet_id=note.tweet_id,
            stage="rewrite",
            text=refinement.rewritten_note,
            parent_note_id=note.id,
        )
        self.db.add(new_note)
        self.db.commit()
        self.db.refresh(new_note)
        
        return new_note
