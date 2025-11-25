import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from note_writer_lab.models import Base, Note, Tweet, WriterConfig
from note_writer_lab.admission_engine import AdmissionEngine
from note_writer_lab.x_client import XClient
from note_writer_lab.grok_client import GrokClient

# Setup in-memory DB
@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

def test_practice_mode_success(session):
    # Mock XClient
    mock_x = MagicMock(spec=XClient)
    mock_x.evaluate_note.return_value = {
        "noteContent": {
            "claimOpinionScore": 0.8
        }
    }
    
    # Mock GrokClient
    mock_grok = MagicMock(spec=GrokClient)

    engine = AdmissionEngine(session, grok_client=mock_grok, x_client=mock_x)
    
    note = Note(text="Good note", writer_id=1, tweet_id="123")
    
    # Run Practice
    result = engine.run_practice(note, tweet_id="123")
    
    assert result["mode"] == "practice"
    assert result["passed"] is True
    assert result["scores"]["claim_opinion_score"] == 0.8
    assert len(result["failure_reasons"]) == 0

def test_practice_mode_failure(session):
    # Mock XClient to fail practice
    mock_x = MagicMock(spec=XClient)
    mock_x.evaluate_note.return_value = {
        "noteContent": {
            "claimOpinionScore": 0.2 # Low score
        }
    }
    
    # Mock GrokClient
    mock_grok = MagicMock(spec=GrokClient)

    engine = AdmissionEngine(session, grok_client=mock_grok, x_client=mock_x)
    
    note = Note(text="Bad note", writer_id=1, tweet_id="123")
    
    # Run Practice
    result = engine.run_practice(note, tweet_id="123")
    
    assert result["mode"] == "practice"
    assert result["passed"] is False
    assert "ClaimOpinion" in result["failure_reasons"]

def test_exam_mode_success(session):
    # Mock XClient for submission
    mock_x = MagicMock(spec=XClient)
    mock_x.submit_note.return_value = {
        "data": {"id": "123"},
        "note_evaluation": {
            "urlValidity": 1.0,
            "claimOpinion": 0.8,
            "harassmentAbuse": 1.0
        }
    }
    mock_x.parse_admission_scores.side_effect = XClient.parse_admission_scores

    # Mock GrokClient
    mock_grok = MagicMock(spec=GrokClient)

    engine = AdmissionEngine(session, grok_client=mock_grok, x_client=mock_x)
    
    note = Note(text="Perfect note", writer_id=1, tweet_id="123")
    
    # Run Exam
    result = engine.submit_final(note, tweet_id="123")
    
    assert result["mode"] == "exam"
    assert result["passed"] is True
    assert result["scores"]["url_validity_score"] == 1.0
