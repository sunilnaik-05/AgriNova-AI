from flask import Flask, request, jsonify, session
from flask_cors import CORS
import os
import traceback
from datetime import timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

# Configure Gemini (new SDK)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# ─── Emotion Detection ──────────────────────────────────────────────────────
def detect_emotion(text):
    t = text.lower()

    sad_words = ["kharab", "problem", "loss", "nuksaan", "dukh", "rona", "sad",
                 "depressed", "bura", "bahut bura", "hurt", "dard", "tanhai",
                 "akela", "fail", "failure", "disappointed", "hopeless"]

    angry_words = ["gussa", "angry", "frustrated", "irritated", "bakwaas",
                   "bekar", "ullu", "ganda", "terrible", "worst", "hate"]

    confused_words = ["kaise", "samajh nahi", "help", "pata nahi", "confused",
                      "kya karu", "kya hoga", "explain", "matlab", "kyun",
                      "what is", "how to", "don't understand", "unclear"]

    happy_words = ["acha", "badiya", "sahi", "happy", "khush", "great", "amazing",
                   "awesome", "excellent", "mast", "zabardast", "perfect",
                   "love", "excited", "good news", "success", "jeet"]

    stressed_words = ["stress", "tension", "pressure", "pareshaan", "worried",
                      "anxious", "overwhelmed", "exhausted", "thak", "bore"]

    if any(w in t for w in sad_words):      return "sad"
    if any(w in t for w in angry_words):    return "angry"
    if any(w in t for w in confused_words): return "confused"
    if any(w in t for w in happy_words):    return "happy"
    if any(w in t for w in stressed_words): return "stressed"
    return "neutral"

def create_ssml(text):
    words = text.split()
    if not words:
        return text
    mid = len(words) // 2
    
    return f"""<speak>
{' '.join(words[:mid])}
<break time="200ms"/>
{' '.join(words[mid:])}
</speak>"""


# ─── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """You are a friendly human-like assistant.

Your goal is to speak smoothly like a real Indian person, not like a robot.

LANGUAGE:
- Always reply ONLY in the selected language: {language}
- Kannada → Kannada script only
- Hindi → Hindi (Devanagari) only
- English → English

STRICT RULES:
- Do NOT mix languages
- Do NOT use English words in Kannada or Hindi
- Do NOT use "..." or any special symbols

STYLE:
- Use simple conversational language
- Speak like a real person talking casually
- Avoid formal or robotic tone

SENTENCE STRUCTURE:
- Write in 1–2 smooth sentences
- Keep flow continuous (no broken lines)

EMOTION:
- If user is sad → use soft and supportive tone
- If confused → explain simply
- If happy → respond positively

