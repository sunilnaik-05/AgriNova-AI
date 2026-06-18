try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import sqlite3

from flask import Flask, request, jsonify, session, render_template, redirect, url_for, flash, send_from_directory, abort
from flask_cors import CORS
import os
import traceback
from datetime import timedelta, datetime
import requests
import json
import pymongo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import secrets
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv(override=True)

# Configure Gemini (new SDK)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# data.gov.in Agmarknet API key (free — register at https://data.gov.in/user/register)
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY")

# Email configuration (Gmail SMTP)
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

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
    # ── Crop name normalizer (Hindi/local → English for Agmarknet API) ──
    CROP_MAP = {
        "gehu": "Wheat",       "wheat": "Wheat",
        "chawal": "Rice",      "rice": "Rice",
        "dhaan": "Paddy",      "paddy": "Paddy",
        "soyabean": "Soyabean","soya": "Soyabean",
        "pyaj": "Onion",       "onion": "Onion",  "kanda": "Onion",
        "tamatar": "Tomato",   "tomato": "Tomato",
        "sarso": "Mustard",    "mustard": "Mustard",
        "kapas": "Cotton",     "cotton": "Cotton",
        "makai": "Maize",      "maize": "Maize",  "corn": "Maize",
        "chana": "Gram",       "gram": "Gram",    "chickpea": "Gram",
        "arhar": "Arhar (Tur/Red Gram)(Whole)", "tur": "Arhar (Tur/Red Gram)(Whole)",
        "bajra": "Bajra",      "jowar": "Jowar",
        "aloo": "Potato",      "potato": "Potato",
    }
    # Government MSP / reference prices (fallback only)
    MSP_PRICES = {
        "Wheat": 2275, "Rice": 2183, "Paddy": 2183,
        "Soyabean": 4600, "Onion": 1800, "Tomato": 1500,
        "Mustard": 5650, "Cotton": 7121, "Maize": 2090,
        "Gram": 5440, "Arhar (Tur/Red Gram)(Whole)": 7000,
        "Bajra": 2500, "Jowar": 3180, "Potato": 800,
    }

    crop_lower = crop.lower().strip()
    api_crop_name = crop.strip()  # default: use as-is
    for k, v in CROP_MAP.items():
        if k in crop_lower:
            api_crop_name = v
            break

    # ── Try live data.gov.in Agmarknet API ──────────────────────────────
    if DATA_GOV_API_KEY:
        try:
            params = {
                "api-key": DATA_GOV_API_KEY,
                "format": "json",
                "limit": 5,
                "filters[commodity]": api_crop_name,
            }
            # If state name given, filter by it too
            if state_or_city:
                params["filters[state]"] = state_or_city.title()

            resp = requests.get(
                "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070",
                params=params,
                timeout=10
            )
            data = resp.json()
            records = data.get("records", [])

            if records:
                rec = records[0]  # most recent record
                modal_price = rec.get("modal_price") or rec.get("Modal_Price", "N/A")
                min_price   = rec.get("min_price")   or rec.get("Min_Price", "N/A")
                max_price   = rec.get("max_price")   or rec.get("Max_Price", "N/A")
                market      = rec.get("market")      or rec.get("Market", state_or_city)
                state       = rec.get("state")       or rec.get("State", "")
                arr_date    = rec.get("arrival_date") or rec.get("Arrival_Date", "Today")

                return {
                    "crop": crop,
                    "location": f"{market}, {state}".strip(", "),
                    "price_per_quintal_in_rupees": modal_price,
                    "min_price": min_price,
                    "max_price": max_price,
                    "arrival_date": arr_date,
                    "source": "data.gov.in (Agmarknet — Government of India)",
                    "market_status": "✅ Live government mandi data"
                }
            else:
                return {
                    "crop": crop,
                    "location": state_or_city,
                    "market_status": f"No Agmarknet records found for '{api_crop_name}' in '{state_or_city}'. Try a different state name (e.g., Karnataka, Punjab).",
                    "source": "data.gov.in"
                }
        except Exception as e:
            print(f"Mandi API error: {e}")
            # Fall through to MSP fallback

    # ── Fallback: MSP reference prices with honest disclaimer ───────────
    ref_price = MSP_PRICES.get(api_crop_name, 2000)
    return {
        "crop": crop,
        "location": state_or_city,
        "price_per_quintal_in_rupees": ref_price,
        "source": "Government MSP 2024-25 (Reference only)",
        "market_status": "⚠️ Estimated MSP price — Set DATA_GOV_API_KEY in .env for live Agmarknet data.",
        "note": "Register free at https://data.gov.in/user/register to get real prices."
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

CRITICAL RULE FOR GENERAL QUESTIONS, DISEASES & IMAGES:
If the user asks any question (including crops like sugarcane, farming techniques, diseases, or attaches an image), you should check `search_kisan_database`. BUT if the search returns no relevant information or says 'No specific info found', DO NOT apologize and do NOT say that the database doesn't have the info. INSTEAD, use your own vast agricultural knowledge to answer the user's question fully, accurately, and in detail.

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

# In-memory chat history per user is removed, we use MongoDB instead.

import urllib.parse
import certifi

# Setup MongoDB client
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://sunilnaik4582_db_user:R6uLDQUnsk0OQ4AD@cluster0.e1kabzk.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
mongo_client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = mongo_client["agrinova_db"]
users_collection = db["users"]
chat_history_collection = db["chat_histories"]

def init_db():
    # MongoDB creates collections automatically. We just ensure email is unique.
    users_collection.create_index("email", unique=True)

init_db()

# Create Flask app
app = Flask(__name__, static_folder="frontend", static_url_path="", template_folder="frontend/login/templates")

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

app.secret_key = os.getenv("SECRET_KEY", "fallback-dev-key-change-in-production")
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

# Upload folder configuration and file utilities
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'frontend', 'login', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp",
    "mp4", "mov", "mkv", "avi",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "zip", "rar"
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_user_folder(username):
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_files(username):
    user_folder = ensure_user_folder(username)
    files_info = []
    total_size = 0
    if not os.path.exists(user_folder):
        return files_info, total_size
    for filename in os.listdir(user_folder):
        filepath = os.path.join(user_folder, filename)
        if os.path.isfile(filepath):
            file_stat = os.stat(filepath)
            file_type = filename.split('.')[-1].lower() if '.' in filename else ''
            files_info.append({
                'name': filename,
                'size': file_stat.st_size,
                'modified': file_stat.st_mtime,
                'type': file_type
            })
            total_size += file_stat.st_size
    return files_info, total_size

def send_password_reset_email(user_email, username, reset_token):
    """Send password reset email via Gmail SMTP."""
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        return False, "Email configuration not set on server."

    reset_url = f"http://127.0.0.1:5000/reset-password?token={reset_token}"
    expiry_text = "1 hour"
    subject = "🔑 AgriNova AI — Password Reset Request"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; background:#f4f4f4; padding:2rem;">
        <div style="max-width:480px; margin:auto; background:#ffffff; padding:2rem; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.1);">
            <h2 style="color:#1a73e8; text-align:center;">AgriNova AI</h2>
            <p>Hello <strong>{username}</strong>,</p>
            <p>We received a request to reset your password. Click the button below to choose a new password:</p>
            <p style="text-align:center; margin:2rem 0;">
                <a href="{reset_url}"
                   style="background:#1a73e8; color:#ffffff; padding:12px 28px; border-radius:8px; text-decoration:none; font-weight:600; display:inline-block;">
                    🔒 Reset Password
                </a>
            </p>
            <p style="font-size:0.9rem; color:#666;">
                This link expires in <strong>{expiry_text}</strong>.<br>
                If you didn't request this, you can safely ignore this email — your password won't change.
            </p>
            <hr style="border:none; border-top:1px solid #eee; margin:1.5rem 0;" />
            <p style="font-size:0.8rem; color:#999;">AgriNova AI — Your Smart Farming Assistant</p>
        </div>
    </body>
    </html>
    """

    import base64 # already imported at top but just in case
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = user_email

    part = MIMEText(html_body, "html")
    msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

@app.route("/check_auth", methods=["GET"])
def check_auth():
    if 'email' in session or 'username' in session:
        email = session.get('email')
        profile_image = None
        if email:
            user = users_collection.find_one({"email": email})
            if user:
                profile_image = user.get("profile_image")
            
        return jsonify({
            'authenticated': True, 
            'username': session.get('username', 'User'),
            'profile_image': profile_image
        })
    return jsonify({'authenticated': False})

@app.route("/login", methods=["GET", "POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        response = jsonify({"status": "preflight"})
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    if request.method == "GET":
        if 'username' in session or 'email' in session:
            return redirect(url_for('dashboard'))
        return render_template('login.html')

    # POST: handle login (AJAX or regular form)
    is_ajax = request.is_json  # fetch with JSON payload => AJAX

    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or data.get("username") or "").strip()
    password = data.get("password", "").strip()

    user = users_collection.find_one({"email": email})

    if user and check_password_hash(user["password_hash"], password):
        session.permanent = True
        session["username"] = user.get("name", "")
        session["email"] = email
        if is_ajax:
            return jsonify({
                "status": "success",
                "username": user.get("name", ""),
                "profile_image": user.get("profile_image"),
                "message": "Login successful"
            })
        else:
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
    else:
        if is_ajax:
            return jsonify({"status": "error", "error": "Invalid email or password"}), 401
        else:
            flash("Invalid email or password", "error")
            return redirect(url_for('login'))
    
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
        users_collection.insert_one({
            "name": name,
            "location": location,
            "mobile": mobile,
            "email": email,
            "password_hash": hashed_password,
            "created_at": datetime.now()
        })
        return jsonify({"status": "success", "message": "Registration successful"})
    except pymongo.errors.DuplicateKeyError:
        return jsonify({"status": "error", "error": "Email already exists! Please login instead."}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/profile", methods=["GET"])
def get_profile():
    if "email" not in session:
        return jsonify({"status": "error", "error": "Not authenticated"}), 401
    
    user = users_collection.find_one({"email": session["email"]})
    
    if user:
        return jsonify({
            "status": "success",
            "profile": {
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                "mobile": user.get("mobile", ""),
                "location": user.get("location", ""),
                "profile_image": user.get("profile_image", ""),
                "farm_size": user.get("farm_size", ""),
                "crops_grown": user.get("crops_grown", ""),
                "soil_type": user.get("soil_type", ""),
                "default_language": user.get("default_language", "Kannada")
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
    
    update_data = {
        "name": name,
        "mobile": mobile,
        "location": location,
        "profile_image": profile_image,
        "farm_size": farm_size,
        "crops_grown": crops_grown,
        "soil_type": soil_type,
        "default_language": default_language
    }

    try:
        if password:
            update_data["password_hash"] = generate_password_hash(password)
            
        users_collection.update_one(
            {"email": email},
            {"$set": update_data}
        )
        
        session["username"] = name # Update session if name changed
        return jsonify({"status": "success", "message": "Profile updated successfully"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/logout", methods=["GET", "POST"])
def logout():
    username = session.pop('username', None)
    if username:
        pass # We no longer delete history on logout
    if request.method == "POST":
        return jsonify({"status": "success"})
    else:
        return redirect(url_for('index'))


# ── Password Reset Routes ─────────────────────────────────────────────────────
@app.route("/api/forgot_password", methods=["POST", "OPTIONS"])
def forgot_password():
    """Request a password reset link by email."""
    if request.method == "OPTIONS":
        response = jsonify({"status": "preflight"})
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

    data = request.get_json(silent=True) or request.form
    email = data.get("email", "").strip()

    if not email:
        return jsonify({"status": "error", "error": "Email is required"}), 400

    user = users_collection.find_one({"email": email})

    if not user:
        return jsonify({"status": "success", "message": "If an account exists with that email, you will receive a password reset link."})

    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    expiry = (datetime.utcnow() + timedelta(hours=1)).isoformat()

    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"reset_token": reset_token, "reset_token_expiry": expiry}}
    )

    success, msg = send_password_reset_email(email, user.get("name", ""), reset_token)

    return jsonify({"status": "success", "message": "If an account exists with that email, you will receive a password reset link."})


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.args.get("token") if request.method == "GET" else request.form.get("token")
    if request.method == "GET":
        if not token:
            flash("Invalid reset link.", "error")
            return redirect(url_for('login'))
        user = users_collection.find_one({"reset_token": token})
        if not user:
            flash("Invalid or expired reset link.", "error")
            return redirect(url_for('login'))
        expiry = datetime.fromisoformat(user.get("reset_token_expiry")) if user.get("reset_token_expiry") else None
        if expiry and expiry < datetime.utcnow():
            flash("This reset link has expired. Please request a new one.", "error")
            return redirect(url_for('login'))
        return render_template("reset_password.html", token=token, username=user.get("name", ""))
    # POST
    token = request.form.get("token", "").strip()
    new_password = request.form.get("password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()
    if not new_password or new_password != confirm_password:
        return render_template("reset_password.html", token=token, error="Passwords do not match.", username="User")
    if len(new_password) < 6:
        return render_template("reset_password.html", token=token, error="Password must be at least 6 characters.", username="User")
    user = users_collection.find_one({"reset_token": token})
    if not user:
        return render_template("reset_password.html", token=token, error="Invalid reset link.", username="User")
    expiry = datetime.fromisoformat(user.get("reset_token_expiry")) if user.get("reset_token_expiry") else None
    if expiry and expiry < datetime.utcnow():
        return render_template("reset_password.html", token=token, error="Reset link expired.", username="User")
    hashed = generate_password_hash(new_password)
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hashed}, "$unset": {"reset_token": "", "reset_token_expiry": ""}}
    )
    flash("Password reset successful! You can now log in.", "success")
    return redirect(url_for('index'))


@app.route("/api/reset_password", methods=["POST", "OPTIONS"])
def api_reset_password():
    if request.method == "OPTIONS":
        response = jsonify({"status": "preflight"})
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    data = request.get_json(silent=True) or request.form
    token = data.get("token", "").strip()
    new_password = data.get("password", "").strip()
    if not token or not new_password:
        return jsonify({"status": "error", "error": "Token and password are required"}), 400
    if len(new_password) < 6:
        return jsonify({"status": "error", "error": "Password must be at least 6 characters"}), 400
    user = users_collection.find_one({"reset_token": token})
    if not user:
        return jsonify({"status": "error", "error": "Invalid reset link"}), 400
    expiry = datetime.fromisoformat(user.get("reset_token_expiry")) if user.get("reset_token_expiry") else None
    if expiry and expiry < datetime.utcnow():
        return jsonify({"status": "error", "error": "Reset link expired"}), 400
    hashed = generate_password_hash(new_password)
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hashed}, "$unset": {"reset_token": "", "reset_token_expiry": ""}}
    )
    return jsonify({"status": "success", "message": "Password reset successful"})


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
            u = users_collection.find_one({"email": email})
            if u:
                loc = u.get("location")
                fsize = u.get("farm_size")
                crops = u.get("crops_grown")
                soil = u.get("soil_type")
                if any([loc, fsize, crops, soil]):
                    user_context = f"\n[User Profile Context: Location: {loc or 'N/A'}, Farm Size: {fsize or 'N/A'}, Crops Grown: {crops or 'N/A'}, Soil Type: {soil or 'N/A'} - Use this context to provide hyper-personalized advice.]"


        # Build message exactly as the prompt instructs
        full_message = f"Selected language: {language}\nUser emotion: {emotion}\nUser message: {message}{user_context}".strip()

        # Get or init history
        # Get or init history from MongoDB
        user_history_doc = chat_history_collection.find_one({"username": username})
        history = []
        if user_history_doc and "history" in user_history_doc:
            # Reconstruct types.Content
            for msg in user_history_doc["history"]:
                role = msg.get("role")
                parts = [types.Part(text=p) for p in msg.get("parts", [])]
                history.append(types.Content(role=role, parts=parts))

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

        def generate_with_fallback(contents, config):
            models_to_try = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-1.5-flash"]
            last_error = None
            for m in models_to_try:
                try:
                    return client.models.generate_content(model=m, contents=contents, config=config, http_options={"timeout": 12.0})
                except Exception as e:
                    print(f"Fallback warning: Model {m} failed: {e}")
                    last_error = e
                    continue
            raise last_error


        # Call Gemini new SDK
        response = generate_with_fallback(contents, config)
        
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
            response = generate_with_fallback(contents, config)
            calls += 1

        reply = response.text
        
        # We no longer strictly need create_ssml since frontend cleans raw text
        ssml_reply = reply

        # Save to history (we save the clean reply visually, or we can save the SSML)
        # We will save the SSML; the frontend will parse it securely
        # Append to the history list
        history.append(types.Content(
            role="user",
            parts=[types.Part(text=full_message)]
        ))
        history.append(types.Content(
            role="model",
            parts=[types.Part(text=reply)]
        ))

        # Keep history trimmed (last 20 exchanges)
        if len(history) > 40:
            history = history[-40:]
            
        # Serialize history for MongoDB
        serialized_history = []
        for h in history:
            serialized_history.append({
                "role": h.role,
                "parts": [p.text for p in h.parts if p.text]
            })
            
        chat_history_collection.update_one(
            {"username": username},
            {"$set": {"history": serialized_history}},
            upsert=True
        )

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
        
        try:
            summary_res = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[summary_prompt],
            )
            ai_summary = summary_res.text.strip()
        except Exception as e:
            print(f"Gemini Weather Summary Error: {e}")
            # Fallback summary logic
            max_temp = max([f['temp_max'] for f in forecast]) if forecast else "N/A"
            min_temp = min([f['temp_min'] for f in forecast]) if forecast else "N/A"
            will_rain = any([f['rain_chance'] > 40 for f in forecast])
            
            if lang == "Hindi":
                rain_text = "kuch din baarish ki sambhavna hai" if will_rain else "mausam saaf rahega"
                ai_summary = f"Agle 7 dino mein tapman {min_temp}°C se {max_temp}°C ke beech rahega aur {rain_text}. Kripya apni fasal ka dhyan rakhein."
            elif lang == "Kannada":
                rain_text = "ಕೆಲವು ದಿನ ಮಳೆಯಾಗುವ ಸಾಧ್ಯತೆಯಿದೆ" if will_rain else "ಹವಾಮಾನವು ಸ್ಪಷ್ಟವಾಗಿರುತ್ತದೆ"
                ai_summary = f"ಮುಂದಿನ 7 ದಿನಗಳಲ್ಲಿ ತಾಪಮಾನವು {min_temp}°C ರಿಂದ {max_temp}°C ವರೆಗೆ ಇರುತ್ತದೆ ಮತ್ತು {rain_text}. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಬೆಳೆಯ ಬಗ್ಗೆ ಕಾಳಜಿ ವಹಿಸಿ."
            else:
                rain_text = "some rain is expected" if will_rain else "the weather will be mostly clear"
                ai_summary = f"In the next 7 days, temperatures will range from {min_temp}°C to {max_temp}°C and {rain_text}. Please take care of your crops."
        
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
    if username:
        chat_history_collection.delete_one({"username": username})

    return jsonify({"status": "success"})


# ── Dashboard / File Manager Routes ───────────────────────────────────────────
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            user_folder = ensure_user_folder(session['username'])
            file.save(os.path.join(user_folder, filename))
            flash('File uploaded successfully', 'success')
        else:
            flash('Invalid file type', 'error')
        return redirect(url_for('dashboard'))
    files, _ = get_user_files(session['username'])
    images_ext = {'jpg','jpeg','png','gif','webp'}
    videos_ext = {'mp4','mov','mkv','avi'}
    docs_ext = {'pdf','doc','docx','xls','xlsx','ppt','pptx','txt','zip','rar'}
    photos = [f for f in files if f['type'].lower() in images_ext]
    videos_list = [f for f in files if f['type'].lower() in videos_ext]  # renamed to avoid conflict with videos route
    docs = [f for f in files if f['type'].lower() in docs_ext]
    return render_template('dashboard.html',
                           username=session.get('username'),
                           photos_count=len(photos),
                           videos_count=len(videos_list),
                           docs_count=len(docs))

@app.route('/photos')
def photos():
    if 'username' not in session:
        return redirect(url_for('index'))
    files, _ = get_user_files(session['username'])
    images_ext = {'jpg','jpeg','png','gif','webp'}
    images = [f for f in files if f['type'].lower() in images_ext]
    for f in images:
        f['view_url'] = url_for('serve_upload', username=session['username'], filename=f['name'])
        f['display_name'] = os.path.splitext(f['name'])[0]
    return render_template('photos.html', files=images, username=session.get('username'))

@app.route('/videos')
def videos():
    if 'username' not in session:
        return redirect(url_for('index'))
    files, _ = get_user_files(session['username'])
    videos_ext = {'mp4','mov','mkv','avi'}
    video_files = [f for f in files if f['type'].lower() in videos_ext]
    for f in video_files:
        f['view_url'] = url_for('serve_upload', username=session['username'], filename=f['name'])
        f['display_name'] = os.path.splitext(f['name'])[0]
    return render_template('videos.html', files=video_files, username=session.get('username'))

@app.route('/docs')
def docs():
    if 'username' not in session:
        return redirect(url_for('index'))
    files, _ = get_user_files(session['username'])
    docs_ext = {'pdf','doc','docx','xls','xlsx','ppt','pptx','txt','zip','rar'}
    doc_files = [f for f in files if f['type'].lower() in docs_ext]
    for f in doc_files:
        f['view_url'] = url_for('serve_upload', username=session['username'], filename=f['name'])
        f['display_name'] = os.path.splitext(f['name'])[0]
    return render_template('docs.html', files=doc_files, username=session.get('username'))

@app.route('/delete', methods=['POST'])
def delete_multiple():
    if 'username' not in session:
        return redirect(url_for('index'))
    filenames = request.form.getlist('selected_files')
    if not filenames:
        flash('No files selected', 'info')
        return redirect(request.referrer or url_for('dashboard'))
    user_folder = ensure_user_folder(session['username'])
    deleted = 0
    for fname in filenames:
        fpath = os.path.join(user_folder, fname)
        if os.path.exists(fpath):
            os.remove(fpath)
            deleted += 1
    flash(f'Deleted {deleted} file(s)', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/uploads/<username>/<filename>')
def serve_upload(username, filename):
    if 'username' not in session or session['username'] != username:
        abort(403)
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], username), filename)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)