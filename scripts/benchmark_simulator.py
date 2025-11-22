
import pandas as pd
import asyncio
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from note_writer_lab.models import Base, Note, Tweet, WriterConfig
from note_writer_lab.simulator import BridgeRankSimulator
from note_writer_lab.grok_client import GrokClient

# Setup DB (in-memory for benchmark)
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def load_and_sample_data(notes_path, status_path, n_per_class=5):
    print("Loading data...")
    notes_df = pd.read_csv(notes_path, sep='\t', usecols=['noteId', 'summary', 'tweetId'])
    status_df = pd.read_csv(status_path, sep='\t', usecols=['noteId', 'currentStatus'])
    
    # Join
    df = notes_df.merge(status_df, on='noteId')
    
    print("Status distribution after merge:")
    print(df['currentStatus'].value_counts())
    
    # Filter
    helpful = df[df['currentStatus'] == 'CURRENTLY_RATED_HELPFUL'].sample(n=n_per_class, random_state=42)
    not_helpful = df[df['currentStatus'] == 'CURRENTLY_RATED_NOT_HELPFUL'].sample(n=n_per_class, random_state=42)
    
    return pd.concat([helpful, not_helpful])

def run_benchmark():
    # Paths
    notes_path = "data/notes-00000.tsv"
    status_path = "data/noteStatusHistory-00000.tsv"
    
    if not os.path.exists(notes_path) or not os.path.exists(status_path):
        print("Data files not found in data/")
        return

    samples = load_and_sample_data(notes_path, status_path, n_per_class=5)
    
    session = SessionLocal()
    grok = GrokClient() # Will use env var for API key
    simulator = BridgeRankSimulator(session, grok_client=grok)
    
    results = []
    
    print(f"Running benchmark on {len(samples)} notes...")
    
    for _, row in samples.iterrows():
        note_text = row['summary']
        actual_status = row['currentStatus']
        tweet_id = str(row['tweetId'])
        
        print(f"Processing Note {row['noteId']} ({actual_status})...")
        
        # Create dummy objects
        tweet = Tweet(tweet_id=tweet_id, text="[Tweet text not available in this dataset]")
        # We need to add tweet to session to satisfy FK
        if not session.get(Tweet, tweet_id):
            session.add(tweet)
            
        # Create dummy writer
        writer = session.get(WriterConfig, 1)
        if not writer:
            writer = WriterConfig(name="Benchmark", prompt="test")
            session.add(writer)
            session.commit()
            
        note = Note(writer_id=writer.id, tweet_id=tweet_id, text=note_text, stage="draft")
        session.add(note)
        session.commit()
        
        # Run Sim
        try:
            # Skip Architect for speed/cost, just run Sim with default personas
            # But wait, run_simulation needs personas list if we want custom ones, 
            # OR it uses default PERSONA_PROMPTS if we don't pass them?
            # Let's check simulator.py. 
            # It iterates PERSONA_PROMPTS.items() directly in the loop.
            # So we don't need to pass anything extra.
            
            sim_run = simulator.run_simulation(note)
            
            results.append({
                "note_id": row['noteId'],
                "actual": actual_status,
                "predicted_score": sim_run.bridge_score,
                "predicted_status": sim_run.consensus_status,
                "text": note_text[:50] + "..."
            })
        except Exception as e:
            print(f"Error: {e}")

    # Analysis
    print("\n=== RESULTS ===")
    df_res = pd.DataFrame(results)
    print(df_res)
    
    helpful_avg = df_res[df_res['actual'] == 'CURRENTLY_RATED_HELPFUL']['predicted_score'].mean()
    not_helpful_avg = df_res[df_res['actual'] == 'CURRENTLY_RATED_NOT_HELPFUL']['predicted_score'].mean()
    
    print(f"\nAvg Score (HELPFUL): {helpful_avg:.2f}")
    print(f"Avg Score (NOT_HELPFUL): {not_helpful_avg:.2f}")
    
    # Accuracy (Threshold 0.5)
    df_res['correct'] = df_res.apply(lambda x: 
        (x['actual'] == 'CURRENTLY_RATED_HELPFUL' and x['predicted_score'] >= 0.5) or 
        (x['actual'] == 'CURRENTLY_RATED_NOT_HELPFUL' and x['predicted_score'] < 0.5), axis=1)
    
    accuracy = df_res['correct'].mean()
    print(f"Accuracy: {accuracy:.2%}")

if __name__ == "__main__":
    run_benchmark()