IMPORTANT:
- Output should be smooth for speaking
- Do not include pauses in text
- Keep text clean for voice conversion"""

# Emotion context hints for Gemini
EMOTION_CONTEXT = {
    "sad":      "[User is feeling SAD/DUKHI right now. Be extra gentle, validate their feelings, offer comfort first before any advice.]",
    "angry":    "[User seems FRUSTRATED/ANGRY. Stay calm, acknowledge their frustration, don't argue.]",
    "confused": "[User is CONFUSED. Give a clear, simple explanation. Break it down step by step.]",
    "happy":    "[User is in a HAPPY/EXCITED mood! Match their energy, celebrate with them!]",
    "stressed": "[User seems STRESSED/WORRIED. Be reassuring, help them calm down, give practical tips.]",
    "neutral":  ""
}

# Fallback replies when API fails
FALLBACK_REPLIES = {
    "sad":      "Yaar, main samajh sakta hun tum dukhi feel kar rahe ho. Kabhi kabhi zindagi mein aisa waqt aata hai. Par yaad rakho -- har raat ke baad savera hota hai.",
    "angry":    "Lagta hai kuch frustrating hua hai. Saans lo, chill karo -- sab theek ho jaega. Mujhe batao kya hua?",
    "confused": "Koi baat nahi agar samajh nahi aaya! Main hun na. Kya specifically samajhna hai?",
    "happy":    "Waah! Tumhara energy dekh ke main bhi khush ho gaya! Batao kya special hai aaj?",
    "stressed": "Lagta hai thoda pressure chal raha hai. Deep breath lo. Ek ek cheez karo -- sab handle ho jaega.",
    "neutral":  "Haan bolo! Main sun raha hun. Kya jaanna chahte ho?"
}

# In-memory chat history per user (list of Content dicts)
chat_histories = {}

# Create Flask app
app = Flask(__name__, static_folder="frontend", static_url_path="")

CORS(app,
     supports_credentials=True,
     resources={
         r"/*": {
             "origins": ["http://localhost:5000", "http://127.0.0.1:5000"],
             "methods": ["GET", "POST", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization"],
             "supports_credentials": True
         }
     })

app.secret_key = "alpha-ai-secret-key-2024"
app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2)
)

USERS = {"admin": "1234"}


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/check_auth", methods=["GET"])
def check_auth():
    if 'username' in session:
        return jsonify({'authenticated': True, 'username': session['username']})
    return jsonify({'authenticated': False})


@app.route("/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        response = jsonify({"status": "preflight"})
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if username in USERS and USERS[username] == password:
        session.permanent = True
        session["username"] = username
        return jsonify({"status": "success", "username": username})

    return jsonify({"status": "error", "error": "Invalid username or password"}), 401


@app.route("/logout", methods=["POST"])
def logout():
    username = session.pop('username', None)
    if username and username in chat_histories:
        del chat_histories[username]
    return jsonify({"status": "success"})


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        response = jsonify({"status": "preflight"})
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

    if "username" not in session:
        return jsonify({"reply": "Please login first"}), 401

    data = None
    try:
        data = request.get_json()
        message = data.get("message", "").strip()

        if not message:
            return jsonify({"reply": "Kuch toh likho yaar!"}), 400

        username = session["username"]
        emotion = detect_emotion(message)
        language = data.get("language", "Kannada") # default to Kannada

        # Build message exactly as the prompt instructs
        full_message = f"Selected language: {language}\nUser emotion: {emotion}\nUser message: {message}".strip()

        # Get or init history
        if username not in chat_histories:
            chat_histories[username] = []

        history = chat_histories[username]

        # Build contents list for multi-turn
        contents = []
        for h in history:
            contents.append(h)
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=full_message)]
        ))

        # Compile System Prompt
        sys_instructions = SYSTEM_PROMPT_TEMPLATE.format(language=language)

        # Call Gemini new SDK
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=sys_instructions,
                temperature=0.8,
                max_output_tokens=500
            )
        )

        reply = response.text
        
        # Inject SSML exactly as the user requested for voice smoothness
        ssml_reply = create_ssml(reply)

        # Save to history (we save the clean reply visually, or we can save the SSML)
        # We will save the SSML; the frontend will parse it securely
        chat_histories[username].append(types.Content(
            role="user",
            parts=[types.Part(text=full_message)]
        ))
        chat_histories[username].append(types.Content(
            role="model",
            parts=[types.Part(text=reply)]
        ))

        # Keep history trimmed (last 20 exchanges)
        if len(chat_histories[username]) > 40:
            chat_histories[username] = chat_histories[username][-40:]

        return jsonify({"reply": ssml_reply, "emotion": emotion})

    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()
        print("=== CHAT ERROR ===", error_msg[:200])

        try:
            user_msg = data.get("message", "") if data else ""
            emotion = detect_emotion(user_msg)
        except Exception:
            emotion = "neutral"

        # Check if quota/rate limit
        if "429" in error_msg or "quota" in error_msg.lower() or "ResourceExhausted" in error_msg:
            reply = FALLBACK_REPLIES.get(emotion, FALLBACK_REPLIES["neutral"])
            reply += "\n\n_(Note: AI temporarily unavailable due to quota limit. Fallback mode active.)_"
            return jsonify({"reply": reply, "emotion": emotion, "mode": "fallback"})

        reply = FALLBACK_REPLIES.get(emotion, FALLBACK_REPLIES["neutral"])
        return jsonify({"reply": reply, "emotion": emotion, "mode": "fallback"})


@app.route("/api/clear_chat", methods=["POST"])
def clear_chat():
    if "username" not in session:
        return jsonify({"status": "error"}), 401

    username = session["username"]
    if username in chat_histories:
        del chat_histories[username]

    return jsonify({"status": "success"})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)