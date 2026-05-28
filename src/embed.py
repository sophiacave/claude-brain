#!/usr/bin/env python3
"""claude-brain embed — Embed brain entries + files into ChromaDB via Ollama."""

import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import chromadb
import requests


def load_config(brain_dir):
    config_path = brain_dir / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {
        "ollama_url": "http://localhost:11434",
        "embed_model": "mxbai-embed-large",
        "collections": ["brain_entries", "memory_files", "sessions", "skills"],
    }


def get_embedding(text, config):
    url = f"{config['ollama_url']}/api/embed"
    for attempt in range(3):
        try:
            resp = requests.post(url, json={
                "model": config["embed_model"],
                "input": text[:1500]
            }, timeout=60)
            if resp.status_code == 200:
                embeddings = resp.json().get("embeddings", [])
                if embeddings:
                    return embeddings[0]
            if attempt < 2:
                time.sleep(0.5)
        except Exception:
            if attempt < 2:
                time.sleep(1)
    return None


def embed_brain_entries(brain_dir, config, mode="new"):
    """Embed entries from brain.db into ChromaDB."""
    db_path = brain_dir / "brain.db"
    if not db_path.exists():
        print("  No brain.db found")
        return 0

    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row

    client = chromadb.PersistentClient(path=str(brain_dir / "vector_store"))
    collection = client.get_or_create_collection(
        name="brain_entries", metadata={"hnsw:space": "cosine"}
    )

    if mode == "new":
        cursor = db.execute("""
            SELECT key, description, value, category, priority
            FROM brain_context
            WHERE key NOT IN (SELECT key FROM brain_embed_log)
            ORDER BY priority DESC LIMIT 50
        """)
    else:
        cursor = db.execute("""
            SELECT key, description, value, category, priority
            FROM brain_context ORDER BY priority DESC
        """)

    entries = cursor.fetchall()
    if not entries:
        print(f"  brain_entries: all embedded ({collection.count()} vectors)")
        db.close()
        return 0

    ts = datetime.now().isoformat()
    embedded = 0

    for entry in entries:
        key = entry["key"]
        desc = entry["description"] or ""
        value = entry["value"] or ""
        val_str = value if isinstance(value, str) else json.dumps(value)

        text = f"{key}: {desc}\n{val_str[:500]}"
        embedding = get_embedding(text, config)
        if not embedding:
            continue

        vector_id = f"brain_{key.replace('.', '_')}"
        collection.upsert(
            ids=[vector_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "key": key,
                "category": entry["category"] or "general",
                "priority": entry["priority"] or 5,
                "source": "brain_context"
            }]
        )

        db.execute("""
            INSERT OR REPLACE INTO brain_embed_log (key, embedded_at, collection, vector_id)
            VALUES (?, ?, ?, ?)
        """, (key, ts, "brain_entries", vector_id))
        embedded += 1
        time.sleep(0.2)

    db.commit()
    db.close()
    print(f"  brain_entries: {embedded} embedded, {collection.count()} total vectors")
    return embedded


def embed_memory_files(brain_dir, config):
    """Embed CLAUDE.md, MEMORY.md, and project memory files."""
    client = chromadb.PersistentClient(path=str(brain_dir / "vector_store"))
    collection = client.get_or_create_collection(
        name="memory_files", metadata={"hnsw:space": "cosine"}
    )

    # Find memory files
    memory_dirs = [
        Path.home() / ".claude" / "projects",
        Path.home(),
    ]
    memory_files = []
    for d in memory_dirs:
        if d.exists():
            memory_files.extend(d.rglob("CLAUDE.md"))
            memory_files.extend(d.rglob("MEMORY.md"))

    # Also check project-specific memory dirs
    for proj_dir in (Path.home() / ".claude" / "projects").glob("*"):
        mem_dir = proj_dir / "memory"
        if mem_dir.exists():
            memory_files.extend(mem_dir.glob("*.md"))

    # Deduplicate
    seen = set()
    unique_files = []
    for f in memory_files:
        if str(f) not in seen:
            seen.add(str(f))
            unique_files.append(f)

    hash_file = brain_dir / "embed_hashes.json"
    hashes = json.loads(hash_file.read_text()) if hash_file.exists() else {}

    embedded = 0
    for fp in unique_files:
        if not fp.exists():
            continue
        fh = hashlib.md5(fp.read_bytes()).hexdigest()
        hash_key = f"memory:{fp.name}"
        if hashes.get(hash_key) == fh:
            continue

        text = fp.read_text(errors="ignore")[:1500]
        if not text.strip():
            continue

        embedding = get_embedding(f"{fp.stem}: {text}", config)
        if not embedding:
            continue

        vector_id = f"mem_{fp.stem.replace('.', '_').replace('-', '_')}"
        collection.upsert(
            ids=[vector_id],
            embeddings=[embedding],
            documents=[f"{fp.stem}: {text[:500]}"],
            metadatas=[{
                "source": "memory_files",
                "filename": fp.name,
                "path": str(fp),
                "updated": datetime.now().isoformat()
            }]
        )
        hashes[hash_key] = fh
        embedded += 1
        time.sleep(0.2)

    hash_file.write_text(json.dumps(hashes, indent=2))
    print(f"  memory_files: {embedded} new, {collection.count()} total vectors")
    return embedded


def main():
    brain_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".claude-brain"
    mode = sys.argv[2] if len(sys.argv) > 2 else "new"
    config = load_config(brain_dir)

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[claude-brain {ts}] Embedding ({mode})...")

    # Check Ollama
    try:
        requests.get(f"{config['ollama_url']}/api/tags", timeout=5)
    except Exception:
        print("  Ollama offline. Skipping.")
        return

    total = 0
    total += embed_brain_entries(brain_dir, config, mode)
    total += embed_memory_files(brain_dir, config)
    print(f"[claude-brain {ts}] Done. {total} new embeddings.")


if __name__ == "__main__":
    main()
