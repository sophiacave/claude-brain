#!/usr/bin/env python3
"""claude-brain init — Set up local brain database, ChromaDB, and cron."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def check_dependencies():
    """Verify required tools are installed."""
    errors = []

    # Check Python packages
    for pkg in ["chromadb", "requests"]:
        try:
            __import__(pkg)
        except ImportError:
            errors.append(f"Missing Python package: {pkg}. Install with: pip install {pkg}")

    # Check Ollama
    try:
        import requests
        requests.get("http://localhost:11434/api/tags", timeout=5)
    except Exception:
        errors.append("Ollama not running. Start with: ollama serve")

    # Check for embedding model
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            if not any("mxbai-embed-large" in m for m in models):
                errors.append("Embedding model not found. Install with: ollama pull mxbai-embed-large")
    except Exception:
        pass

    return errors


def create_brain_db(brain_dir):
    """Create the SQLite brain database with schema."""
    db_path = brain_dir / "brain.db"
    db = sqlite3.connect(str(db_path))

    db.executescript("""
        CREATE TABLE IF NOT EXISTS brain_context (
            key TEXT PRIMARY KEY,
            description TEXT,
            value TEXT,
            category TEXT DEFAULT 'general',
            priority INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS brain_embed_log (
            key TEXT PRIMARY KEY,
            embedded_at TEXT,
            collection TEXT,
            vector_id TEXT
        );

        CREATE TABLE IF NOT EXISTS brain_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_number INTEGER,
            summary TEXT,
            started_at TEXT DEFAULT (datetime('now')),
            ended_at TEXT,
            tool_calls INTEGER DEFAULT 0,
            topics TEXT
        );

        CREATE TABLE IF NOT EXISTS brain_skills (
            name TEXT PRIMARY KEY,
            description TEXT,
            trigger_phrases TEXT,
            category TEXT,
            learned_at TEXT DEFAULT (datetime('now')),
            times_used INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_brain_context_category ON brain_context(category);
        CREATE INDEX IF NOT EXISTS idx_brain_context_priority ON brain_context(priority DESC);
    """)

    db.commit()
    db.close()
    return db_path


def setup_chromadb(brain_dir):
    """Initialize ChromaDB with default collections."""
    import chromadb

    chroma_path = brain_dir / "vector_store"
    client = chromadb.PersistentClient(path=str(chroma_path))

    collections = {
        "brain_entries": "Core knowledge from brain database",
        "memory_files": "CLAUDE.md, MEMORY.md, and topic files",
        "sessions": "Session summaries and learnings",
        "skills": "Learned skills and procedures",
    }

    for name, desc in collections.items():
        client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "description": desc}
        )

    return chroma_path


def setup_hooks(brain_dir):
    """Create Claude Code hooks for automatic brain integration."""
    hooks_dir = Path.home() / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Post-session hook to log session data
    hook_script = brain_dir / "hooks" / "brain-post-session.py"
    hook_script.parent.mkdir(parents=True, exist_ok=True)
    hook_script.write_text(f'''#!/usr/bin/env python3
"""Claude Code hook: Log session data to brain after each session."""
import json, sqlite3, sys
from pathlib import Path

BRAIN_DB = Path("{brain_dir}/brain.db")

def main():
    if not BRAIN_DB.exists():
        return
    # Read hook input from stdin
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    db = sqlite3.connect(str(BRAIN_DB))
    db.execute("""
        INSERT INTO brain_sessions (summary, tool_calls, topics)
        VALUES (?, ?, ?)
    """, (
        data.get("summary", "session"),
        data.get("tool_calls", 0),
        json.dumps(data.get("topics", []))
    ))
    db.commit()
    db.close()

if __name__ == "__main__":
    main()
''')
    hook_script.chmod(0o755)

    return hook_script


def setup_cron(brain_dir):
    """Add embedding cron job."""
    embed_script = brain_dir / "embed.py"
    cron_line = f"*/5 * * * * python3 {brain_dir}/src/embed.py {brain_dir} new >> {brain_dir}/logs/embed.log 2>&1"

    # Check if cron already exists
    try:
        existing = subprocess.check_output(["crontab", "-l"], stderr=subprocess.DEVNULL, text=True)
        if "claude-brain" in existing or str(brain_dir) in existing:
            print("  Cron already configured")
            return
    except subprocess.CalledProcessError:
        existing = ""

    print(f"  Adding cron: embed every 5 minutes")
    new_cron = existing.rstrip() + "\n" + cron_line + "\n"
    subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)


def create_claude_md_snippet(brain_dir):
    """Generate CLAUDE.md snippet for brain integration."""
    snippet = f"""
# Claude Brain Integration
# Add this to your project's CLAUDE.md to enable persistent memory

## Brain Commands
- Search brain: `claude-brain search "query"` — find relevant context
- Check status: `claude-brain status` — view brain health
- Embed new data: `claude-brain embed new` — embed recent entries

## Brain Location
- Database: {brain_dir}/brain.db
- Vectors: {brain_dir}/vector_store/
- Logs: {brain_dir}/logs/

## How It Works
Your brain automatically embeds new entries every 5 minutes via cron.
Search uses semantic similarity (Ollama mxbai-embed-large) across all collections.
All data stays local. Zero cloud dependency.
"""
    snippet_path = brain_dir / "CLAUDE-BRAIN-SNIPPET.md"
    snippet_path.write_text(snippet.strip())
    return snippet_path


def main():
    brain_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".claude-brain"

    print(f"claude-brain init")
    print(f"  Brain directory: {brain_dir}")
    print()

    # Check dependencies
    errors = check_dependencies()
    if errors:
        print("Missing dependencies:")
        for e in errors:
            print(f"  - {e}")
        print()
        print("Fix the above issues and run 'claude-brain init' again.")
        sys.exit(1)

    # Create directories
    brain_dir.mkdir(parents=True, exist_ok=True)
    (brain_dir / "logs").mkdir(exist_ok=True)

    # Initialize components
    print("  Creating brain database...")
    db_path = create_brain_db(brain_dir)
    print(f"    {db_path}")

    print("  Setting up ChromaDB vector store...")
    chroma_path = setup_chromadb(brain_dir)
    print(f"    {chroma_path}")

    print("  Creating hooks...")
    hook_path = setup_hooks(brain_dir)
    print(f"    {hook_path}")

    print("  Setting up cron...")
    setup_cron(brain_dir)

    print("  Creating CLAUDE.md snippet...")
    snippet_path = create_claude_md_snippet(brain_dir)
    print(f"    {snippet_path}")

    # Write config
    config = {
        "version": "0.1.0",
        "brain_dir": str(brain_dir),
        "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        "embed_model": "mxbai-embed-large",
        "collections": ["brain_entries", "memory_files", "sessions", "skills"],
        "embed_interval_minutes": 5,
    }
    (brain_dir / "config.json").write_text(json.dumps(config, indent=2))

    print()
    print("claude-brain initialized successfully!")
    print()
    print("Next steps:")
    print(f"  1. Add the snippet from {snippet_path} to your CLAUDE.md")
    print("  2. Start writing to brain: claude-brain embed full")
    print("  3. Search your memory: claude-brain search 'how does X work'")
    print()
    print("Built with love by Like One (likeone.ai)")


if __name__ == "__main__":
    main()
