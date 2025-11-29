import chromadb
import logging
from typing import List, Dict, Any, Optional
from .analytics import HistoryEngine

logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self, persist_path: str = "data/chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_path)
        # Use the default embedding function (all-MiniLM-L6-v2) implicitly by not specifying one
        self.collection = self.client.get_or_create_collection(name="gold_standard_notes")
        self.history_engine = HistoryEngine()

    def ingest_helpful_notes(self, limit: int = 5000):
        """
        Fetches 'CURRENTLY_RATED_HELPFUL' notes from DuckDB and indexes them in ChromaDB.
        """
        logger.info(f"Ingesting top {limit} helpful notes into ChromaDB...")
        
        # Query DuckDB for helpful notes
        # We join with status to filter by CURRENTLY_RATED_HELPFUL
        query = f"""
            SELECT n.noteId, n.summary
            FROM notes n
            JOIN status s ON n.noteId = s.noteId
            WHERE s.currentStatus = 'CURRENTLY_RATED_HELPFUL'
            LIMIT {limit}
        """
        
        try:
            results = self.history_engine.con.execute(query).fetchall()
            
            if not results:
                logger.warning("No helpful notes found to ingest.")
                return

            ids = []
            documents = []
            metadatas = []
            
            for row in results:
                note_id = str(row[0])
                summary = row[1]
                
                if not summary:
                    continue
                    
                ids.append(note_id)
                documents.append(summary)
                metadatas.append({"noteId": note_id})
                
            # Add to collection in batches if needed, but 5000 is small enough for one go usually
            # Chroma handles batching internally for reasonable sizes
            if ids:
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                logger.info(f"Successfully indexed {len(ids)} notes.")
            
        except Exception as e:
            logger.error(f"Error ingesting notes: {e}")
            raise e

    def find_similar_notes(self, draft_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Finds the most similar helpful notes to the draft text.
        """
        if not draft_text:
            return []
            
        try:
            results = self.collection.query(
                query_texts=[draft_text],
                n_results=n_results
            )
            
            # Parse results into a cleaner format
            # results['documents'][0] is a list of strings
            # results['metadatas'][0] is a list of dicts
            
            parsed_results = []
            if results['documents']:
                docs = results['documents'][0]
                metas = results['metadatas'][0]
                
                for i in range(len(docs)):
                    parsed_results.append({
                        "note_text": docs[i],
                        "metadata": metas[i]
                    })
                    
            return parsed_results
            
        except Exception as e:
            logger.error(f"Error querying similar notes: {e}")
            return []
