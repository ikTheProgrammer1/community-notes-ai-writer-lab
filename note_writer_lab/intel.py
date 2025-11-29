import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from .x_client import XClient

logger = logging.getLogger(__name__)

class ThreatEngine:
    def __init__(self, x_client: Optional[XClient] = None):
        self.client = x_client or XClient()

    def get_open_goals(self, keywords: List[str], min_views: int = 10000) -> pd.DataFrame:
        """
        Fetches 'Open Goals': Viral tweets about keywords that have 0 notes.
        
        Returns a DataFrame ready for the UI.
        """
        try:
            # 1. Fetch eligible tweets (test_mode=true gives us a sample)
            # In a real prod scenario, we'd search for specific keywords.
            # The current XClient.fetch_eligible_tweets just hits the sample endpoint.
            # We will fetch a batch and then filter locally for now.
            raw_tweets = self.client.fetch_eligible_tweets(max_results=50)
            
            threats = []
            for tweet in raw_tweets:
                text = tweet.get("text", "")
                tweet_id = tweet.get("id")
                metrics = tweet.get("public_metrics", {})
                views = metrics.get("impression_count", 0)
                
                # Filter by keywords (if provided)
                # If no keywords, return all high-view tweets (Discovery Mode)
                hit = False
                if not keywords:
                    hit = True
                else:
                    for kw in keywords:
                        if kw.lower() in text.lower():
                            hit = True
                            break
                
                if hit and views >= min_views:
                    threats.append({
                        "Tweet Text": text,
                        "Views": self._format_views(views),
                        "Status": "Unchallenged ❌", # By definition, eligible means no helpful note yet
                        "URL": f"https://x.com/i/status/{tweet_id}",
                        "raw_views": views
                    })
            
            # Sort by views descending
            df = pd.DataFrame(threats)
            if not df.empty:
                df = df.sort_values("raw_views", ascending=False)
                # Drop raw_views for display
                df = df.drop(columns=["raw_views"])
                
            return df
            
        except Exception as e:
            logger.error(f"ThreatEngine Error: {e}")
            # Return empty DF on error
            return pd.DataFrame(columns=["Tweet Text", "Views", "Status", "URL"])

    @staticmethod
    def _format_views(count: int) -> str:
        if count >= 1_000_000:
            return f"{count/1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count/1_000:.1f}K"
        return str(count)
