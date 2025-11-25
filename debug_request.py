import requests

url = "http://127.0.0.1:8000/simulator/run"
data = {
    "tweet_text": "The earth is flat.",
    "note_text": "This is false."
}

try:
    response = requests.post(url, data=data)
    print(f"Status Code: {response.status_code}")
    print("Response Body:")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
