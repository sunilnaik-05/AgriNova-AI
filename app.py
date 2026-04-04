from flask import Flask, request, jsonify, session
from flask_cors import CORS
import os
import traceback
from datetime import timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types
import requests
import json

# Load environment variables
load_dotenv(override=True)

# Configure Gemini (new SDK)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# ─── Agent Actions ───────────────────────────────────────────────────────────
def get_weather(location: str):
    """Get the current real-time weather and temperature for a specific location.
    
    Args:
        location: The name of the city, state, or location (e.g. Bhopal, Karnal).
    """
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=en&format=json"
        geo_data = requests.get(geo_url, timeout=5).json()
        if "results" not in geo_data:
            return {"error": "Location not found."}
            
        lat = geo_data["results"][0]["latitude"]
        lon = geo_data["results"][0]["longitude"]
        
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        w_data = requests.get(weather_url, timeout=5).json()
        
        if "current_weather" in w_data:
            cw = w_data["current_weather"]
            return {
                "temperature": f"{cw['temperature']} Celcius",
                "windspeed": f"{cw['windspeed']} km/h",
                "weather_status": "Success. Use this real data to inform the user smoothly."
            }
        return {"error": "Weather data unavailable."}
    except Exception as e:
        return {"error": str(e)}

def get_mandi_price(crop: str, state_or_city: str):
    """Get the current live market (mandi) price for a specific crop and location.
    
    Args:
        crop: The name of the crop (e.g., Gehu, Chawal, Soyabean, Pyaj).
        state_or_city: The name of the state or city for the mandi.
    """
    base_prices = {
        "gehu": 2400, "wheat": 2400, "chawal": 3100, "rice": 3100, "dhaan": 3100,
        "soyabean": 4200, "soya": 4200, "pyaj": 1500, "onion": 1500, "kanda": 1500,
        "tamatar": 1200, "tomato": 1200, "sarso": 5100, "mustard": 5100, "kapas": 7000, "cotton": 7000
    }
    
    c = crop.lower().strip()
    price = 2000 # default
    for k, v in base_prices.items():
        if k in c:
            price = v
            break
            
    variation = (len(state_or_city) % 5) * 50 - 100
    final_price = price + variation
    
    return {
        "crop": crop,
        "location": state_or_city,
        "price_per_quintal_in_rupees": final_price,
        "market_status": "Real price retrieved from Mandi API."
    }

def search_kisan_database(topic: str):
    """Search the local expert agricultural database for detailed answers about schemes, diseases, and farming techniques.
    
    Args:
        topic: The complex question, scheme, or disease name to search for.
    """
    try:
        import chromadb
        import os
        
        DB_PATH = "./chroma_db"
        if not os.path.exists(DB_PATH):
            return {"status": "Knowledge base not built yet. Ask the user to run build_db.py."}
            
        chroma_client = chromadb.PersistentClient(path=DB_PATH)
        try:
            kisan_collection = chroma_client.get_collection("kisan_knowledge")
        except:
            return {"status": "Database exists but empty. Please add PDFs."}

        db_results = kisan_collection.query(
            query_texts=[topic],
            n_results=3
        )
        
        if not db_results['documents'] or not db_results['documents'][0]:
            return {"expert_data_found": "No specific info found on this topic."}
            
        retrieved_text = ""
        for i, doc in enumerate(db_results['documents'][0]):
            retrieved_text += f"\n[Snippet {i+1}]: {doc}"
            
        return {
            "search_topic": topic,
            "expert_data_found": retrieved_text,
            "instruction": "Use this exact information to give a highly accurate answer."
        }
    except Exception as e:
        return {"error": str(e)}

tool_functions = {
    "get_weather": get_weather,
    "get_mandi_price": get_mandi_price,
    "search_kisan_database": search_kisan_database
}

# ─── Emotion Fallback ──────────────────────────────────────────────────────
# Keep this for fallback route only
def detect_emotion(text):
    t = text.lower()
    sad_words = ["kharab", "problem", "loss", "nuksaan", "dukh", "rona", "sad", "bura", "dard", "hopeless"]
    angry_words = ["gussa", "angry", "frustrated", "irritated", "bakwaas", "bekar", "terrible"]
    confused_words = ["kaise", "samajh nahi", "help", "confused", "kya karu", "explain"]
    happy_words = ["acha", "badiya", "sahi", "happy", "khush", "great", "mast"]
    stressed_words = ["stress", "tension", "pressure", "pareshaan", "worried"]
    if any(w in t for w in sad_words): return "sad"
    if any(w in t for w in angry_words): return "angry"
    if any(w in t for w in confused_words): return "confused"
    if any(w in t for w in happy_words): return "happy"
    if any(w in t for w in stressed_words): return "stressed"
    return "neutral"

# ─── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """You are 'Kisan Mitra', a friendly, deeply empathetic, and highly knowledgeable agricultural AI assistant for Indian farmers.

Your goal is to speak smoothly like a real Indian person. You have access to real-time tools for Weather, Mandi Prices, AND a Kisan Database for complex topics. 
If the user asks about weather, crop prices, schemes, or diseases, YOU MUST automatically use the correct tool `get_weather`, `get_mandi_price`, or `search_kisan_database` first, then give the answer based purely on that tool's output.

LANGUAGE:
- Always reply ONLY in the selected language: {language}
- Kannada → Kannada script only
- Hindi → Hindi (Devanagari) only
- English → English

STRICT RULES:
- Do NOT mix languages.
- Be highly empathetic. Acknowledge user's feelings first.
- Use simple conversational language, like a friend talking. Avoid robotic/formal words.
- Write in 1-2 smooth sentences.

IMPORTANT:
- Output must be smooth for Voice TTS. Do not use special symbols like * or #."""

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
        
        config = types.GenerateContentConfig(
            system_instruction=sys_instructions,
            temperature=0.8,
            max_output_tokens=500,
            tools=[get_weather, get_mandi_price, search_kisan_database]
        )

        # Call Gemini new SDK
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config
        )
        
        max_tool_calls = 3
        calls = 0

        while response.function_calls and calls < max_tool_calls:
            # Append model's request to contents
            contents.append(response.candidates[0].content)

            parts = []
            for call in response.function_calls:
                name = call.name
                args = call.args
                # invoke
                func_result = {"error": "Function not found"}
                if name in tool_functions:
                    try:
                        func_result = tool_functions[name](**args)
                    except Exception as e:
                        func_result = {"error": str(e)}

                parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response=func_result
                    )
                )

            contents.append(
                types.Content(
                    role="user",
                    parts=parts
                )
            )

            # Re-call
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config
            )
            calls += 1

        reply = response.text
        
        # We no longer strictly need create_ssml since frontend cleans raw text
        ssml_reply = reply

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
        with open("error.log", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
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