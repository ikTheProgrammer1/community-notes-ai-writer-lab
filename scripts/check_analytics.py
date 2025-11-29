import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from note_writer_lab.analytics import HistoryEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("--- Analytics Engine Verification ---")
    
    try:
        engine = HistoryEngine()
        
        # 1. Verify Ingestion
        count = engine.get_total_notes_count()
        print(f"Total Notes Loaded: {count}")
        
        if count == 0:
            print("❌ ERROR: No notes loaded. Check file paths and delimiters.")
            return

        # 2. Verify Trust Score Logic
        domains = ["nytimes.com", "dailymail.co.uk", "wikipedia.org"]
        for domain in domains:
            result = engine.get_source_trust_score(domain)
            print(f"Trust Score for {domain}: {result}")
            
        # 3. Verify Narrative Share Logic
        topics = ["inflation", "border", "taxes"]
        for topic in topics:
            result = engine.get_narrative_share(topic)
            print(f"Narrative Share for '{topic}': {result}")

        print("--- Verification Complete ---")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
