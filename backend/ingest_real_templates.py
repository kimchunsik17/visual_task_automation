import os
import glob
from rag_utils import get_vector_store, RAW_N8N_COLLECTION

def ingest_templates():
    scraped_dir = os.path.join(os.path.dirname(__file__), "scraped_templates")
    if not os.path.exists(scraped_dir):
        print(f"Error: Directory {scraped_dir} not found.")
        return

    json_files = glob.glob(os.path.join(scraped_dir, "**", "*.json"), recursive=True)
    if not json_files:
        print("No .json files found to ingest.")
        return

    print(f"Found {len(json_files)} templates. Starting ingestion into ChromaDB (RAW_N8N_COLLECTION)...")
    
    docs = []
    metadatas = []
    
    for file_path in json_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # extract category and filename for metadata
        rel_path = os.path.relpath(file_path, scraped_dir)
        category = os.path.dirname(rel_path)
        filename = os.path.basename(rel_path)
        name = os.path.splitext(filename)[0]
        
        docs.append(content)
        metadatas.append({"name": name, "category": category})
        
    store = get_vector_store(RAW_N8N_COLLECTION)
    
    # insert in batches to avoid payload size errors
    batch_size = 50
    for i in range(0, len(docs), batch_size):
        batch_docs = docs[i:i+batch_size]
        batch_metas = metadatas[i:i+batch_size]
        store.add_texts(texts=batch_docs, metadatas=batch_metas)
        print(f"Ingested batch {i // batch_size + 1}/{(len(docs) + batch_size - 1) // batch_size}")
        
    print("Ingestion complete!")

if __name__ == "__main__":
    ingest_templates()
