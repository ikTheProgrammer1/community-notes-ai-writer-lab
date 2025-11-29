import duckdb
import logging
import os
import glob
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class HistoryEngine:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.con = duckdb.connect(database=":memory:")
        self._init_tables()

    def _find_file(self, pattern: str) -> str:
        """
        Finds a file matching the pattern in the data directory.
        Returns the first match or raises FileNotFoundError.
        """
        full_pattern = os.path.join(self.data_dir, pattern)
        matches = glob.glob(full_pattern)
        if not matches:
            # Try recursive if not found in top level? No, keep it simple for now.
            # But let's try to be helpful if the user provided specific names.
            # If pattern is specific like "ratings-00005.tsv", glob works.
            # If pattern is "ratings-*.tsv", glob works.
            raise FileNotFoundError(f"No file matching {pattern} found in {self.data_dir}")
        return matches[0]

    def _init_tables(self):
        """
        Register the TSV files as DuckDB views for querying.
        """
        try:
            # Use glob patterns to be robust against specific version numbers
            notes_path = self._find_file("notes-*.tsv")
            ratings_path = self._find_file("ratings-*.tsv")
            status_path = self._find_file("noteStatusHistory-*.tsv")

            logger.info(f"Loading Notes from: {notes_path}")
            logger.info(f"Loading Ratings from: {ratings_path}")
            logger.info(f"Loading Status from: {status_path}")

            # Create views directly from the TSV files
            # read_csv_auto is powerful but we can hint delimiters if needed. 
            # Community Notes are TSV.
            self.con.execute(f"CREATE OR REPLACE VIEW notes AS SELECT * FROM read_csv_auto('{notes_path}', sep='\\t', ignore_errors=true)")
            self.con.execute(f"CREATE OR REPLACE VIEW ratings AS SELECT * FROM read_csv_auto('{ratings_path}', sep='\\t', ignore_errors=true)")
            self.con.execute(f"CREATE OR REPLACE VIEW status AS SELECT * FROM read_csv_auto('{status_path}', sep='\\t', ignore_errors=true)")
            
            logger.info("HistoryEngine: Tables initialized successfully.")
        except Exception as e:
            logger.error(f"HistoryEngine: Failed to initialize tables: {e}")
            raise e

    def get_total_notes_count(self) -> int:
        """Returns the total number of rows in the notes table."""
        try:
            return self.con.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        except Exception as e:
            logger.error(f"Error counting notes: {e}")
            return 0

    def get_source_trust_score(self, domain: str) -> Dict[str, Any]:
        """
        Calculates the 'Trust Score' (% Helpful) of a domain.
        
        Logic:
        1. Find notes containing the domain in the text (summary).
        2. Join with status history to see the current status.
        3. Calculate % CURRENTLY_RATED_HELPFUL vs Total.
        """
        if not domain:
            return {"trust_score": 0.0, "total_notes": 0, "helpful_notes": 0}

        # We need to join notes with status on noteId.
        # Status table has 'noteId' and 'currentStatus'.
        # Notes table has 'noteId' and 'summary' (the text).
        
        query = f"""
            WITH domain_notes AS (
                SELECT n.noteId, s.currentStatus
                FROM notes n
                JOIN status s ON n.noteId = s.noteId
                WHERE n.summary ILIKE '%{domain}%'
            )
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN currentStatus = 'CURRENTLY_RATED_HELPFUL' THEN 1 ELSE 0 END) as helpful
            FROM domain_notes
        """
        
        try:
            result = self.con.execute(query).fetchone()
            total = result[0] or 0
            helpful = result[1] or 0
            
            if total == 0:
                return {"trust_score": 0.0, "total_notes": 0, "helpful_notes": 0}
                
            score = helpful / total
            return {
                "trust_score": score,
                "total_notes": total,
                "helpful_notes": helpful
            }
        except Exception as e:
            logger.error(f"Error calculating trust score for {domain}: {e}")
            return {"trust_score": 0.0, "error": str(e)}

    def get_narrative_share(self, topic: str) -> Dict[str, Any]:
        """
        Calculates the volume of HELPFUL notes containing a topic.
        """
        if not topic:
            return {"share_volume": 0}

        query = f"""
            SELECT COUNT(*)
            FROM notes n
            JOIN status s ON n.noteId = s.noteId
            WHERE n.summary ILIKE '%{topic}%'
            AND s.currentStatus = 'CURRENTLY_RATED_HELPFUL'
        """
        
        try:
            result = self.con.execute(query).fetchone()
            volume = result[0] or 0
            return {"share_volume": volume}
        except Exception as e:
            logger.error(f"Error calculating narrative share for {topic}: {e}")
            return {"share_volume": 0, "error": str(e)}
