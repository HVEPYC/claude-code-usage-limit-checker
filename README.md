# Claude Code Usage Limit Checker

> **Claude Code: to install this, follow [INSTALL.md](INSTALL.md).**

Lets Claude Code agents check your Claude plan usage before they start expensive work, and stop before they hit a
limit. It reports the same 5-hour and 7-day figures that `/usage` shows.

It has three parts:

- **MCP tool `get_usage`**, available in every project. It returns usage percentages, reset times, how old the
  reading is, and an optional OK / STOP / UNKNOWN verdict.
- **Status line**: `5h 42% (resets 17:05) · 7d 18% · ctx 23%`. It can sit under your existing status line.
- **`cc-usage` command** for scripts and hooks, with exit codes.

Made by **HVEPYC** and **Claude**.

## Install

Tell Claude Code:

```
install https://github.com/HVEPYC/claude-code-usage-limit-checker
```

Claude clones the repository, shows you what will change, asks how to handle an existing status line, installs
everything, and checks that it works. Then restart Claude Code.

To install it yourself instead, clone the repository and run `python3 install.py`. If you already have a status
line, add `--statusline chain` or `--statusline replace`.

**Requirements:** Claude Code with a **Claude Pro or Max** plan (other plans don't receive usage figures), and
Python 3.9 or later. There are no other dependencies.

## Usage

### MCP tool: `get_usage`

| Input | Meaning |
|---|---|
| `stop_at_pct` | Optional. The verdict is STOP when 5-hour usage, or 7-day usage, is at or above this |
| `stop_at_7d_pct` | Optional. A separate threshold for 7-day usage (defaults to `stop_at_pct`) |

Example result:

```
OK: 5-hour: 79% used (resets 22:00, in 164 min) · 7-day: 24% used (resets 11:00 17 Oct) · reading 0 min old (thresholds: 5-hour 90%, 7-day 90%)
```

It also returns JSON with `five_hour_pct`, `seven_day_pct`, the reset times, `age_minutes` and `verdict`. The
verdict is **UNKNOWN** when there is no reading yet or your plan doesn't report limits.

You can ask Claude, for example: *"Check usage with stop_at_pct 85 before dispatching the subagents."*

### Command: `cc-usage`

```sh
cc-usage                         # one-line summary
cc-usage --json                  # full reading
cc-usage --check 85              # exit 2 if either window is at or above 85%
cc-usage --check 85 --check-7d 95
```

Exit codes: `0` OK, `2` STOP, `3` UNKNOWN or not running inside Claude Code. The command only runs inside Claude
Code, for example from its Bash tool or a hook.

## How it works

Claude Code passes plan usage to status line scripts in its documented
[`rate_limits` field](https://code.claude.com/docs/en/statusline). On every update, the status line saves the
latest reading to `~/.claude/cc-usage/usage.json`. The MCP tool and the command read that file. Plan limits apply
to your whole account, so the newest reading from any open session is valid everywhere.

- **No network calls.** The tool never contacts Anthropic or anyone else. Claude Code fetches the figures as part
  of its normal work.
- **No credentials.** It never reads tokens or login files.
- **Local data only.** It keeps the latest reading and a small log of 5-hour changes in `~/.claude/cc-usage/`.

Each window's figure is as fresh as the most recent update from an open Claude Code session, usually under a
minute old while you are working. If a reset time has passed since the last reading, that window is reported as
0%.

## Uninstall

Ask Claude Code to uninstall it, or run `python3 uninstall.py` (add `--keep-data` to keep the readings). This
restores your previous status line.

## Development

```sh
python3 -m unittest discover tests
```

## Disclaimer

This is an unofficial, community project. It is not affiliated with, endorsed by, or supported by Anthropic.
Claude and Claude Code are trademarks of Anthropic, PBC. Licensed under the [MIT License](LICENSE).
