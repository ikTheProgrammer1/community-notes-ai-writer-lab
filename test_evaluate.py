"""
Test script for XClient.evaluate_note
"""
import os
import logging
from note_writer_lab.x_client import XClient

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_evaluate():
    client = XClient()
    
    tweet_id = "1859382644263063923" # Example ID
    note_text = "This is a test note for practice mode."
    
    print(f"Testing evaluate_note with tweet_id={tweet_id}...")
    
    try:
        response = client.evaluate_note(tweet_id, note_text)
        print("Success!")
        print(response)
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_evaluate()
