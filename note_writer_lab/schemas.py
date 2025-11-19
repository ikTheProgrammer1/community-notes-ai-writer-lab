from typing import List
from pydantic import BaseModel, Field

class Persona(BaseModel):
    name: str = Field(..., description="Name of the persona, e.g., 'The Privacy Advocate'")
    core_motivation: str = Field(..., description="The core belief or motivation driving this persona")
    critique_criteria: List[str] = Field(..., description="List of 2-3 specific criteria this persona uses to judge notes")

class ArchitectOutput(BaseModel):
    analysis: str = Field(..., description="Brief analysis of the tweet's potential conflicts")
    personas: List[Persona] = Field(..., description="List of 3 diverse personas to critique the note", min_length=3, max_length=3)

class Critique(BaseModel):
    persona_name: str = Field(..., description="Name of the persona providing the critique")
    score: float = Field(..., description="Helpfulness score between 0.0 and 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(..., description="One sentence explanation of the score")

class RefinementOutput(BaseModel):
    rewritten_note: str = Field(..., description="The rewritten note text")
    change_summary: str = Field(..., description="Brief summary of changes made to address critiques")
