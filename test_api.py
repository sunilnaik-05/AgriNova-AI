import os, traceback, sys
sys.stdout = open('api_result.txt', 'w', encoding='utf-8')
sys.stderr = sys.stdout

from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

key = os.getenv('GEMINI_API_KEY')
print(f"Key: {key[:20] if key else 'NONE'}...")

client = genai.Client(api_key=key)
try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Say hi in one line",
        config=types.GenerateContentConfig(temperature=0.5)
    )
    print(f"SUCCESS: {response.text}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}")
    print(f"Message: {str(e)[:300]}")
    traceback.print_exc()

sys.stdout.close()
