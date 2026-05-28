#!/bin/bash
# claude-brain — Local-first persistent memory for Claude Code
# Usage: claude-brain [init|status|search|embed|serve]
# By Like One (likeone.ai)

set -e

BRAIN_DIR="${CLAUDE_BRAIN_DIR:-$HOME/.claude-brain}"
SCRIPT_DIR="$(cd "$(dirname "$0")/../src" && pwd)"

case "${1:-help}" in
  init)
    echo "claude-brain: Initializing local brain..."
    python3 "$SCRIPT_DIR/init.py" "$BRAIN_DIR"
    ;;
  status)
    python3 "$SCRIPT_DIR/status.py" "$BRAIN_DIR"
    ;;
  search)
    shift
    python3 "$SCRIPT_DIR/search.py" "$BRAIN_DIR" "$@"
    ;;
  embed)
    python3 "$SCRIPT_DIR/embed.py" "$BRAIN_DIR" "${2:-full}"
    ;;
  serve)
    python3 "$SCRIPT_DIR/mcp_server.py" "$BRAIN_DIR"
    ;;
  help|--help|-h)
    cat <<'HELP'
claude-brain — Local-first persistent memory for Claude Code

Commands:
  init              Set up brain database, ChromaDB, and cron
  status            Show brain health, vector counts, collection stats
  search <query>    Semantic search across all memory collections
  embed [full|new]  Run embedding pipeline (full or new entries only)
  serve             Start MCP server for Claude Code integration

Environment:
  CLAUDE_BRAIN_DIR  Override brain directory (default: ~/.claude-brain)
  OLLAMA_URL        Override Ollama endpoint (default: http://localhost:11434)

Requires: Python 3.10+, Ollama (running), chromadb, requests

Quick start:
  npx claude-brain init    # Set up brain
  npx claude-brain status  # Check health
  npx claude-brain search "how does auth work"  # Search your memory

Built with love by Like One (likeone.ai)
HELP
    ;;
  *)
    echo "Unknown command: $1. Run 'claude-brain help' for usage."
    exit 1
    ;;
esac
