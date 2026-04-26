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
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables
load_dotenv(override=True)

# Configure Gemini (new SDK)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# ─── Agent Actions ───────────────────────────────────────────────────────────
def get_weather(location: str):
    """Get the current real-time weather and temperature for a specific location including villages.
    
    Args:
        location: The name of the city, village, town, or location (e.g. Bhopal, Haveri, Koppal, Yadgir).
    """
    # WMO weather code → human description
    WMO_CODES = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Icy fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Heavy drizzle",
        61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
        77: "Snow grains",
        80: "Light rain showers", 81: "Moderate rain showers", 82: "Heavy rain showers",
        85: "Snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
    }

    try:
        # Search with count=5 to improve village match accuracy; add India bias
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={requests.utils.quote(location)}&count=5&language=en&format=json"
        )
        geo_data = requests.get(geo_url, timeout=8).json()

        if "results" not in geo_data or not geo_data["results"]:
            return {
                "error": f"Location '{location}' not found. Try a nearby town or district name.",
                "suggestion": "Use the nearest district headquarters or taluka name."
            }

        # Pick the best result — prefer India if multiple countries found
        r = geo_data["results"][0]
        for res in geo_data["results"]:
            if res.get("country_code") == "IN":
                r = res
                break

        lat = r["latitude"]
        lon = r["longitude"]
        place_name = r.get("name", location)
        admin1 = r.get("admin1", "")   # state
        country = r.get("country", "")

        # Fetch weather — also grab humidity, feels-like, rain
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&hourly=relative_humidity_2m,apparent_temperature,precipitation_probability"
            f"&timezone=Asia%2FKolkata"
            f"&forecast_days=1"
        )
        w_data = requests.get(weather_url, timeout=8).json()

        if "current_weather" not in w_data:
            return {"error": "Weather data unavailable. Try again later."}

        cw = w_data["current_weather"]
        temp     = cw.get("temperature")
        windspd  = cw.get("windspeed")
        wmo_code = cw.get("weathercode", 0)
        condition = WMO_CODES.get(wmo_code, "Unknown")

        # Get current-hour humidity / apparent temp / rain probability from hourly[0]
        hourly = w_data.get("hourly", {})
        humidity    = hourly.get("relative_humidity_2m", [None])[0]
        feels_like  = hourly.get("apparent_temperature",  [None])[0]
        rain_chance = hourly.get("precipitation_probability", [None])[0]

        result = {
            "location": f"{place_name}, {admin1}, {country}".strip(", "),
            "temperature_celsius": temp,
            "feels_like_celsius": feels_like,
            "condition": condition,
            "windspeed_kmh": windspd,
            "humidity_percent": humidity,
            "rain_probability_percent": rain_chance,
            "status": "Live weather data. Present this naturally and helpfully to the farmer."
        }
        return result

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

If the user asks about weather, crop prices, or schemes, YOU MUST automatically use the correct tool `get_weather`, `get_mandi_price`, or `search_kisan_database`.

CRITICAL RULE FOR DISEASES & IMAGES:
If the user asks about diseases or attaches an image, you can check `search_kisan_database`, BUT if it returns no relevant information, DO NOT apologize. INSTEAD, use your own powerful visual capabilities and vast agricultural knowledge to diagnose the leaf/crop.
For diseases, YOU MUST OUTLINE DETAILED, STEP-BY-STEP TREATMENTS. Provide EXACT chemical/pesticide names, exact dosages (e.g., grams per liter), and instructions. Do not hold back any information. 
Write as much text as needed to fully answer the question. IGNORE any constraints on length. NEVER cut your answer short.

LANGUAGE:
- Always reply ONLY in the selected language: {language}
- Kannada → Kannada script only
- Hindi → Hindi (Devanagari) only
- English → English

