import json
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from .grok_client import GrokClient
from .models import Note, Simulation, Tweet
from .prompts import (
    ARCHITECT_SYSTEM_PROMPT,
    REFINER_SYSTEM_PROMPT,
    SIMULATOR_SYSTEM_PROMPT,
)
from .schemas import ArchitectOutput, Critique, Persona, RefinementOutput

logger = logging.getLogger(__name__)


class BridgeRankSimulator:
    def __init__(self, db: Session, grok_client: Optional[GrokClient] = None):
        self.db = db
        self.grok = grok_client or GrokClient()

    def _parse_json_response(self, response_text: str) -> dict:
        """Helper to robustly parse JSON from LLM response."""
        # Strip markdown code blocks if present
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())

    def run_architect(self, tweet_text: str) -> ArchitectOutput:
        """Step 1: Analyze tweet and generate personas."""
        logger.info("Running Architect on tweet...")
        response = self.grok._chat(
            system_prompt=ARCHITECT_SYSTEM_PROMPT,
            user_prompt=f"Tweet Text: {tweet_text}",
        )
        data = self._parse_json_response(response)
        return ArchitectOutput(**data)

    def run_simulation(self, note: Note, personas: List[Persona]) -> Simulation:
        """Step 2: Run the simulation with the given personas."""
        logger.info(f"Running Simulation for note {note.id} with {len(personas)} personas...")
        
        critiques = []
        scores = []

        for persona in personas:
            user_prompt = (
                f"Persona Name: {persona.name}\n"
                f"Core Motivation: {persona.core_motivation}\n"
                f"Critique Criteria: {', '.join(persona.critique_criteria)}\n\n"
                f"Draft Note: {note.text}"
            )
            
            response = self.grok._chat(
                system_prompt=SIMULATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            
            data = self._parse_json_response(response)
            # Ensure persona name matches what we expect, or just trust the LLM?
            # Let's enforce the name from the loop to be safe in our record
            data["persona_name"] = persona.name 
            
            critique = Critique(**data)
            critiques.append(critique)
            scores.append(critique.score)

        # Calculate BridgeScore
        avg_score = sum(scores) / len(scores)
        variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
        penalty_factor = 0.5  # Tunable parameter
        bridge_score = max(0.0, avg_score - (variance * penalty_factor))

        # Save to DB
        simulation = Simulation(
            note_id=note.id,
            bridge_score=bridge_score,
            architect_dump=ArchitectOutput(analysis="Generated during simulation", personas=personas).model_dump(),
            critiques_dump=[c.model_dump() for c in critiques],
        )
        self.db.add(simulation)
        self.db.commit()
        self.db.refresh(simulation)
        
        return simulation

    def run_refiner(self, note: Note, simulation: Simulation) -> Note:
        """Step 3: Auto-refine the note based on critiques."""
        logger.info(f"Running Refiner for note {note.id}...")
        
        critiques_text = "\n".join(
            [f"- {c['persona_name']}: {c['reasoning']} (Score: {c['score']})" 
             for c in simulation.critiques_dump]
        )
        
        user_prompt = (
            f"Original Note: {note.text}\n\n"
            f"Critiques:\n{critiques_text}"
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
