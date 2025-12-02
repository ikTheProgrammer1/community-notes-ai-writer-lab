import sys
import os
import logging
from unittest.mock import patch

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from note_writer_lab.intel import ThreatDetector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_threat_structure(threat):
    required_keys = ["id", "text", "author", "metrics", "threat_score", "timestamp"]
    missing = [k for k in required_keys if k not in threat]
    if missing:
        logger.error(f"❌ Threat missing keys: {missing}")
        return False
    
    metrics = threat.get("metrics", {})
    metric_keys = ["views", "likes", "retweets"]
    missing_metrics = [k for k in metric_keys if k not in metrics]
    if missing_metrics:
        logger.error(f"❌ Metrics missing keys: {missing_metrics}")
        return False
        
    return True

def main():
    print("--- ThreatDetector Verification ---")
    
    # 1. Test Live Mode (if keys exist)
    print("\nStep 1: Testing Live Mode (based on .env)...")
    detector = ThreatDetector()
    if detector.live_mode:
        print("✅ Live Mode Detected.")
        threats = detector.fetch_threats(keywords=["news"], min_views=100)
        if threats:
            print(f"✅ Fetched {len(threats)} live threats.")
            if validate_threat_structure(threats[0]):
                print("✅ Output structure valid.")
                print(f"Sample: {threats[0]['text'][:50]}... (Score: {threats[0]['threat_score']})")
        else:
            print("⚠️ No live threats found (check API limits or query).")
    else:
        print("⚠️ Live Mode not available (missing keys). Skipping.")

    # 2. Test Simulation Mode (Force it)
    print("\nStep 2: Testing Simulation Mode...")
    with patch.dict(os.environ, {"X_BEARER_TOKEN": "", "X_API_KEY": ""}):
        sim_detector = ThreatDetector()
        if not sim_detector.live_mode:
            print("✅ Simulation Mode Detected.")
            threats = sim_detector.fetch_threats(keywords=["Cybersecurity"], min_views=1000)
            if threats:
                print(f"✅ Generated {len(threats)} mock threats.")
                if validate_threat_structure(threats[0]):
                    print("✅ Output structure valid.")
                    print(f"Sample: {threats[0]['text'][:50]}... (Score: {threats[0]['threat_score']})")
            else:
                print("❌ Failed to generate mock threats.")
        else:
            print("❌ Failed to switch to Simulation Mode.")

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    main()
