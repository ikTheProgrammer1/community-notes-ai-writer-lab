import requests

url = "http://127.0.0.1:8000/simulator/run"
data = {
    "tweet_url": "https://x.com/bikatr7/status/1992818336649105792?s=20",
    "note_text": "Test note",
    "action": "check"
}

try:
    response = requests.post(url, data=data)
    print(f"Status Code: {response.status_code}")
    print("Response Body:")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
