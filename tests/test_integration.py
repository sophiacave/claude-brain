#!/usr/bin/env python3
"""Integration tests for claude-brain MCP server."""
import json
import sys
import tempfile
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

PASS = 0
FAIL = 0


def check(name, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}")


def setup_test_brain(tmpdir):
    """Create a minimal brain for testing."""
    brain_dir = Path(tmpdir) / "test-brain"
    brain_dir.mkdir()

    db = sqlite3.connect(str(brain_dir / "brain.db"))
    db.execute("""
        CREATE TABLE IF NOT EXISTS brain_context (
            key TEXT PRIMARY KEY,
            description TEXT,
            value TEXT,
            category TEXT DEFAULT 'general',
            priority INTEGER DEFAULT 5,
            updated_at TEXT
        )
    """)
    db.execute("""
        INSERT INTO brain_context (key, description, value, category, priority, updated_at)
        VALUES ('test.key', 'Test entry', 'test value', 'test', 5, '2026-01-01')
    """)
    db.commit()
    db.close()
    return brain_dir


def test_brain_write_and_read():
    """brain_write and brain_read work correctly."""
    print("\n--- Write & Read ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        brain_dir = setup_test_brain(tmpdir)

        # Patch BRAIN_DIR for testing
        import mcp_server
        original_dir = mcp_server.BRAIN_DIR
        mcp_server.BRAIN_DIR = brain_dir

        try:
            from mcp_server import brain_write, brain_read

            # Write
            result = brain_write("test.new_key", "hello world", "A test entry", "test", 7)
            check("brain_write returns saved status", result.get("status") == "saved")
            check("brain_write returns correct key", result.get("key") == "test.new_key")

            # Read back
            result = brain_read("test.new_key")
            check("brain_read returns value", result.get("value") == "hello world")
            check("brain_read returns category", result.get("category") == "test")

            # Read existing
            result = brain_read("test.key")
            check("brain_read existing key works", result.get("value") == "test value")

            # Read nonexistent
            result = brain_read("nonexistent.key")
            check("brain_read missing key returns error", "error" in result)

            # Overwrite
            brain_write("test.key", "updated value")
            result = brain_read("test.key")
            check("brain_write overwrites existing key", result.get("value") == "updated value")

        finally:
            mcp_server.BRAIN_DIR = original_dir


def test_brain_status():
    """brain_status returns correct counts."""
    print("\n--- Status ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        brain_dir = setup_test_brain(tmpdir)

        import mcp_server
        original_dir = mcp_server.BRAIN_DIR
        mcp_server.BRAIN_DIR = brain_dir

        try:
            from mcp_server import brain_status

            result = brain_status()
            check("brain_status returns entries count", result.get("entries", 0) >= 1)
            check("brain_status has vectors field", "vectors" in result)

        finally:
            mcp_server.BRAIN_DIR = original_dir


def test_init_check():
    """_check_init catches uninitialized brain."""
    print("\n--- Init Check ---")

    import mcp_server
    original_dir = mcp_server.BRAIN_DIR
    mcp_server.BRAIN_DIR = Path("/nonexistent/brain/dir")

    try:
        from mcp_server import brain_read, brain_write, brain_status

        result = brain_read("any.key")
        check("brain_read on uninit returns error", "error" in result)

        result = brain_write("any.key", "value")
        check("brain_write on uninit returns error", "error" in result)

        result = brain_status()
        check("brain_status on uninit returns error", "error" in result)

    finally:
        mcp_server.BRAIN_DIR = original_dir


def test_mcp_protocol():
    """MCP protocol handlers work."""
    print("\n--- MCP Protocol ---")

    from mcp_server import handle_request

    resp = handle_request({"method": "initialize", "id": 1})
    check("initialize returns serverInfo", "serverInfo" in resp)
    check("server name is claude-brain", resp["serverInfo"]["name"] == "claude-brain")

    resp = handle_request({"method": "tools/list", "id": 2})
    tools = resp["tools"]
    tool_names = [t["name"] for t in tools]
    check("4 tools listed", len(tools) == 4)
    check("brain_search exists", "brain_search" in tool_names)
    check("brain_write exists", "brain_write" in tool_names)
    check("brain_read exists", "brain_read" in tool_names)
    check("brain_status exists", "brain_status" in tool_names)

    # Schema validation
    for tool in tools:
        schema = tool.get("inputSchema", {})
        check(f"{tool['name']} has input schema", schema.get("type") == "object")

    # Unknown tool
    resp = handle_request({
        "method": "tools/call",
        "params": {"name": "nonexistent", "arguments": {}},
        "id": 3
    })
    result = json.loads(resp["content"][0]["text"])
    check("unknown tool returns error", "error" in result)

    # Unknown method
    resp = handle_request({"method": "nonexistent/method", "id": 4})
    check("unknown method returns error", "error" in resp)


def test_brain_write_types():
    """brain_write handles different value types."""
    print("\n--- Value Types ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        brain_dir = setup_test_brain(tmpdir)

        import mcp_server
        original_dir = mcp_server.BRAIN_DIR
        mcp_server.BRAIN_DIR = brain_dir

        try:
            from mcp_server import brain_write, brain_read

            # String value
            brain_write("types.string", "hello")
            result = brain_read("types.string")
            check("String value preserved", result["value"] == "hello")

            # Dict value (should be JSON-serialized)
            brain_write("types.dict", {"foo": "bar", "num": 42})
            result = brain_read("types.dict")
            parsed = json.loads(result["value"])
            check("Dict value JSON-serialized", parsed["foo"] == "bar")

            # List value
            brain_write("types.list", [1, 2, 3])
            result = brain_read("types.list")
            parsed = json.loads(result["value"])
            check("List value JSON-serialized", parsed == [1, 2, 3])

        finally:
            mcp_server.BRAIN_DIR = original_dir


if __name__ == "__main__":
    test_brain_write_and_read()
    test_brain_status()
    test_init_check()
    test_mcp_protocol()
    test_brain_write_types()
    print(f"\n{'='*40}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL > 0 else 0)
