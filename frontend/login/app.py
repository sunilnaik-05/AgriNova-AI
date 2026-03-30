import os
import time
import mimetypes
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify, send_from_directory
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-123")

# ================== CONFIG ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

# App configuration
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=3600,  # 1 hour
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,  # 100MB
    UPLOAD_FOLDER=UPLOAD_FOLDER
)

# Demo credentials
VALID_USERNAME = "admin"
VALID_PASSWORD = "1234"

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp",
    "mp4", "mov", "mkv", "avi",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "zip", "rar"
}

# ============= HELPER FUNCTIONS =============
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_user_folder(username):
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_files(username):
    user_folder = ensure_user_folder(username)
    files_info = []
    total_size = 0
    
    for filename in os.listdir(user_folder):
        filepath = os.path.join(user_folder, filename)
        if os.path.isfile(filepath):
            file_stat = os.stat(filepath)
            file_type = filename.split('.')[-1].lower()
            files_info.append({
                'name': filename,
                'size': file_stat.st_size,
                'modified': file_stat.st_mtime,
                'type': file_type
            })
            total_size += file_stat.st_size
    
    return files_info, total_size

# ================== ROUTES ===================
@app.route("/")
def index():
    return app.send_static_file('index.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Get form data
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        # Debug print
        print(f"Login attempt - Username: {username}, Password: {password}")
        
        # Simple authentication (replace with your actual authentication logic)
        if username == "admin" and password == "1234":
            # Set session
            session['user'] = username
            session['logged_in'] = True
            
            # Create user folder if it doesn't exist
            session["user"] = username
            ensure_user_folder(username)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    "status": "success",
                    "username": username
                })
                
            flash("Login successful!", "success")
            return redirect(url_for("chat"))
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    "status": "error",
                    "error": "Invalid username or password"
                }), 401
            flash("Invalid username or password", "error")
    
    if "user" in session:
        return redirect(url_for("chat"))
    return render_template("login.html")

@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect(url_for("login"))
    return app.send_static_file('index.html')

@app.route("/api/chat", methods=["POST"])
def chat_api():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = request.get_json()
    message = data.get("message", "")
    
    # Here you would typically process the chat message with your AI
    return jsonify({
        "reply": f"Echo: {message}",
        "status": "success"
    })

@app.route("/check_auth")
def check_auth():
    if "user" in session:
        return jsonify({
            "authenticated": True,
            "username": session["user"]
        })
    return jsonify({"authenticated": False})

@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return jsonify({
        "status": "success",
        "message": "Logged out successfully"
    })

# API endpoint to get user files
@app.route("/api/files")
def get_files():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    files, total_size = get_user_files(session["user"])
    return jsonify({
        "files": files,
        "total_size": total_size
    })

# Static file serving
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# Add CORS headers
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, port=5000)