#!/usr/bin/env python3
"""Global Claude Code status line (stdlib only). Claude Code pipes session JSON to stdin on every UI update.

Writes ~/.claude/cc-usage/usage.json (latest plan rate-limit reading; read by cc-usage, the MCP
usage tool and project usage gates) and appends to usage_log.jsonl whenever the 5-hour % changes.
Prints: 5h 42% (resets 17:05) · 7d 18% · ctx 23%
If config.json has "chain_statusline" (a previous status line command), that command gets the same input and its
output is printed first, followed by this line.
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parent
USAGE = HOME / "usage.json"
LOG = HOME / "usage_log.jsonl"
CONFIG = HOME / "config.json"


def to_iso(v):
    """resets_at arrives as epoch seconds (status line) or ISO (other surfaces)."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace(".", "", 1).isdigit()):
        return dt.datetime.fromtimestamp(float(v)).astimezone().isoformat(timespec="seconds")
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone().isoformat(timespec="seconds")
    except ValueError:
        return str(v)


def pct(w):
    if isinstance(w, dict):
        for k in ("used_percentage", "utilization"):
            if w.get(k) is not None:
                return round(float(w[k]), 1)
    return None


def chained(raw):
    """Output of the user's previous status line, if the installer chained one; '' on any problem."""
    try:
        cmd = json.loads(CONFIG.read_text()).get("chain_statusline")
    except Exception:
        return ""
    if not cmd:
        return ""
    try:
        return subprocess.run(cmd, shell=True, input=raw, capture_output=True, text=True, timeout=3).stdout.rstrip("\n")
    except Exception:
        return ""


def main():
    raw = sys.stdin.read()
    prefix = chained(raw)
    if prefix:
        print(prefix)
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        print("status: no data")
        return
    now = dt.datetime.now().astimezone()

    rl = d.get("rate_limits") or {}
    five, seven = rl.get("five_hour"), rl.get("seven_day")
    reading = {
        "five_hour_pct": pct(five),
        "five_hour_resets_at": to_iso((five or {}).get("resets_at")),
        "seven_day_pct": pct(seven),
        "seven_day_resets_at": to_iso((seven or {}).get("resets_at")),
        "rate_limits_available": bool(rl) if d.get("rate_limits_available") is None else bool(d["rate_limits_available"]),
        "captured_at": now.isoformat(timespec="seconds"),
        "session_id": d.get("session_id"),
        "cwd": d.get("cwd"),
    }
    prev = {}
    try:
        prev = json.loads(USAGE.read_text())
    except Exception:
        pass
    # keep the last good reading if this update carries no rate limits (e.g. an API-key session)
    if reading["five_hour_pct"] is not None or not prev:
        tmp = USAGE.with_name(f".usage.{now.timestamp():.0f}.{id(reading)}.tmp")
        tmp.write_text(json.dumps(reading, indent=1))
        tmp.replace(USAGE)  # atomic: several sessions may update at once
        if reading["five_hour_pct"] != prev.get("five_hour_pct"):
            with open(LOG, "a") as fh:
                fh.write(json.dumps({"t": reading["captured_at"], "pct": reading["five_hour_pct"],
                                     "resets_at": reading["five_hour_resets_at"]}) + "\n")

    parts = []
    if reading["five_hour_pct"] is not None:
        r = reading["five_hour_resets_at"]
        parts.append(f"5h {reading['five_hour_pct']:.0f}%" + (f" (resets {r[11:16]})" if r else ""))
    else:
        parts.append("5h n/a")
    if reading["seven_day_pct"] is not None:
        parts.append(f"7d {reading['seven_day_pct']:.0f}%")
    ctx = (d.get("context_window") or {}).get("used_percentage")
    if ctx is not None:
        parts.append(f"ctx {float(ctx):.0f}%")
    print(" · ".join(parts))


if __name__ == "__main__":
    main()
