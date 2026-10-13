#!/usr/bin/env python3
"""Uninstall Claude Code Usage Limit Checker, undoing everything install.py did.

  python3 uninstall.py [--keep-data]

Removes the `cc-usage` MCP server, the permission and the command, restores the status line that was there before
(if the installer chained or replaced one), and deletes ~/.claude/cc-usage/ (--keep-data keeps the usage readings).
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install import CONFIG, DEST, NAME, PERMISSION, SETTINGS, backup_settings, claude, is_ours, load_json, shim_path, write_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep-data", action="store_true", help="keep usage.json and usage_log.jsonl")
    a = ap.parse_args()

    if shutil.which("claude"):
        claude("mcp", "remove", "-s", "user", NAME)

    config = load_json(CONFIG, {})
    if SETTINGS.exists():
        settings = load_json(SETTINGS, {})
        backup_settings()
        if is_ours(settings.get("statusLine")):
            if config.get("previous_statusline"):
                settings["statusLine"] = config["previous_statusline"]
            else:
                settings.pop("statusLine")
        allow = (settings.get("permissions") or {}).get("allow")
        if allow and PERMISSION in allow:
            allow.remove(PERMISSION)
            if not allow:  # drop the containers the installer created
                del settings["permissions"]["allow"]
                if not settings["permissions"]:
                    del settings["permissions"]
        write_json(SETTINGS, settings)

    shim = shim_path()
    if shim.is_symlink() or shim.exists():
        shim.unlink()

    if DEST.exists():
        if a.keep_data:
            for p in DEST.iterdir():
                if p.name not in ("usage.json", "usage_log.jsonl"):
                    shutil.rmtree(p) if p.is_dir() else p.unlink()
        else:
            shutil.rmtree(DEST)
    print("Uninstalled Claude Code Usage Limit Checker. Restart Claude Code to finish.")


if __name__ == "__main__":
    main()
