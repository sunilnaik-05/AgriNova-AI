
import sys

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_imports = [
    "from dotenv import load_dotenv\n",
    "from google import genai\n",
    "from google.genai import types\n"
]

# Insert after line 14 (which is index 13)
# Line 14 is 'import secrets'
for i, line in enumerate(lines):
    if 'import secrets' in line:
        lines.insert(i + 1, "".join(new_imports))
        break

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
