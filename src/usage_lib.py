"""Shared reader for the Claude plan-usage reading captured by statusline.py (stdlib only).

The status line receives Claude Code's own rate_limits data (the same figures /usage shows) and writes
~/.claude/cc-usage/usage.json. Plan limits are account-wide, so the newest reading from ANY open
session is valid everywhere. Nothing here contacts the network: Claude Code is the only source of the numbers.
"""
import datetime as dt
import json
import os
from pathlib import Path

HOME = Path(__file__).resolve().parent
USAGE = HOME / "usage.json"
LOG = HOME / "usage_log.jsonl"


def now():
    return dt.datetime.now().astimezone()


def parse(ts):
    try:
        return dt.datetime.fromisoformat(ts)
    except Exception:
        return None


def read():
    """Return the latest reading enriched with age and reset status, or None if there is no reading yet."""
    try:
        r = json.loads(USAGE.read_text())
    except Exception:
        return None
    t = parse(r.get("captured_at", ""))
    r["age_minutes"] = round((now() - t).total_seconds() / 60, 1) if t else None
    for w in ("five_hour", "seven_day"):
        reset = parse(r.get(f"{w}_resets_at") or "")
        if reset and now() > reset:
            # the window rolled over since this reading was taken: usage restarted at 0
            r[f"{w}_pct"] = 0.0
            r[f"{w}_note"] = "window has reset since the last reading"
        if reset:
            r[f"{w}_resets_in_minutes"] = max(0, round((reset - now()).total_seconds() / 60))
    return r


def fmt_reset(iso):
    t = parse(iso or "")
    if not t:
        return "unknown"
    return t.strftime("%H:%M") + ("" if t.date() == now().date() else t.strftime(" %d %b"))


def summary(r=None):
    r = r if r is not None else read()
    if not r or r.get("five_hour_pct") is None:
        return "No usage reading yet: open any Claude Code session (the status line records it on each update)."
    parts = [f"5-hour: {r['five_hour_pct']:.0f}% used (resets {fmt_reset(r.get('five_hour_resets_at'))}"
             + (f", in {r['five_hour_resets_in_minutes']} min" if r.get("five_hour_resets_in_minutes") is not None else "") + ")"]
    if r.get("seven_day_pct") is not None:
        parts.append(f"7-day: {r['seven_day_pct']:.0f}% used (resets {fmt_reset(r.get('seven_day_resets_at'))})")
    if r.get("age_minutes") is not None:
        parts.append(f"reading {r['age_minutes']:.0f} min old")
    return " · ".join(parts)


def in_claude_code():
    """True when launched by Claude Code (it sets CLAUDECODE=1 for MCP servers and Bash-tool commands)."""
    return os.environ.get("CLAUDECODE") == "1"


def verdict(r, five_pct=None, seven_pct=None):
    """Return (word, reason): STOP if either window is at/above its threshold, UNKNOWN if a needed figure is missing."""
    if not r:
        return "UNKNOWN", "no reading yet"
    if r.get("rate_limits_available") is False:
        return "UNKNOWN", "Claude Code reported no rate limits for this account"
    for key, label, thr in (("five_hour_pct", "5-hour", five_pct), ("seven_day_pct", "7-day", seven_pct)):
        if thr is None:
            continue
        if r.get(key) is None:
            return "UNKNOWN", f"no {label} figure"
        if r[key] >= thr:
            return "STOP", f"{label} {r[key]:.0f}% >= {thr:g}%"
    return "OK", ""
