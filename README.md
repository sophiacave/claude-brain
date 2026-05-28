# claude-brain

**Local-first persistent memory for Claude Code.** Semantic search, auto-embedding, team brain. Zero cloud dependency.

Claude Code forgets everything between sessions. claude-brain remembers.

## Why claude-brain?

| Feature | claude-brain | claude-mem | CLAUDE.md |
|---------|-------------|------------|-----------|
| Cross-session memory | Yes (semantic) | Yes (replay) | Manual only |
| Local-first | Yes (Ollama) | No (Claude API) | Yes |
| Semantic search | Yes (ChromaDB) | Limited | No |
| Team sharing | Yes | No | Git only |
| Collections | 4+ (brain, memory, sessions, skills) | 1 | 0 |
| Zero cloud | Yes | No | Yes |
| Auto-embed | Yes (cron) | Hook-based | No |
| MCP server | Yes | No | No |

## Quick Start

```bash
# Prerequisites: Ollama running with mxbai-embed-large
ollama pull mxbai-embed-large
pip install chromadb requests

# Initialize brain
npx claude-brain init

# Embed your context
claude-brain embed full

# Search your memory
claude-brain search "how does auth work in this project"

# Check health
claude-brain status
```

## MCP Server Integration

Add to your Claude Code MCP config (`~/.claude/mcp.json`):

```json
{
  "mcpServers": {
    "claude-brain": {
      "command": "python3",
      "args": ["~/.claude-brain/src/mcp_server.py"]
    }
  }
}
```

Claude Code will now have these tools:
- `brain_search` — Semantic search across all memory
- `brain_write` — Persist decisions, patterns, and context
- `brain_read` — Read specific brain keys
- `brain_status` — Check brain health

## How It Works

```
You code with Claude Code
     |
     v
brain_write() stores decisions, patterns, learnings
     |
     v
Cron (*/5 min) embeds new entries via Ollama
     |
     v
ChromaDB stores vectors locally
     |
     v
Next session: brain_search() retrieves relevant context
     |
     v
Claude Code has memory across sessions
```

## Architecture

- **SQLite brain.db** — Structured key-value store for decisions, patterns, project context
- **ChromaDB vector_store** — Semantic embeddings for similarity search
- **Ollama mxbai-embed-large** — Local embeddings, no API costs, no data leaves your machine
- **Cron auto-embed** — New entries embedded every 5 minutes automatically
- **MCP server** — Direct integration with Claude Code via Model Context Protocol

All data stays on your machine. No cloud. No API keys needed (except Ollama, which is local).

## Commands

| Command | Description |
|---------|-------------|
| `claude-brain init` | Set up brain database, ChromaDB, and cron |
| `claude-brain status` | Show brain health, vector counts, stats |
| `claude-brain search <query>` | Semantic search across all collections |
| `claude-brain embed [full\|new]` | Run embedding pipeline |
| `claude-brain serve` | Start MCP server |

## Collections

| Collection | What it stores |
|------------|---------------|
| `brain_entries` | Core knowledge: decisions, patterns, architecture notes |
| `memory_files` | CLAUDE.md, MEMORY.md, and project memory files |
| `sessions` | Session summaries, learnings, what was tried |
| `skills` | Learned procedures and reusable patterns |

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai) running locally
- `pip install chromadb requests`
- Node.js 18+ (for npx install)

## Built With Love

Made by [Like One](https://likeone.ai) — a 501(c)(3) building AI tools for everyone.

We believe AI memory should be:
- **Local** — your data stays on your machine
- **Free** — the core is open source forever
- **Useful** — not a gimmick, actual persistent context that makes you productive

This tool was born from 200+ coding sessions where we needed Claude to remember what happened yesterday. Now it does.

## License

MIT
