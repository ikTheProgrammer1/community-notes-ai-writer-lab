import pytest
from sqlalchemy import select
from note_writer_lab.db import get_session
from note_writer_lab.models import GoldStandardCase, Note, Tweet, WriterConfig
from note_writer_lab.simulator import BridgeRankSimulator
from note_writer_lab.grok_client import GrokClient

@pytest.fixture
def db_session():
    session = next(get_session())
    yield session
    session.close()

def test_calibration(db_session):
    """
    Verifies that the BridgeRank Simulator assigns higher scores to HELPFUL notes
    than to NOT_HELPFUL notes on average.
    """
    # 1. Load Gold Standard Cases
    cases = list(db_session.scalars(select(GoldStandardCase)))
    if not cases:
        pytest.skip("No Gold Standard cases found. Run ingest_gold_standard.py first.")
        
    helpful_cases = [c for c in cases if c.classification == "HELPFUL"]
    not_helpful_cases = [c for c in cases if c.classification == "NOT_HELPFUL"]
    
    assert helpful_cases, "No HELPFUL cases found"
    assert not_helpful_cases, "No NOT_HELPFUL cases found"
    
    print(f"\nFound {len(helpful_cases)} HELPFUL and {len(not_helpful_cases)} NOT_HELPFUL cases.")
    
    # 2. Run Simulator
    # We need a real GrokClient (or a very sophisticated mock, but for calibration we want real AI)
    # Assuming we have API key in env
    try:
        grok = GrokClient()
    except ValueError:
        pytest.skip("GROK_API_KEY not set")
        
    simulator = BridgeRankSimulator(db_session, grok_client=grok)
    
    helpful_scores = []
    not_helpful_scores = []
    
    # Ensure a default writer exists for the notes
    writer = db_session.scalars(select(WriterConfig)).first()
    if not writer:
        writer = WriterConfig(name="Calibration User", prompt="Default")
        db_session.add(writer)
        db_session.flush()
        
    for case in cases:
        print(f"Simulating case {case.id}: {case.classification}...")
        
        # Create a temporary Note for simulation
        # We need a Tweet object too
        tweet = db_session.scalar(select(Tweet).where(Tweet.tweet_id == case.tweet_id))
        if not tweet:
            tweet = Tweet(tweet_id=case.tweet_id, text=case.tweet_text)
            db_session.add(tweet)
            db_session.flush()
            
        note = Note(
            writer_id=writer.id,
            tweet_id=case.tweet_id,
            text=case.text,
            stage="calibration"
        )
        db_session.add(note)
        db_session.flush()
        
        # Run Simulation
        run = simulator.run_simulation(note)
        
        if case.classification == "HELPFUL":
            helpful_scores.append(run.bridge_score)
        else:
            not_helpful_scores.append(run.bridge_score)
            
    # 3. Analyze Results
    avg_helpful = sum(helpful_scores) / len(helpful_scores)
    avg_not_helpful = sum(not_helpful_scores) / len(not_helpful_scores)
    
    print(f"\nAverage HELPFUL Score: {avg_helpful:.2f}")
    print(f"Average NOT_HELPFUL Score: {avg_not_helpful:.2f}")
    
    # 4. Assert Calibration
    # We expect a significant gap. Let's say at least 0.1 difference for now.
    assert avg_helpful > avg_not_helpful, f"Calibration failed: Helpful ({avg_helpful}) <= Not Helpful ({avg_not_helpful})"
    
    # Optional: Assert threshold
    # Helpful should be > 0.5, Not Helpful < 0.5?
    # assert avg_helpful > 0.5
    # assert avg_not_helpful < 0.5
