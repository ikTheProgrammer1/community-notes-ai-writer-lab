import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from note_writer_lab.models import Base, Note, Tweet, WriterConfig
from note_writer_lab.schemas import ArchitectOutput, Critique, Persona
from note_writer_lab.simulator import BridgeRankSimulator


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@pytest.fixture
def mock_grok():
    return MagicMock()


def test_run_architect(session, mock_grok):
    simulator = BridgeRankSimulator(session, grok_client=mock_grok)
    
    # Mock Grok response
    mock_response = json.dumps({
        "analysis": "Conflict detected",
        "personas": [
            {"name": "P1", "core_motivation": "M1", "critique_criteria": ["C1"]},
            {"name": "P2", "core_motivation": "M2", "critique_criteria": ["C2"]},
            {"name": "P3", "core_motivation": "M3", "critique_criteria": ["C3"]},
        ]
    })
    mock_grok._chat.return_value = mock_response
    
    output = simulator.run_architect("Some controversial tweet")
    
    assert isinstance(output, ArchitectOutput)
    assert len(output.personas) == 3
    assert output.personas[0].name == "P1"


def test_run_simulation(session, mock_grok):
    simulator = BridgeRankSimulator(session, grok_client=mock_grok)
    
    # Setup data
    writer = WriterConfig(name="TestWriter", prompt="TestPrompt")
    tweet = Tweet(tweet_id="123", text="Test Tweet")
    note = Note(writer=writer, tweet=tweet, text="Test Note")
    session.add_all([writer, tweet, note])
    session.commit()
    
    personas = [
        Persona(name="P1", core_motivation="M1", critique_criteria=["C1"]),
        Persona(name="P2", core_motivation="M2", critique_criteria=["C2"]),
        Persona(name="P3", core_motivation="M3", critique_criteria=["C3"]),
    ]
    
    # Mock Grok response for simulation (called 3 times)
    mock_grok._chat.side_effect = [
        json.dumps({"persona_name": "P1", "score": 0.8, "reasoning": "Good"}),
        json.dumps({"persona_name": "P2", "score": 0.6, "reasoning": "Okay"}),
        json.dumps({"persona_name": "P3", "score": 0.4, "reasoning": "Bad"}),
    ]
    
    simulation = simulator.run_simulation(note, personas)
    
    assert simulation.note_id == note.id
    assert len(simulation.critiques_dump) == 3
    # Avg = 0.6. Variance = ((0.2^2 + 0^2 + 0.2^2)/3) = 0.08/3 = 0.0266. 
    # Penalty = 0.0266 * 0.5 = 0.0133. Score = 0.6 - 0.0133 = 0.586...
    assert 0.5 < simulation.bridge_score < 0.6


def test_run_refiner(session, mock_grok):
    simulator = BridgeRankSimulator(session, grok_client=mock_grok)
    
    # Setup data
    writer = WriterConfig(name="TestWriter", prompt="TestPrompt")
    tweet = Tweet(tweet_id="123", text="Test Tweet")
    note = Note(writer=writer, tweet=tweet, text="Test Note")
    session.add_all([writer, tweet, note])
    session.commit()
    
    # Mock Grok response for simulation (called 3 times here)
    mock_grok._chat.side_effect = [
        json.dumps({"persona_name": "P1", "score": 0.8, "reasoning": "Good"}),
        json.dumps({"persona_name": "P2", "score": 0.8, "reasoning": "Good"}),
        json.dumps({"persona_name": "P3", "score": 0.8, "reasoning": "Good"}),
        json.dumps({"rewritten_note": "Better Note", "change_summary": "Fixed stuff"}) # For refiner
    ]
    
    personas = [
        Persona(name="P1", core_motivation="M1", critique_criteria=["C1"]),
        Persona(name="P2", core_motivation="M2", critique_criteria=["C2"]),
        Persona(name="P3", core_motivation="M3", critique_criteria=["C3"]),
    ]

    # Create a simulation first
    simulation = simulator.run_simulation(note, personas)
    
    new_note = simulator.run_refiner(note, simulation)
    
    assert new_note.text == "Better Note"
    assert new_note.stage == "rewrite"
    assert new_note.parent_note_id == note.id
