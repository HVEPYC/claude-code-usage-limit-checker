#!/usr/bin/env python3
"""Install Claude Code Usage Limit Checker (stdlib only, safe to re-run).

  python3 install.py [--statusline chain|replace|skip] [--dry-run]

Copies src/ to ~/.claude/cc-usage/, registers the `cc-usage` MCP server at user scope, sets the status line and a
permission in ~/.claude/settings.json (backed up first), and links the `cc-usage` command into ~/.local/bin.

Exit codes: 0 installed, 1 a prerequisite is missing, 4 another status line exists and --statusline was not given
(nothing was changed; ask the user, then re-run with chain or replace).
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

NAME = "cc-usage"
REPO = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"
DEST = CLAUDE_DIR / NAME
SETTINGS = CLAUDE_DIR / "settings.json"
CONFIG = DEST / "config.json"
BIN = Path.home() / ".local" / "bin"
PERMISSION = f"mcp__{NAME}__get_usage"
CODE_FILES = ("usage_lib.py", "statusline.py", "mcp_server.py", "cli.py")
WINDOWS = os.name == "nt"


def quote(p):
    return f'"{p}"'


def our_statusline():
    return {"type": "command", "command": f"{quote(sys.executable)} {quote(DEST / 'statusline.py')}"}


def is_ours(statusline):
    return isinstance(statusline, dict) and f"{NAME}/statusline.py" in str(statusline.get("command", "")).replace("\\", "/")


def shim_path():
    return BIN / (f"{NAME}.cmd" if WINDOWS else NAME)


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def backup_settings():
    if SETTINGS.exists():
        dest = SETTINGS.with_name(f"settings.json.bak-{NAME}-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(SETTINGS, dest)
        return dest
    return None


def claude(*args):
    return subprocess.run(["claude", *args], capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--statusline", choices=("chain", "replace", "skip"),
                    help="what to do when a different status line is already configured")
    ap.add_argument("--dry-run", action="store_true", help="print what would change and change nothing")
    a = ap.parse_args()

    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 or later is required.")
    if not shutil.which("claude"):
        sys.exit("The `claude` command (Claude Code) was not found on PATH.")

    settings = load_json(SETTINGS, {})
    current = settings.get("statusLine")
    config = load_json(CONFIG, {})
    mode = "set"
    if current and not is_ours(current):
        if not a.statusline:
            print(f"Another status line is already configured:\n  {json.dumps(current)}\n"
                  "Nothing was changed. Re-run with one of:\n"
                  "  --statusline chain    keep it and show the usage line under it (recommended)\n"
                  "  --statusline replace  use only the usage line (the old one is restored on uninstall)\n"
                  "  --statusline skip     leave it alone (readings will NOT be recorded)")
            sys.exit(4)
        mode = a.statusline
    elif is_ours(current):
        mode = "keep"

    plan = [f"copy {', '.join(CODE_FILES)} to {DEST}",
            f"register MCP server '{NAME}' (user scope): {sys.executable} {DEST / 'mcp_server.py'}",
            f"back up {SETTINGS} and add '{PERMISSION}' to permissions.allow",
            {"set": "set statusLine to the usage status line",
             "keep": "refresh statusLine (already the usage status line)",
             "chain": f"set statusLine to the usage status line, chaining the existing one: {current and current.get('command')}",
             "replace": "replace the existing statusLine (saved in config.json, restored on uninstall)",
             "skip": "leave the existing statusLine unchanged (WARNING: readings will not be recorded)"}[mode],
            f"{'write' if WINDOWS else 'link'} the `{NAME}` command at {shim_path()}"]
    if a.dry_run:
        print("Dry run. The installer would:\n" + "\n".join(f"  - {p}" for p in plan))
        return

    DEST.mkdir(parents=True, exist_ok=True)
    for f in CODE_FILES:
        shutil.copy2(REPO / "src" / f, DEST / f)
        if not WINDOWS:
            (DEST / f).chmod(0o755)

    claude("mcp", "remove", "-s", "user", NAME)
    r = claude("mcp", "add", "-s", "user", NAME, "--", sys.executable, str(DEST / "mcp_server.py"))
    if r.returncode != 0:
        sys.exit(f"Registering the MCP server failed:\n{r.stdout}{r.stderr}")

    backup = backup_settings()
    if mode in ("chain", "replace"):
        config = {"previous_statusline": current}
        if mode == "chain":
            config["chain_statusline"] = current.get("command")
        write_json(CONFIG, config)
    elif mode == "set":
        write_json(CONFIG, {})
    if mode != "skip":
        settings["statusLine"] = our_statusline()
    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    if PERMISSION not in allow:
        allow.append(PERMISSION)
    write_json(SETTINGS, settings)

    BIN.mkdir(parents=True, exist_ok=True)
    shim = shim_path()
    if shim.is_symlink() or shim.exists():
        shim.unlink()
    if WINDOWS:
        shim.write_text(f'@{quote(sys.executable)} {quote(DEST / "cli.py")} %*\r\n')
    else:
        shim.symlink_to(DEST / "cli.py")

    print("Installed Claude Code Usage Limit Checker:\n" + "\n".join(f"  - {p}" for p in plan))
    if backup:
        print(f"Settings backup: {backup}")
    if str(BIN) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"Note: {BIN} is not on PATH, so `{NAME}` must be run by its full path until it is added.")
    print("Restart Claude Code to load the MCP server and status line. "
          "The first reading appears after the session's first response.")


if __name__ == "__main__":
    main()
