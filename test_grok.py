from note_writer_lab.grok_client import GrokClient

client = GrokClient()
try:
    response = client._chat(
        system_prompt="You are a helpful assistant.",
        user_prompt="Say 'Hello World' and nothing else."
    )
    print("✓ GrokClient works!")
    print(f"Response: {response}")
except Exception as e:
    print(f"✗ GrokClient failed: {e}")
