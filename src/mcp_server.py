#!/usr/bin/env python3
"""Minimal stdio MCP server (stdlib only) exposing Claude plan usage as a tool in every workspace.

Tool `get_usage`: returns the latest 5-hour / 7-day usage %, reset times and reading age, as captured by the
global status line (~/.claude/cc-usage/statusline.py). Optional `stop_at_pct` / `stop_at_7d_pct` return a verdict.
Runs only when launched by Claude Code (CLAUDECODE=1); it never contacts the network.
Protocol: newline-delimited JSON-RPC 2.0 over stdin/stdout (MCP stdio transport).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage_lib import in_claude_code, read, summary, verdict  # noqa: E402

PROTOCOL = "2025-06-18"
TOOL = {
    "name": "get_usage",
    "description": ("Get the current Claude plan usage: exact 5-hour and 7-day usage percentages (the figures /usage "
                    "shows), when each window resets, and how old the reading is (age_minutes). The reading comes from "
                    "Claude Code's own status line and is kept fresh by the running session, so call it as often as "
                    "needed, e.g. before dispatching several subagents. Pass stop_at_pct (and optionally "
                    "stop_at_7d_pct) to get an OK/STOP/UNKNOWN verdict covering both windows."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "stop_at_pct": {"type": "number", "description": "Optional threshold; the verdict is STOP when 5-hour usage (or 7-day usage, unless stop_at_7d_pct is given) is at or above it."},
            "stop_at_7d_pct": {"type": "number", "description": "Optional separate threshold for 7-day usage; defaults to stop_at_pct."},
        },
        "additionalProperties": False,
    },
}


def respond(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def call_tool(args):
    if not in_claude_code():
        return {"content": [{"type": "text", "text": "get_usage only runs inside Claude Code"}], "isError": True}
    r = read()
    text = summary(r)
    data = {k: v for k, v in (r or {}).items() if k not in ("session_id", "cwd")}
    five = args.get("stop_at_pct")
    seven = args.get("stop_at_7d_pct", five)
    if five is not None or seven is not None:
        word, reason = verdict(r, five, seven)
        data["verdict"] = word
        thresholds = ", ".join(f"{n} {t:g}%" for n, t in (("5-hour", five), ("7-day", seven)) if t is not None)
        text = f"{word}{f' ({reason})' if reason else ''}: {text} (thresholds: {thresholds})"
    return {"content": [{"type": "text", "text": text}, {"type": "text", "text": json.dumps(data)}], "isError": False}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, id_ = msg.get("method"), msg.get("id")
        if id_ is None:  # notifications (e.g. notifications/initialized) need no reply
            continue
        if method == "initialize":
            if not in_claude_code():
                sys.stderr.write("cc-usage MCP server only runs inside Claude Code (CLAUDECODE=1 not set)\n")
                sys.exit(1)
            client_proto = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
            respond(id_, {"protocolVersion": client_proto, "capabilities": {"tools": {}},
                          "serverInfo": {"name": "cc-usage", "version": "1.1.0"}})
        elif method == "tools/list":
            respond(id_, {"tools": [TOOL]})
        elif method == "tools/call":
            p = msg.get("params") or {}
            if p.get("name") != TOOL["name"]:
                respond(id_, error={"code": -32602, "message": f"unknown tool {p.get('name')}"})
            else:
                respond(id_, call_tool(p.get("arguments") or {}))
        elif method == "ping":
            respond(id_, {})
        else:
            respond(id_, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()
