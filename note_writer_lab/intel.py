import logging
import pandas as pd
import random
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from .x_client import XClient

logger = logging.getLogger(__name__)

class ThreatDetector:
    def __init__(self, x_client: Optional[XClient] = None):
        self.client = x_client or XClient()
        # Check for Bearer Token to determine mode
        self.live_mode = bool(os.getenv("X_BEARER_TOKEN") or os.getenv("X_API_BEARER_TOKEN") or os.getenv("X_API_KEY"))
        logger.info(f"ThreatDetector initialized in {'LIVE' if self.live_mode else 'SIMULATION'} mode.")

    def fetch_threats(self, keywords: List[str], min_views: int = 1000, force_simulation: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches 'Active Threats': Viral tweets about keywords.
        Auto-switches between Live API and Simulation based on credentials.
        Returns a standardized list of dictionaries.
        """
        threats = []
        
        if self.live_mode and not force_simulation:
            threats = self._fetch_live_threats(keywords)
        else:
            threats = self._generate_mock_threats(keywords)
            
        # Filter by min_views and standardize
        filtered_threats = []
        for t in threats:
            metrics = t.get("metrics", {})
            views = metrics.get("views", 0)
            
            if views >= min_views:
                # Calculate Threat Score
                t["threat_score"] = self._calculate_threat_level(views)
                # Add formatted views for UI if not present (though UI might handle it)
                t["formatted_views"] = self._format_views(views)
                filtered_threats.append(t)
        
        # Sort by views descending
        filtered_threats.sort(key=lambda x: x["metrics"]["views"], reverse=True)
            
        return filtered_threats

    def _fetch_live_threats(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Fetches real tweets from X API using search_recent.
        """
        all_threats = []
        if not keywords:
            return []

        # Construct Query: (kw1 OR kw2) -is:retweet -is:reply lang:en
        # The x_client.search_tweets appends the filters, so we just need the OR part.
        query_str = " OR ".join(f'"{kw}"' for kw in keywords)
        
        try:
            # We use the client's search_tweets which hits /2/tweets/search/recent
            # and requests public_metrics and created_at.
            results = self.client.search_tweets(query=query_str, max_results=20)
            
            for tweet in results:
                text = tweet.get("text", "")
                tweet_id = tweet.get("id")
                metrics = tweet.get("public_metrics", {})
                # Normalize metrics
                normalized_metrics = {
                    "views": metrics.get("impression_count", 0),
                    "likes": metrics.get("like_count", 0),
                    "retweets": metrics.get("retweet_count", 0)
                }
                
                author_username = tweet.get("author", {}).get("username", "unknown")
                created_at = tweet.get("created_at", "")
                
                all_threats.append({
                    "id": tweet_id,
                    "text": text,
                    "author": author_username,
                    "metrics": normalized_metrics,
                    "timestamp": created_at,
                    "url": f"https://x.com/{author_username}/status/{tweet_id}"
                })
        except Exception as e:
            logger.error(f"Error fetching live threats: {e}")
                
        return all_threats

    def _generate_mock_threats(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Generates realistic mock data for simulation.
        """
        mock_threats = []
        # Default templates if no keywords
        topics = keywords if keywords else ["Inflation", "Scandal", "Policy"]
        
        # 1. Better Usernames
        usernames = [
            "@TruthSeeker1776", "@DailyPatriot_", "@CapitolInsider", 
            "@CryptoBro_99", "@BreakingNews_US", "@EagleEye_24", 
            "@LibertyVoice", "@DeepStateExposed", "@RealTalk_USA",
            "@PolicyWatchdog"
        ]
        
        # 3. Bot Attack Simulation (Templates + Variable Hashtags)
        templates = [
            "BREAKING: Leaked documents reveal {topic} disaster!",
            "Why is no one talking about the {topic} crisis? They are hiding the truth.",
            "Senator Smith voted against {topic} relief. Unbelievable.",
            "Experts say {topic} will destroy the economy by next year.",
            "The mainstream media won't show you this about {topic}."
        ]
        
        hashtags = ["#Corruption", "#Scandal", "#Truth", "#WatchNow", "#Breaking", "#USA", "#Crisis"]
        
        for _ in range(random.randint(5, 10)):
            topic = random.choice(topics)
            base_text = random.choice(templates).format(topic=topic)
            
            # Vary hashtags slightly for "Bot" feel
            hashtag = random.choice(hashtags)
            text = f"{base_text} {hashtag}"
            
            views = random.randint(1000, 2500000) # 1k to 2.5M
            tweet_id = str(random.randint(1000000000, 9999999999))
            
            # 2. Add Timestamps (2 hours to 2 days ago)
            hours_ago = random.randint(2, 48)
            created_at = (datetime.now() - timedelta(hours=hours_ago)).isoformat()
            
            mock_threats.append({
                "id": tweet_id,
                "text": text,
                "author": random.choice(usernames),
                "metrics": {
                    "views": views,
                    "likes": int(views * 0.05),
                    "retweets": int(views * 0.01)
                },
                "timestamp": created_at,
                "url": f"https://x.com/{random.choice(usernames)[1:]}/status/{tweet_id}" # Strip @ for URL
            })
            
        return mock_threats

    def _calculate_threat_level(self, views: int) -> str:
        """
        Calculates Threat Level based on view count.
        """
        if views >= 1_000_000:
            return "CRITICAL"
        elif views >= 100_000:
            return "HIGH"
        else:
            return "ELEVATED"

    @staticmethod
    def _format_views(count: int) -> str:
        if count >= 1_000_000:
            return f"{count/1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count/1_000:.1f}K"
        return str(count)
