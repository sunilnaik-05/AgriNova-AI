# 🌱 AgriNova AI — Intelligent Agricultural Assistant

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Flask-3.0.3-black?style=for-the-badge&logo=flask" />
  <img src="https://img.shields.io/badge/Gemini-2.0--Flash-orange?style=for-the-badge&logo=google" />
  <img src="https://img.shields.io/badge/ChromaDB-RAG-purple?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

# 🌱 AgriNova AI — Smart Farming Assistant for Indian Farmers

AgriNova AI is a production-ready, full-stack AI assistant that helps farmers make better decisions using real-time weather data, live mandi prices, and AI-powered crop disease detection.

Built with Google Gemini 2.0-Flash, it supports multilingual voice interaction, image-based diagnosis, and local knowledge retrieval — making advanced agricultural intelligence accessible to rural India.

📦 GitHub: [https://github.com/sunilnaik4582-jpg/AgriNova-AI](https://github.com/sunilnaik4582-jpg/AgriNova-AI)
---

## 📸 Screenshots

<table>
  <tr>
    <td align="center" width="50%">
      <img src="screenshots/login_page.png" alt="AgriNova AI Login Page" width="100%" />
      <br/>
      <b>🔐 Login Page</b>
      <br/>
      <sub>Glassmorphism dark-themed secure login with typewriter animation</sub>
    </td>
    <td align="center" width="50%">
      <img src="screenshots/chat_interface.png" alt="AgriNova AI Chat Interface" width="100%" />
      <br/>
      <b>💬 Chat Interface</b>
      <br/>
      <sub>Multilingual AI chat with crop disease diagnosis via image upload</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="screenshots/profile_page.png" alt="AgriNova AI User Profile" width="100%" />
      <br/>
      <b>🧑‍🌾 User Profile</b>
      <br/>
      <sub>Manage farm context (size, crops, soil) for personalized advice</sub>
    </td>
    <td align="center" width="50%">
      <img src="screenshots/weather_dashboard.png" alt="AgriNova AI Weather Dashboard" width="100%" />
      <br/>
      <b>🌤️ Live Weather Dashboard</b>
      <br/>
      <sub>7-day forecast with AI-generated multilingual weather summaries & fail-safe fallbacks</sub>
    </td>
  </tr>
</table>

---

## ✨ Features

### 🤖 AI & Agentic Intelligence
- **Gemini 2.0-Flash** — High-speed Google LLM with multi-turn conversation memory.
- **Agentic Function Calling** — AI autonomously calls tools to fetch live weather and mandi data.
- **RAG (Retrieval-Augmented Generation)** — ChromaDB-powered local knowledge base using expert agriculture PDFs.
- **Multimodal Input** — Upload crop photos for instant visual disease diagnosis and treatment.
- **Emotion-Aware AI** — Detects user frustration or sadness and responds with empathy.

### 🛠️ Real-Time Tools (Agent Actions)
| Tool | Description |
|------|-------------|
| `get_weather` | Live weather via Open-Meteo API. Supports village-level accuracy. |
| `get_mandi_price` | **Live Government Data** via Agmarknet (data.gov.in) API for real-time crop prices. |
| `search_kisan_database` | Searches local ChromaDB vector store for specific agricultural expert data. |

### 📊 Farmer Dashboard & File Manager
- **Personalized Profile** — Store farm size, crops grown, and soil type for tailored AI insights.
- **Secure File Storage** — Integrated dashboard to manage **Photos**, **Videos**, and **Documents**.
- **Responsive Navigation** — Modern sidebar that adapts perfectly to mobile and desktop screens.

### 🗣️ Voice & Language
- **Voice Input** — Seamless Speech-to-Text interaction.
- **Text-to-Speech (TTS)** — Bot replies read aloud in the selected language.
- **Native Support** — Full support for **Kannada (ಕನ್ನಡ)**, **Hindi (हिंदी)**, and **English**.

### 🔐 Advanced Security
- **Email-Based Password Reset** — Secure flow with SMTP email notifications and temporary tokens.
- **Secure Auth** — Password hashing (PBKDF2) and session-based authentication.
- **Data Privacy** — Local SQLite storage for user credentials and profiles.

---

## 🏗️ Project Structure

```
chatbot-project/
│
├── app.py                   # Main Flask backend (API, Auth, Gemini, Function Calling)
├── build_db.py              # Script to build ChromaDB knowledge base from PDFs/TXT
├── view_users.py            # Utility to view registered users from SQLite DB
├── requirements.txt         # Python dependencies
│
├── frontend/
│   ├── index.html           # Main chat UI (sidebar, chat area, voice, image upload)
│   ├── login.html           # Standalone login/register page
│   ├── style.css            # Modern Glassmorphism Design System
│   └── login/               # Dashboard and Profile management components
│       ├── templates/       # Jinja2 templates for Dashboard and Password Reset
│       └── uploads/         # User-specific media storage (Photos/Videos/Docs)
│
├── data/                    # Source documents for RAG (PDFs/TXT)
├── chroma_db/               # Generated Vector Store
├── screenshots/             # Project screenshots for documentation
│
├── .env                     # API keys (GEMINI_API_KEY, DATA_GOV_API_KEY, etc.)
├── .env.example             # Template for environment variables
└── README.md                # This file
```

---

## ⚡ Quick Start

1. **Clone & Install**
   ```bash
   git clone https://github.com/sunilnaik4582-jpg/AgriNova-AI.git
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   Create a `.env` file and add your keys:
   ```
   GEMINI_API_KEY=your_key
   DATA_GOV_API_KEY=your_key
   EMAIL_ADDRESS=your_gmail
   EMAIL_PASSWORD=your_app_password
   ```

3. **Build Knowledge Base**
   ```bash
   python build_db.py
   ```

4. **Launch**
   ```bash
   python app.py
   ```

---

## 🚀 Future Roadmap

- [ ] **Offline Mode** — Support for areas with limited connectivity.
- [ ] **Push Alerts** — Real-time notifications for sudden weather changes.
- [ ] **Crop Calendar** — Automated planting and harvest schedules.
- [ ] **More Languages** — Expanding to Telugu, Tamil, and Marathi.

---

<p align="center">
  Built with ❤️ for Indian Farmers &nbsp;|&nbsp; Powered by Google Gemini &nbsp;|&nbsp; AgriNova AI
</p>
