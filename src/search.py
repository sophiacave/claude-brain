#!/usr/bin/env python3
"""claude-brain search — Semantic search across all brain collections."""

import json
import sys
from pathlib import Path

import chromadb
import requests


def load_config(brain_dir):
    config_path = brain_dir / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {"ollama_url": "http://localhost:11434", "embed_model": "mxbai-embed-large"}


def get_embedding(text, config):
    try:
        resp = requests.post(
            f"{config['ollama_url']}/api/embed",
            json={"model": config["embed_model"], "input": text},
            timeout=30
        )
        if resp.status_code == 200:
            embeddings = resp.json().get("embeddings", [])
            if embeddings:
                return embeddings[0]
    except Exception:
        pass
    return None


def search(brain_dir, query, top_k=10):
    config = load_config(brain_dir)
    chroma_path = brain_dir / "vector_store"

    if not chroma_path.exists():
        print("No vector store found. Run 'claude-brain embed full' first.")
        return

    embedding = get_embedding(query, config)
    if not embedding:
        print("Failed to embed query. Is Ollama running?")
        return

    client = chromadb.PersistentClient(path=str(chroma_path))
    collections = client.list_collections()

    results = []
    for col in collections:
        if col.count() == 0:
            continue
        try:
            r = col.query(query_embeddings=[embedding], n_results=min(5, col.count()))
            for i, doc in enumerate(r["documents"][0]):
                dist = r["distances"][0][i] if r.get("distances") else 0
                meta = r["metadatas"][0][i] if r.get("metadatas") else {}
                results.append({
                    "distance": dist,
                    "collection": col.name,
                    "document": doc[:300],
                    "metadata": meta
                })
        except Exception:
            pass

    results.sort(key=lambda x: x["distance"])
    results = results[:top_k]

    if not results:
        print(f"No results for: {query}")
        return

    print(f"Search: '{query}' ({len(results)} results)\n")
    for r in results:
        src = r["metadata"].get("filename", r["metadata"].get("key", "?"))
        print(f"  [{r['collection']}] {src} (dist={r['distance']:.3f})")
        print(f"    {r['document'][:150]}...")
        print()


def main():
    brain_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".claude-brain"
    query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if not query:
        print("Usage: claude-brain search <query>")
        sys.exit(1)

    search(brain_dir, query)


if __name__ == "__main__":
    main()
