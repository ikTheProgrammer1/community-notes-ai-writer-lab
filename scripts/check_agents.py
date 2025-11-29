import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from note_writer_lab.agents import ResearcherAgent, FixerAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("--- Agents Verification ---")
    
    try:
        # 1. Test Researcher Agent
        print("\nStep 1: Testing Researcher Agent...")
        researcher = ResearcherAgent()
        claim = "Inflation in the US is at 8%."
        print(f"Claim: {claim}")
        urls = researcher.find_sources(claim)
        if urls:
            print(f"✅ Found {len(urls)} sources:")
            for url in urls:
                print(f" - {url}")
        else:
            print("⚠️ No sources found (Check API key or model availability).")

        # 2. Test Fixer Agent
        print("\nStep 2: Testing Fixer Agent...")
        fixer = FixerAgent()
        draft = "This is a bad tweet and the person is lying about inflation."
        print(f"Draft: {draft}")
        critique = "Tone is too aggressive. Needs to be neutral."
        
        fixed_note = fixer.fix_note(draft, critique)
        print(f"\n✅ Fixed Note:\n{fixed_note}")

        print("\n--- Verification Complete ---")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
