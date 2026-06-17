try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import os
import glob
from PyPDF2 import PdfReader
import chromadb
DB_PATH = "./chroma_db"
DATA_DIR = "./data"

# Initialize ChromaDB
chroma_client = chromadb.PersistentClient(path=DB_PATH)

def extract_text_from_data():
    documents = []
    metadata = []
    
    files = glob.glob(os.path.join(DATA_DIR, "*.pdf")) + glob.glob(os.path.join(DATA_DIR, "*.txt"))
    if not files:
        return [], []

    for file_path in files:
        filename = os.path.basename(file_path)
        content = ""
        print(f"Reading: {filename}...")
        
        if file_path.endswith(".pdf"):
            try:
                reader = PdfReader(file_path)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        content += extracted + "\n"
            except Exception as e:
                print(f"Error reading PDF {filename}: {e}")
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

        if content.strip():
            # Split content into ~800 character chunks with overlap
            chunk_size = 800
            overlap = 150
            for i in range(0, len(content), chunk_size - overlap):
                chunk = content[i:i+chunk_size]
                if len(chunk.strip()) > 50:
                    documents.append(chunk)
                    metadata.append({"source": filename, "chunk": str(i)})
                        
    return documents, metadata

def build():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"Created '{DATA_DIR}' folder. Please place some PDFs/text files inside it and run again.")
        return

    docs, meta = extract_text_from_data()
    if not docs:
        print(f"No documents found or they are empty. Add PDF/txt files to the '{DATA_DIR}' folder.")
        return

    print(f"Extracted {len(docs)} text chunks. Generating Local Embeddings by ONNX ChromaDB Model...")
    
    ids = [f"doc_{j}" for j in range(len(docs))]
    
    try:
        chroma_client.delete_collection("kisan_knowledge")
    except:
        pass
    
    collection = chroma_client.create_collection("kisan_knowledge")
        
    collection.add(
        documents=docs,
        metadatas=meta,
        ids=ids
    )
    print("Database successfully built! The agent can now answer using this knowledge.")

if __name__ == "__main__":
    build()
