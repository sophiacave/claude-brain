#!/usr/bin/env python3
"""claude-brain status — Show brain health, vector counts, and stats."""

import json
import sqlite3
import sys
from pathlib import Path

import chromadb
import requests


def main():
    brain_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".claude-brain"
    config_path = brain_dir / "config.json"

    print("claude-brain status\n")

    # Brain directory
    if not brain_dir.exists():
        print(f"  Brain not initialized. Run: claude-brain init")
        return
    print(f"  Brain: {brain_dir}")

    # Config
    if config_path.exists():
        config = json.loads(config_path.read_text())
        print(f"  Model: {config.get('embed_model', '?')}")
        print(f"  Ollama: {config.get('ollama_url', '?')}")
    else:
        config = {"ollama_url": "http://localhost:11434"}

    # Ollama status
    try:
        resp = requests.get(f"{config['ollama_url']}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        has_embed = any("mxbai-embed-large" in m for m in models)
        print(f"  Ollama: ONLINE ({len(models)} models, embed={'YES' if has_embed else 'MISSING'})")
    except Exception:
        print("  Ollama: OFFLINE")

    # Brain DB
    db_path = brain_dir / "brain.db"
    if db_path.exists():
        db = sqlite3.connect(str(db_path))
        entries = db.execute("SELECT COUNT(*) FROM brain_context").fetchone()[0]
        try:
            embedded = db.execute("SELECT COUNT(*) FROM brain_embed_log").fetchone()[0]
        except Exception:
            embedded = 0
        try:
            sessions = db.execute("SELECT COUNT(*) FROM brain_sessions").fetchone()[0]
        except Exception:
            sessions = 0
        try:
            skills = db.execute("SELECT COUNT(*) FROM brain_skills").fetchone()[0]
        except Exception:
            skills = 0
        db.close()
        print(f"  Brain DB: {entries} entries, {embedded} embedded, {sessions} sessions, {skills} skills")
    else:
        print("  Brain DB: not found")

    # ChromaDB
    chroma_path = brain_dir / "vector_store"
    if chroma_path.exists():
        client = chromadb.PersistentClient(path=str(chroma_path))
        cols = client.list_collections()
        total = 0
        print(f"  ChromaDB: {len(cols)} collections")
        for col in cols:
            n = col.count()
            total += n
            print(f"    {col.name}: {n} vectors")
        print(f"  Total vectors: {total}")
    else:
        print("  ChromaDB: not initialized")

    print()


if __name__ == "__main__":
    main()
