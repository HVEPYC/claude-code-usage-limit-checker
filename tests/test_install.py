"""Installer / uninstaller tests in a sandbox HOME with a fake `claude` that records its arguments (POSIX only)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FOREIGN = {"type": "command", "command": "echo mine", "padding": 1}


@unittest.skipIf(os.name == "nt", "sandbox uses a POSIX fake `claude`")
class Installer(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="cc-usage-home-"))
        fakebin = self.home / "fakebin"
        fakebin.mkdir()
        self.calls = self.home / "claude_calls.txt"
        fake = fakebin / "claude"
        fake.write_text(f'#!/bin/sh\necho "$@" >> "{self.calls}"\n')
        fake.chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.home), "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}"}
        self.settings = self.home / ".claude" / "settings.json"
        self.dest = self.home / ".claude" / "cc-usage"

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(REPO / name), *args], capture_output=True, text=True, env=self.env)

    def write_settings(self, data):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps(data))

    def read_settings(self):
        return json.loads(self.settings.read_text())

    def test_fresh_install_and_uninstall(self):
        p = self.run_script("install.py")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        s = self.read_settings()
        self.assertIn("cc-usage/statusline.py", s["statusLine"]["command"])
        self.assertEqual(s["permissions"]["allow"], ["mcp__cc-usage__get_usage"])
        for f in ("usage_lib.py", "statusline.py", "mcp_server.py", "cli.py"):
            self.assertTrue((self.dest / f).exists())
        shim = self.home / ".local" / "bin" / "cc-usage"
        self.assertEqual(shim.resolve(), (self.dest / "cli.py").resolve())
        calls = self.calls.read_text().splitlines()
        self.assertEqual(calls[0], "mcp remove -s user cc-usage")
        self.assertEqual(calls[1], f"mcp add -s user cc-usage -- {sys.executable} {self.dest / 'mcp_server.py'}")
        # the shim runs and the copied tool works
        out = subprocess.run([str(shim)], capture_output=True, text=True, env={**self.env, "CLAUDECODE": "1"})
        self.assertIn("No usage reading yet", out.stdout)

        p = self.run_script("uninstall.py")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.read_settings(), {})
        self.assertFalse(self.dest.exists())
        self.assertFalse(shim.is_symlink() or shim.exists())
        self.assertEqual(self.calls.read_text().splitlines()[-1], "mcp remove -s user cc-usage")

    def test_dry_run_changes_nothing(self):
        p = self.run_script("install.py", "--dry-run")
        self.assertEqual(p.returncode, 0)
        self.assertIn("Dry run", p.stdout)
        self.assertFalse(self.settings.exists() or self.dest.exists() or self.calls.exists())

    def test_foreign_statusline_needs_decision(self):
        original = {"statusLine": FOREIGN, "theme": "dark", "permissions": {"allow": ["Bash(ls)"]}}
        self.write_settings(original)
        p = self.run_script("install.py")
        self.assertEqual(p.returncode, 4)
        self.assertIn("echo mine", p.stdout)
        self.assertEqual(self.read_settings(), original)
        self.assertFalse(self.dest.exists() or self.calls.exists())

    def test_chain_then_uninstall_restores_exactly(self):
        original = {"statusLine": FOREIGN, "theme": "dark", "permissions": {"allow": ["Bash(ls)"]}}
        self.write_settings(original)
        self.assertEqual(self.run_script("install.py", "--statusline", "chain").returncode, 0)
        cfg = json.loads((self.dest / "config.json").read_text())
        self.assertEqual(cfg["chain_statusline"], "echo mine")
        self.assertEqual(self.read_settings()["permissions"]["allow"], ["Bash(ls)", "mcp__cc-usage__get_usage"])
        line = subprocess.run([sys.executable, str(self.dest / "statusline.py")], input='{"session_id":"x"}',
                              capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(line[0], "mine")
        # re-running keeps the chain (status line is already ours now)
        self.assertEqual(self.run_script("install.py").returncode, 0)
        self.assertEqual(json.loads((self.dest / "config.json").read_text()), cfg)
        self.assertEqual(self.read_settings()["permissions"]["allow"].count("mcp__cc-usage__get_usage"), 1)
        self.run_script("uninstall.py")
        self.assertEqual(self.read_settings(), original)

    def test_replace_and_keep_data(self):
        self.write_settings({"statusLine": FOREIGN})
        self.assertEqual(self.run_script("install.py", "--statusline", "replace").returncode, 0)
        self.assertNotIn("chain_statusline", json.loads((self.dest / "config.json").read_text()))
        (self.dest / "usage.json").write_text("{}")
        self.run_script("uninstall.py", "--keep-data")
        self.assertEqual(self.read_settings(), {"statusLine": FOREIGN})
        self.assertEqual([p.name for p in self.dest.iterdir()], ["usage.json"])

    def test_skip_leaves_statusline(self):
        self.write_settings({"statusLine": FOREIGN})
        self.assertEqual(self.run_script("install.py", "--statusline", "skip").returncode, 0)
        self.assertEqual(self.read_settings()["statusLine"], FOREIGN)

    def test_settings_backup_written(self):
        self.write_settings({"theme": "dark"})
        self.run_script("install.py")
        self.assertEqual(len(list(self.settings.parent.glob("settings.json.bak-cc-usage-*"))), 1)


if __name__ == "__main__":
    unittest.main()
