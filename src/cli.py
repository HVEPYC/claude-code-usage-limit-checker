#!/usr/bin/env python3
"""cc-usage: print the current Claude plan usage from inside Claude Code (e.g. its Bash tool or hooks).

  cc-usage                         one-line summary
  cc-usage --json                  full reading as JSON
  cc-usage --check 85              exit 2 if 5-hour or 7-day usage is at/above 85%
  cc-usage --check 85 --check-7d 95  separate 7-day threshold

Exit codes: 0 OK, 2 STOP, 3 UNKNOWN (no reading, limits unavailable) or not running inside Claude Code.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage_lib import in_claude_code, read, summary, verdict  # noqa: E402


def main():
    ap = argparse.ArgumentParser(prog="cc-usage")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", type=float, metavar="PCT")
    ap.add_argument("--check-7d", type=float, metavar="PCT")
    a = ap.parse_args()
    if not in_claude_code():
        print("cc-usage only runs inside Claude Code", file=sys.stderr)
        sys.exit(3)
    r = read()
    if a.json:
        print(json.dumps(r, indent=1))
    else:
        print(summary(r))
    if a.check is not None or a.check_7d is not None:
        seven = a.check_7d if a.check_7d is not None else a.check
        word, reason = verdict(r, a.check, seven)
        if word != "OK":
            print(f"{word}: {reason}", file=sys.stderr)
        sys.exit({"OK": 0, "STOP": 2}.get(word, 3))


if __name__ == "__main__":
    main()
