import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from note_writer_lab.rag_engine import RAGEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("--- RAG Engine Verification ---")
    
    try:
        rag = RAGEngine()
        
        # 1. Ingest Data
        print("Step 1: Ingesting Data...")
        rag.ingest_helpful_notes(limit=5000)
        print("Ingestion Complete.")
        
        # 2. Test Retrieval
        query_text = "Inflation is hurting the economy."
        print(f"\nStep 2: Querying for: '{query_text}'")
        
        results = rag.find_similar_notes(query_text, n_results=3)
        
        if not results:
            print("❌ No results found.")
        else:
            print(f"✅ Found {len(results)} similar notes:\n")
            for i, res in enumerate(results):
                print(f"--- Result {i+1} ---")
                print(f"Note: {res['note_text'][:200]}...") # Truncate for display
                print(f"Metadata: {res['metadata']}")
                print()

        print("--- Verification Complete ---")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
