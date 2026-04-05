AgriNova AI

AgriNova AI is a simple chatbot project designed to help users (especially farmers) get quick and easy answers. The idea behind this project is to make conversations feel natural, like talking to a real person instead of a robot.

The chatbot supports both text and voice interaction and can respond in multiple languages.


What this project does

Sometimes, getting useful information quickly can be difficult, especially when language becomes a barrier. This project tries to solve that by:

* Giving clear and simple answers
* Supporting local languages like Kannada and Hindi
* Allowing both text and voice input
* Responding in a more human and friendly way


Features

* Text + Voice input
* Voice output (Text-to-Speech)
* Multi-language support (Kannada, Hindi, English)
* Emotion-based responses
* Simple and clean interface


How to run

1. Clone the repository

```bash
git clone https://github.com/sunilnaik4582-jpg/AgriNova-AI.git
cd AgriNova-AI
```

2. Create a `.env` file

```bash
copy .env.example .env
```

3. Add your API key

```text
GEMINI_API_KEY=your_api_key_here
```

4. Install dependencies

```bash
pip install -r requirements.txt
```

5. Run the project

```bash
python app.py
```


Project structure

app.py
frontend/
test_api.py
.env.example
.gitignore
README.md


Note

The `.env` file is not included in the repository for security reasons.
You need to create it manually and add your own API key.


Future improvements# AgriNova AI

AgriNova AI is an intelligent agriculture assistant designed to provide real-time, context-aware, and human-like guidance to farmers. It leverages advanced AI techniques such as Agentic AI, Function Calling, and Retrieval-Augmented Generation (RAG) to deliver accurate and practical solutions.

The chatbot supports both voice and text interaction and can communicate in multiple languages like Hindi, Kannada, and English, making it accessible to a wider range of users.

---

Features

* Natural conversational chatbot (human-like responses)
* Voice input and voice output (Text-to-Speech)
* Multi-language support (Hindi, Kannada, English)
* Emotion-aware responses
* Function calling (real-time weather and mandi data)
* RAG-based knowledge system (expert agriculture data)
* Farmer-friendly interface

---

Advanced AI Capabilities

* Agentic AI workflow for multi-step reasoning and decision-making
* Function calling to fetch real-time external data (weather, market prices)
* Retrieval-Augmented Generation (RAG) using agriculture documents
* Context-aware and intent-aware conversation handling

---

Tech Stack

* Backend: Python
* Frontend: HTML, CSS, JavaScript
* LLM: Gemini API
* Vector Database: ChromaDB
* Speech: Text-to-Speech (TTS)
* Embeddings: Used for RAG pipeline

---

Architecture

User Input → LLM →
(Function Call: Weather / Mandi)
(RAG: Knowledge Retrieval)
→ Response Generation → Voice Output

---

Project Structure

AgriNova-AI/

├── app.py
├── build_db.py
├── requirements.txt
├── frontend/
├── data/ (PDFs for RAG, not included)
├── chroma_db/ (auto-generated, ignored)
├── test_agent.py
├── .env.example
├── .gitignore
└── README.md

Environment Variables

The `.env` file is not included in this repository for security reasons. It may contain sensitive information such as API keys.

After cloning the project, you need to create a `.env` file in the root directory and add your API key:

GEMINI_API_KEY=your_api_key_here

Make sure not to share or upload your `.env` file to GitHub.

---

.gitignore

This project uses a `.gitignore` file to prevent sensitive and unnecessary files from being uploaded to the repository.

The following files and folders are ignored:

* `.env` – Contains API keys and secrets
* `chroma_db/` – Auto-generated vector database (can be recreated)
* `data/*.pdf` – External knowledge files (large and optional)
* `__pycache__/`, `*.pyc` – Python cache files
* `venv/`, `env/` – Virtual environment folders
* `server.log` – Log files
* `.ipynb_checkpoints/` – Jupyter notebook auto-saves

These files are excluded to keep the repository secure, lightweight, and easy to manage.

---

Setup Notes

If the project does not run correctly, make sure you have:

* Created the `.env` file with your API key
* Added required PDF files inside the `data/` folder
* Built the vector database using:

python build_db.py


## How to Run

1. Clone the repository

git clone https://github.com/sunilnaik4582-jpg/AgriNova-AI.git
cd AgriNova-AI

2. Create a .env file

copy .env.example .env

Add your API key:
GEMINI_API_KEY=your_api_key_here

---

 3. Install dependencies

pip install -r requirements.txt

---

 4. Add knowledge base (RAG)

* Download agriculture PDFs (crop guides, disease management, schemes)
* Place them inside the `data/` folder

---

5. Build vector database

python build_db.py

---

6. Run the application

python app.py

---

Important Notes

* Do not upload your `.env` file
* `chroma_db/` will be generated automatically
* Add your own PDFs inside `data/` for RAG functionality

---

Future Improvements

* Integration with real-time government mandi APIs
* Image-based crop disease detection
* Personalized farmer memory system
* Mobile-friendly interface
* Offline support for rural areas

---

Why this project matters

This project demonstrates real-world application of modern AI techniques such as RAG, function calling, and conversational AI design in the agriculture domain. It focuses on making AI accessible, practical, and useful for farmers.

---

Contribution

Contributions are welcome. Feel free to fork the repository and submit a pull request.


* Better voice quality
* More local languages
* Mobile-friendly version
* Smarter emotion detection


Final note

This project is built as a practical experiment to make AI more accessible and human-like.
If you have ideas or want to improve it, feel free to contribute.

