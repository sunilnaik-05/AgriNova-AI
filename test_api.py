import os, sys
sys.stdout = open('api_result.txt', 'w', encoding='utf-8')
sys.stderr = sys.stdout

from dotenv import load_dotenv
load_dotenv()
from google import genai

key = os.getenv('GEMINI_API_KEY')
client = genai.Client(api_key=key)

models_to_test = [
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash"
]

for model_name in models_to_test:
    print(f"\n--- Testing model: {model_name} ---")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents="Say hi in one line",
        )
        print(f"SUCCESS: {response.text.strip()}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__} - {str(e)[:300]}")

sys.stdout.close()
