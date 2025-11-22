import csv
import sys
import os
import random

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from note_writer_lab.db import engine
from note_writer_lab.models import GoldStandardCase, Base

def ingest_real_data(notes_path, history_path, limit_per_class=50):
    """
    Ingests real data.
    1. Reads noteStatusHistory to find HELPFUL/NOT_HELPFUL note IDs.
    2. Reads notes to get the text for those IDs.
    """
    print(f"Scanning history from {history_path}...")
    
    helpful_ids = set()
    not_helpful_ids = set()
    
    # We need enough IDs to sample from. Let's try to get 10x the limit.
    target_count = limit_per_class * 10
    
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                status = row.get('currentStatus')
                nid = row.get('noteId')
                
                if status == "CURRENTLY_RATED_HELPFUL":
                    if len(helpful_ids) < target_count:
                        helpful_ids.add(nid)
                elif status == "CURRENTLY_RATED_NOT_HELPFUL":
                    if len(not_helpful_ids) < target_count:
                        not_helpful_ids.add(nid)
                
                if len(helpful_ids) >= target_count and len(not_helpful_ids) >= target_count:
                    break
    except Exception as e:
        print(f"Error reading history: {e}")
        return

    print(f"Found {len(helpful_ids)} HELPFUL and {len(not_helpful_ids)} NOT_HELPFUL IDs.")
    
    # Sample IDs now
    final_helpful_ids = set(random.sample(list(helpful_ids), min(len(helpful_ids), limit_per_class)))
    final_not_helpful_ids = set(random.sample(list(not_helpful_ids), min(len(not_helpful_ids), limit_per_class)))
    
    target_ids = final_helpful_ids.union(final_not_helpful_ids)
    
    print(f"Ingesting {len(target_ids)} notes from {notes_path}...")
    
    notes_to_ingest = []
    
    try:
        with open(notes_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                nid = row.get('noteId')
                if nid in target_ids:
                    # Determine class
                    classification = "HELPFUL" if nid in final_helpful_ids else "NOT_HELPFUL"
                    
                    row['simple_class'] = classification
                    notes_to_ingest.append(row)
                    
                    # Optimization: remove from set to make lookups faster (micro-opt) 
                    # and check if done
                    target_ids.remove(nid)
                    if not target_ids:
                        break
    except Exception as e:
        print(f"Error reading notes: {e}")
        return

    with Session(engine) as session:
        # Clear existing Gold Standard data
        session.query(GoldStandardCase).delete()
        
        count = 0
        for note in notes_to_ingest:
            tweet_text_placeholder = "[Real Tweet Text Lookup Needed for ID: " + note['tweetId'] + "]"
            
            gs_case = GoldStandardCase(
                tweet_id=note['tweetId'],
                tweet_text=tweet_text_placeholder,
                note_id=note['noteId'],
                text=note['summary'],
                classification=note['simple_class'],
                original_rating_status=note['classification'] # This is tweet classification, but we store it for context
            )
            session.add(gs_case)
            count += 1
            
        session.commit()
        print(f"Successfully ingested {count} real Gold Standard cases.")

if __name__ == "__main__":
    # Ensure tables exist
    Base.metadata.create_all(engine)
    
    notes_file = "data/notes-00000.tsv"
    history_file = "data/noteStatusHistory-00000.tsv"
    
    if os.path.exists(notes_file) and os.path.exists(history_file):
        ingest_real_data(notes_file, history_file)
    else:
        print(f"Data files not found.")