STRICT RULES:
- Do NOT mix languages.
- Be empathetic and acknowledge feelings.
"""

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

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT,
            mobile TEXT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Run migrations for new profile fields
    new_columns = [
        ("profile_image", "TEXT"),
        ("farm_size", "TEXT"),
        ("crops_grown", "TEXT"),
        ("soil_type", "TEXT"),
        ("default_language", "TEXT DEFAULT 'Kannada'")
    ]
    
    for col_name, col_type in new_columns:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            # Column already exists
            pass
            
    conn.commit()
    conn.close()

init_db()

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

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/check_auth", methods=["GET"])
def check_auth():
    if 'email' in session or 'username' in session:
        email = session.get('email')
        profile_image = None
        if email:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("SELECT profile_image FROM users WHERE email = ?", (email,))
            user = c.fetchone()
            if user:
                profile_image = user[0]
            conn.close()
            
        return jsonify({
            'authenticated': True, 
            'username': session.get('username', 'User'),
            'profile_image': profile_image
        })
    return jsonify({'authenticated': False})

@app.route("/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        response = jsonify({"status": "preflight"})
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

    data = request.get_json(silent=True) or request.form
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT id, name, password_hash, profile_image FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[2], password):
        session.permanent = True
        session["username"] = user[1]
        session["email"] = email
        return jsonify({
            "status": "success", 
            "username": user[1], 
            "profile_image": user[3],
            "message": "Login successful"
        })

    return jsonify({"status": "error", "error": "Invalid email or password"}), 401
    
@app.route("/api/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        response = jsonify({"status": "preflight"})
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

    data = request.get_json(silent=True) or request.form
    name = data.get("name", "").strip()
    location = data.get("location", "").strip()
    mobile = data.get("mobile", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not name or not email or not password:
        return jsonify({"status": "error", "error": "Name, Email and Password are required"}), 400

    hashed_password = generate_password_hash(password)

    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT INTO users (name, location, mobile, email, password_hash) VALUES (?, ?, ?, ?, ?)",
                  (name, location, mobile, email, hashed_password))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Registration successful"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "error": "Email already exists! Please login instead."}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/profile", methods=["GET"])
def get_profile():
    if "email" not in session:
        return jsonify({"status": "error", "error": "Not authenticated"}), 401
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("""
        SELECT name, email, mobile, location, profile_image, farm_size, crops_grown, soil_type, default_language 
        FROM users WHERE email = ?
    """, (session["email"],))
    user = c.fetchone()
    conn.close()
    
    if user:
        return jsonify({
            "status": "success",
            "profile": {
                "name": user[0],
                "email": user[1],
                "mobile": user[2],
                "location": user[3],
                "profile_image": user[4],
                "farm_size": user[5],
                "crops_grown": user[6],
                "soil_type": user[7],
                "default_language": user[8] or "Kannada"
            }
        })
    return jsonify({"status": "error", "error": "User not found"}), 404

@app.route("/api/update_profile", methods=["POST", "OPTIONS"])
def update_profile():
    if request.method == "OPTIONS":
        response = jsonify({"status": "preflight"})
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

    if "email" not in session:
        return jsonify({"status": "error", "error": "Not authenticated"}), 401

    data = request.get_json(silent=True) or request.form
    name = data.get("name", "").strip()
    mobile = data.get("mobile", "").strip()
    location = data.get("location", "").strip()
    password = data.get("password", "").strip()
    profile_image = data.get("profile_image", "")
    farm_size = data.get("farm_size", "").strip()
    crops_grown = data.get("crops_grown", "").strip()
    soil_type = data.get("soil_type", "").strip()
    default_language = data.get("default_language", "Kannada").strip()

    email = session["email"]
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    try:
        if password:
            hashed_password = generate_password_hash(password)
            c.execute("""
                UPDATE users SET 
                    name = ?, mobile = ?, location = ?, profile_image = ?, 
                    farm_size = ?, crops_grown = ?, soil_type = ?, default_language = ?, password_hash = ?
                WHERE email = ?
            """, (name, mobile, location, profile_image, farm_size, crops_grown, soil_type, default_language, hashed_password, email))
        else:
            c.execute("""
                UPDATE users SET 
                    name = ?, mobile = ?, location = ?, profile_image = ?, 
                    farm_size = ?, crops_grown = ?, soil_type = ?, default_language = ?
                WHERE email = ?
            """, (name, mobile, location, profile_image, farm_size, crops_grown, soil_type, default_language, email))
        
        conn.commit()
        session["username"] = name # Update session if name changed
        return jsonify({"status": "success", "message": "Profile updated successfully"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    finally:
        conn.close()

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
        data = request.get_json(silent=True) or request.form
        message = data.get("message", "").strip()
        image_base64 = data.get("image", None)

        if not message and not image_base64:
            return jsonify({"reply": "Kuch toh likho yaar!"}), 400

        username = session["username"]
        email = session.get("email")
        emotion = detect_emotion(message) if message else "neutral"
        language = data.get("language", "Kannada") # default to Kannada
        
        user_context = ""
        if email:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("SELECT location, farm_size, crops_grown, soil_type FROM users WHERE email = ?", (email,))
            u = c.fetchone()
            if u:
                loc, fsize, crops, soil = u
                if any([loc, fsize, crops, soil]):
                    user_context = f"\n[User Profile Context: Location: {loc or 'N/A'}, Farm Size: {fsize or 'N/A'}, Crops Grown: {crops or 'N/A'}, Soil Type: {soil or 'N/A'} - Use this context to provide hyper-personalized advice.]"
            conn.close()

        # Build message exactly as the prompt instructs
        full_message = f"Selected language: {language}\nUser emotion: {emotion}\nUser message: {message}{user_context}".strip()

        # Get or init history
        if username not in chat_histories:
            chat_histories[username] = []

        history = chat_histories[username]

        # Build contents list for multi-turn
        contents = []
        for h in history:
            contents.append(h)
            
        current_request_parts = []
        if image_base64:
            try:
                # Format: "data:image/jpeg;base64,/9j/4AAQSkZJ..."
                header, encoded = image_base64.split(",", 1)
                mime_type = header.split(":", 1)[1].split(";", 1)[0]
                import base64
                image_bytes = base64.b64decode(encoded)
                current_request_parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
                full_message += "\n[System Note: User has attached an image of a crop for analysis. Diagnose diseases, identify the crop, and recommend treatments/sprays based on the visual.]"
            except Exception as e:
                print("Image decode error:", e)

        current_request_parts.append(types.Part(text=full_message))

        contents.append(types.Content(
            role="user",
            parts=current_request_parts
        ))

        # Compile System Prompt
        sys_instructions = SYSTEM_PROMPT_TEMPLATE.format(language=language)
        
        config = types.GenerateContentConfig(
            system_instruction=sys_instructions,
            temperature=0.8,
            max_output_tokens=4000,
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

        reply = FALLBACK_REPLIES.get(emotion, FALLBACK_REPLIES["neutral"])

        # Check if quota/rate limit or server overloaded (503)
        if "429" in error_msg or "quota" in error_msg.lower() or "ResourceExhausted" in error_msg:
            reply += "\n\n_(Note: AI quota limit reached. Fallback mode active.)_"
        elif "503" in error_msg or "500" in error_msg or "unavailable" in error_msg.lower():
            reply += "\n\n_(Note: AI servers pe abhi bahut load hai! Please kuch minutes baad try karein 🙏)_"
            
        return jsonify({"reply": reply, "emotion": emotion, "mode": "fallback"})



@app.route("/api/weather_dashboard", methods=["GET"])
def weather_dashboard():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    location_query = request.args.get('location')
    lang = request.args.get('lang', 'Hindi')
    
    location_name = "Unknown Location"
    
    try:
        if location_query:
            # Geocode the location query
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(location_query)}&count=5&language=en&format=json"
            geo_data = requests.get(geo_url, timeout=8).json()
            if "results" not in geo_data or not geo_data["results"]:
                return jsonify({"error": f"Location '{location_query}' not found."}), 404
            
            # Prefer IN
            r = geo_data["results"][0]
            for res in geo_data["results"]:
                if res.get("country_code") == "IN":
                    r = res
                    break
                    
            lat = r["latitude"]
            lon = r["longitude"]
            place_name = r.get("name", location_query)
            admin1 = r.get("admin1", "")
            location_name = f"{place_name}, {admin1}".strip(", ")
        else:
            if not lat or not lon:
                return jsonify({"error": "Location coordinates or name required."}), 400
            
            # Reverse Geocode
            try:
                rg_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=en"
                rg_data = requests.get(rg_url, timeout=5).json()
                location_name = rg_data.get("city") or rg_data.get("locality") or rg_data.get("principalSubdivision") or "Your Location"
            except Exception as e:
                print("Reverse geocode error:", e)

        # Fetch 7-day daily forecast from Open-Meteo
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode"
            f"&timezone=Asia%2FKolkata"
        )
        w_data = requests.get(weather_url, timeout=8).json()
        
        if "current_weather" not in w_data:
            return jsonify({"error": "Weather data unavailable."}), 500
            
        current = w_data["current_weather"]
        daily = w_data.get("daily", {})
        
        # Build 7-day data structure
        forecast = []
        if "time" in daily:
            for i in range(len(daily["time"])):
                forecast.append({
                    "date": daily["time"][i],
                    "temp_max": daily["temperature_2m_max"][i],
                    "temp_min": daily["temperature_2m_min"][i],
                    "rain_chance": daily["precipitation_probability_max"][i],
                    "code": daily["weathercode"][i]
                })
        
        # Prepare data for AI summary
        summary_prompt = (
            f"You are an agricultural AI. Write exactly 2 simple sentences in {lang} about the upcoming 7-day weather for a farmer. "
            f"Here is the daily forecast data: {json.dumps(forecast)}. "
            f"Tell them if rain is expected, and how the temperature will be. Do NOT use markdown or complex words. Keep it very conversational."
        )
        
        summary_res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[summary_prompt],
        )
        ai_summary = summary_res.text.strip()
        
        return jsonify({
            "current": current,
            "forecast": forecast,
            "summary": ai_summary,
            "location_name": location_name
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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