# Installing Claude Code Usage Limit Checker

**These steps are written for Claude Code to follow.** If a user has given you this repository's link and asked you
to install it, work through the steps in order. Every step is a command you run yourself. Ask the user only where a
step says to.

## 1. Check prerequisites

- `python3 --version` must be 3.9 or later. On Windows, use `python` or `py -3` wherever this guide says `python3`.
- `claude --version` must work. The installer registers the MCP server with `claude mcp add`.
- `git` is needed to clone. If it isn't installed, download the repository archive instead.

## 2. Clone into a temporary folder

```sh
git clone --depth 1 https://github.com/HVEPYC/claude-code-usage-limit-checker <temp-dir>/cc-usage-src
```

Use your scratchpad or another temporary folder, not the user's project. The installer copies everything it needs
into `~/.claude/cc-usage/`, so the clone can be deleted afterwards.

## 3. Show the user what will change

```sh
python3 cc-usage-src/install.py --dry-run
```

Tell the user in a few lines what the dry run printed. The installer:
- copies 4 Python files to `~/.claude/cc-usage/`
- registers the `cc-usage` MCP server for all projects
- sets the status line and allows `mcp__cc-usage__get_usage` in `~/.claude/settings.json`, after saving a backup
- links the `cc-usage` command into `~/.local/bin`

If the dry run exits with code **4**, the user already has a status line, so go to step 4. Otherwise run:

```sh
python3 cc-usage-src/install.py
```

## 4. Only if the exit code was 4: ask about the existing status line

The tool records readings through the status line, because that is where Claude Code supplies plan usage. Show the
user their current status line command (the installer printed it) and ask them to choose:

- **chain** (recommended): keep their status line and show the usage line under it.
- **replace**: show only the usage line. Their old one is saved and restored on uninstall.

Then run `python3 cc-usage-src/install.py --statusline chain` (or `replace`). Use `--statusline skip` only if the
user explicitly wants their status line untouched. In that case, tell them that no readings will be recorded.

## 5. Verify

```sh
claude mcp list | grep cc-usage
CLAUDECODE=1 ~/.local/bin/cc-usage; echo "exit $?"
```

- `claude mcp list` must show `cc-usage`.
- `cc-usage` prints either a reading or "No usage reading yet". Both mean the install worked.
- If the installer warned that `~/.local/bin` is not on PATH, tell the user how to add it for their shell.

## 6. Finish

1. Delete the temporary clone.
2. Tell the user to **restart Claude Code**, then ask Claude "check my usage". The first reading appears after the
   new session's first response.
3. Mention that usage figures are only provided for **Claude Pro and Max** plans. On other plans the tool always
   reports UNKNOWN.

## Upgrading

Clone the latest version and run `install.py` again. It is safe to re-run: it updates the files and keeps the
existing readings and status line setup.

## Uninstalling

```sh
python3 cc-usage-src/uninstall.py            # or --keep-data to keep the readings
```

It removes the MCP server, the permission and the command, restores any status line it chained or replaced, and
deletes `~/.claude/cc-usage/`.
