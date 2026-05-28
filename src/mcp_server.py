#!/usr/bin/env python3
"""claude-brain MCP server — Exposes brain search + write as MCP tools for Claude Code."""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import chromadb
import requests

BRAIN_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".claude-brain"


def load_config():
    config_path = BRAIN_DIR / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {"ollama_url": "http://localhost:11434", "embed_model": "mxbai-embed-large"}


def get_embedding(text):
    config = load_config()
    try:
        resp = requests.post(
            f"{config['ollama_url']}/api/embed",
            json={"model": config["embed_model"], "input": text[:1500]},
            timeout=30
        )
        if resp.status_code == 200:
            embeddings = resp.json().get("embeddings", [])
            if embeddings:
                return embeddings[0]
    except Exception:
        pass
    return None


def brain_search(query, top_k=5):
    """Semantic search across all brain collections."""
    embedding = get_embedding(query)
    if not embedding:
        return {"error": "Failed to embed query"}

    client = chromadb.PersistentClient(path=str(BRAIN_DIR / "vector_store"))
    results = []

    for col in client.list_collections():
        if col.count() == 0:
            continue
        try:
            r = col.query(query_embeddings=[embedding], n_results=min(3, col.count()))
            for i, doc in enumerate(r["documents"][0]):
                results.append({
                    "distance": r["distances"][0][i],
                    "collection": col.name,
                    "document": doc[:500],
                    "metadata": r["metadatas"][0][i]
                })
        except Exception:
            pass

    results.sort(key=lambda x: x["distance"])
    return {"results": results[:top_k], "total": len(results)}


def brain_write(key, value, description="", category="general", priority=5):
    """Write a key-value entry to the brain."""
    db = sqlite3.connect(str(BRAIN_DIR / "brain.db"))
    val_str = json.dumps(value) if not isinstance(value, str) else value

    db.execute("""
        INSERT OR REPLACE INTO brain_context (key, description, value, category, priority, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (key, description, val_str, category, priority, datetime.now().isoformat()))
    db.commit()
    db.close()
    return {"status": "saved", "key": key}


def brain_read(key):
    """Read a specific key from the brain."""
    db = sqlite3.connect(str(BRAIN_DIR / "brain.db"))
    row = db.execute("SELECT * FROM brain_context WHERE key = ?", (key,)).fetchone()
    db.close()
    if row:
        return {"key": row[0], "description": row[1], "value": row[2],
                "category": row[3], "priority": row[4]}
    return {"error": f"Key not found: {key}"}


def brain_status():
    """Get brain health status."""
    db = sqlite3.connect(str(BRAIN_DIR / "brain.db"))
    entries = db.execute("SELECT COUNT(*) FROM brain_context").fetchone()[0]
    db.close()

    client = chromadb.PersistentClient(path=str(BRAIN_DIR / "vector_store"))
    vectors = sum(col.count() for col in client.list_collections())

    return {"entries": entries, "vectors": vectors,
            "collections": {col.name: col.count() for col in client.list_collections()}}


# MCP stdio protocol handler
def handle_request(request):
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "claude-brain", "version": "0.1.0"}
        }

    if method == "tools/list":
        return {"tools": [
            {
                "name": "brain_search",
                "description": "Semantic search across all brain memory collections. Use this to recall past decisions, learned patterns, project context, and session history.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "top_k": {"type": "integer", "description": "Number of results", "default": 5}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "brain_write",
                "description": "Write a key-value entry to persistent brain memory. Use for decisions, learnings, patterns, and important context that should persist across sessions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Dot-notation key (e.g. 'project.auth_setup')"},
                        "value": {"type": "string", "description": "Value to store"},
                        "description": {"type": "string", "description": "Human-readable description"},
                        "category": {"type": "string", "description": "Category: general, project, decision, pattern, session"},
                        "priority": {"type": "integer", "description": "Priority 1-10", "default": 5}
                    },
                    "required": ["key", "value"]
                }
            },
            {
                "name": "brain_read",
                "description": "Read a specific key from brain memory.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Key to read"}
                    },
                    "required": ["key"]
                }
            },
            {
                "name": "brain_status",
                "description": "Get brain health: entry count, vector count, collection stats.",
                "inputSchema": {"type": "object", "properties": {}}
            }
        ]}

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        if tool_name == "brain_search":
            result = brain_search(args["query"], args.get("top_k", 5))
        elif tool_name == "brain_write":
            result = brain_write(
                args["key"], args["value"],
                args.get("description", ""), args.get("category", "general"),
                args.get("priority", 5)
            )
        elif tool_name == "brain_read":
            result = brain_read(args["key"])
        elif tool_name == "brain_status":
            result = brain_status()
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    return {"error": f"Unknown method: {method}"}


def main():
    """Run MCP server over stdio."""
    import io
    input_stream = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")

    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            result = handle_request(request)
            response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if "request" in dir() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
