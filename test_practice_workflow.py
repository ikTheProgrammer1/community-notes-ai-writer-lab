"""
Quick test to verify the Practice vs Exam workflow is working.
"""
import requests

# Test 1: Check home page loads
print("Test 1: Loading home page...")
response = requests.get("http://127.0.0.1:8000")
if response.status_code == 200:
    print("✓ Home page loads successfully")
    if "Tweet URL" in response.text:
        print("✓ Tweet URL input is present")
    if "Check Draft (Practice)" in response.text:
        print("✓ Practice button is present")
else:
    print(f"✗ Failed to load home page: {response.status_code}")

# Test 2: Submit a practice check
print("\nTest 2: Submitting practice check...")
data = {
    "tweet_url": "https://x.com/test/status/123456",
    "note_text": "This is a test note with a URL https://example.com",
    "action": "check"
}

try:
    response = requests.post("http://127.0.0.1:8000/simulator/run", data=data)
    print(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        print("✓ Practice check endpoint responds")
        
        # Check for key elements
        if "Practice Results" in response.text:
            print("✓ Practice Results page shown")
        elif "Admission Results" in response.text:
            print("⚠ Shows Admission Results (might be exam mode)")
            
        if "Submit to Community Notes" in response.text:
            print("✓ Submit button is present")
        
        if "Error:" in response.text:
            print("⚠ Error message detected in response")
            # Extract error if present
            import re
            error_match = re.search(r'<strong>Error:</strong> (.*?)</div>', response.text)
            if error_match:
                print(f"  Error: {error_match.group(1)[:100]}")
    else:
        print(f"✗ Failed: {response.status_code}")
        
except Exception as e:
    print(f"✗ Exception: {e}")

print("\n" + "="*50)
print("Manual Testing Instructions:")
print("="*50)
print("1. Open http://127.0.0.1:8000 in your browser")
print("2. Paste a Tweet URL (e.g., https://x.com/user/status/123)")
print("3. Enter a note with a URL")
print("4. Click 'Check Draft (Practice)'")
print("5. Verify the results show 'Practice Results'")
print("6. Check if 'Submit' button is disabled/enabled based on score")
print("7. Try the 'Auto-Fix' button if score is low")
print("="*50)
