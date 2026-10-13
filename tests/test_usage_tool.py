"""Tests for src/. They run against a temporary copy, so no real readings are touched (override with $TOOL)."""
import ast
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if os.environ.get("TOOL"):
    TOOL = Path(os.environ["TOOL"]).resolve()
else:
    TOOL = Path(tempfile.mkdtemp(prefix="cc-usage-test-"))
    for _f in (Path(__file__).resolve().parent.parent / "src").glob("*.py"):
        shutil.copy2(_f, TOOL)
PY = sys.executable
sys.path.insert(0, str(TOOL))
import usage_lib  # noqa: E402

USAGE, LOG = TOOL / "usage.json", TOOL / "usage_log.jsonl"
IN_CC = {**os.environ, "CLAUDECODE": "1"}
OUT_CC = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def now():
    return dt.datetime.now().astimezone()


def iso(delta_min):
    return (now() + dt.timedelta(minutes=delta_min)).isoformat(timespec="seconds")


def write_reading(five=50.0, seven=20.0, five_reset=120, seven_reset=3000, age=0, available=True):
    USAGE.write_text(json.dumps({
        "five_hour_pct": five, "five_hour_resets_at": iso(five_reset) if five_reset is not None else None,
        "seven_day_pct": seven, "seven_day_resets_at": iso(seven_reset) if seven_reset is not None else None,
        "rate_limits_available": available, "captured_at": iso(-age), "session_id": "s", "cwd": "/x"}))


def clean():
    for f in (USAGE, LOG):
        f.unlink(missing_ok=True)


def run(script, args=(), stdin="", env=IN_CC):
    return subprocess.run([PY, str(TOOL / script), *args], input=stdin, capture_output=True, text=True, env=env, timeout=20)


def sl_payload(five=42, seven=18, five_reset=None, seven_reset=None, rate_limits=True):
    d = {"session_id": "abc", "cwd": "/tmp", "context_window": {"used_percentage": 23}}
    if rate_limits:
        d["rate_limits"] = {
            "five_hour": {"used_percentage": five, "resets_at": five_reset or int(now().timestamp()) + 3600},
            "seven_day": {"used_percentage": seven, "resets_at": seven_reset or int(now().timestamp()) + 86400}}
    return json.dumps(d)


class Lib(unittest.TestCase):
    def setUp(self):
        clean()

    def test_no_file(self):
        self.assertIsNone(usage_lib.read())
        self.assertIn("No usage reading yet", usage_lib.summary(None))

    def test_corrupt_file(self):
        USAGE.write_text("{not json")
        self.assertIsNone(usage_lib.read())

    def test_age_and_reset_minutes(self):
        write_reading(age=7, five_reset=90)
        r = usage_lib.read()
        self.assertAlmostEqual(r["age_minutes"], 7, delta=0.2)
        self.assertIn(r["five_hour_resets_in_minutes"], (89, 90))

    def test_rollover_zeroes_window(self):
        write_reading(five=95, seven=60, five_reset=-5, seven_reset=100)
        r = usage_lib.read()
        self.assertEqual(r["five_hour_pct"], 0.0)
        self.assertIn("reset", r["five_hour_note"])
        self.assertEqual(r["five_hour_resets_in_minutes"], 0)
        self.assertEqual(r["seven_day_pct"], 60)

    def test_missing_reset_times(self):
        write_reading(five_reset=None, seven_reset=None)
        r = usage_lib.read()
        self.assertNotIn("five_hour_resets_in_minutes", r)
        self.assertIn("resets unknown", usage_lib.summary(r))

    def test_summary_without_seven_day(self):
        write_reading(seven=None)
        s = usage_lib.summary(usage_lib.read())
        self.assertIn("5-hour: 50%", s)
        self.assertNotIn("7-day", s)

    def test_in_claude_code(self):
        old = os.environ.get("CLAUDECODE")
        try:
            os.environ["CLAUDECODE"] = "1"
            self.assertTrue(usage_lib.in_claude_code())
            os.environ["CLAUDECODE"] = "0"
            self.assertFalse(usage_lib.in_claude_code())
            del os.environ["CLAUDECODE"]
            self.assertFalse(usage_lib.in_claude_code())
        finally:
            if old is not None:
                os.environ["CLAUDECODE"] = old


class Verdict(unittest.TestCase):
    v = staticmethod(usage_lib.verdict)

    def test_cases(self):
        ok = {"five_hour_pct": 10, "seven_day_pct": 10, "rate_limits_available": True}
        self.assertEqual(self.v(None, 90, 90)[0], "UNKNOWN")
        self.assertEqual(self.v({**ok, "rate_limits_available": False}, 90, 90)[0], "UNKNOWN")
        self.assertEqual(self.v({**ok, "seven_day_pct": None}, 90, 90)[0], "UNKNOWN")
        self.assertEqual(self.v(ok, 90, 90), ("OK", ""))
        self.assertEqual(self.v({**ok, "seven_day_pct": 100}, 90, 90)[0], "STOP")
        self.assertEqual(self.v({**ok, "five_hour_pct": 90}, 90, 90)[0], "STOP")  # boundary: at threshold stops
        self.assertEqual(self.v({**ok, "five_hour_pct": 89.9}, 90, 90)[0], "OK")
        self.assertEqual(self.v({**ok, "seven_day_pct": None}, 90, None)[0], "OK")  # 7-day not checked
        self.assertEqual(self.v(ok, None, None), ("OK", ""))


class StatusLine(unittest.TestCase):
    def setUp(self):
        clean()

    def test_writes_reading_and_prints(self):
        p = run("statusline.py", stdin=sl_payload())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout, r"^5h 42% \(resets \d\d:\d\d\) · 7d 18% · ctx 23%")
        r = json.loads(USAGE.read_text())
        self.assertEqual((r["five_hour_pct"], r["seven_day_pct"], r["rate_limits_available"]), (42, 18, True))

    def test_iso_resets_with_z(self):
        run("statusline.py", stdin=sl_payload(five_reset="2030-01-01T00:00:00Z"))
        self.assertTrue(json.loads(USAGE.read_text())["five_hour_resets_at"].startswith("20"))

    def test_keeps_last_good_reading_without_rate_limits(self):
        run("statusline.py", stdin=sl_payload(five=42))
        p = run("statusline.py", stdin=sl_payload(rate_limits=False))
        self.assertIn("5h n/a", p.stdout)
        self.assertEqual(json.loads(USAGE.read_text())["five_hour_pct"], 42)

    def test_bad_input(self):
        p = run("statusline.py", stdin="garbage")
        self.assertEqual(p.stdout.strip(), "status: no data")

    def test_log_only_on_change(self):
        for pct in (10, 10, 11, 11, 12):
            run("statusline.py", stdin=sl_payload(five=pct))
        self.assertEqual([json.loads(l)["pct"] for l in LOG.read_text().splitlines()], [10, 11, 12])

    def test_parallel_writes_stay_valid(self):
        with ThreadPoolExecutor(16) as ex:
            list(ex.map(lambda i: run("statusline.py", stdin=sl_payload(five=i % 100)), range(48)))
        json.loads(USAGE.read_text())  # never torn
        self.assertEqual(list(TOOL.glob(".usage.*.tmp")), [])

    def test_writes_only_usage_and_log(self):
        before = set(TOOL.iterdir())
        run("statusline.py", stdin=sl_payload(five=33))
        self.assertEqual({f.name for f in set(TOOL.iterdir()) - before} - {"__pycache__"}, {"usage.json", "usage_log.jsonl"})

    def test_chains_previous_statusline(self):
        cfg = TOOL / "config.json"
        try:
            cfg.write_text(json.dumps({"chain_statusline": f"{PY} -c \"import sys,json; print('OLD', json.load(sys.stdin)['session_id'])\""}))
            lines = run("statusline.py", stdin=sl_payload(five=12)).stdout.splitlines()
            self.assertEqual(lines[0], "OLD abc")
            self.assertTrue(lines[1].startswith("5h 12%"))
            cfg.write_text(json.dumps({"chain_statusline": "exit 1"}))  # a broken previous line never hides ours
            self.assertTrue(run("statusline.py", stdin=sl_payload(five=12)).stdout.startswith("5h 12%"))
        finally:
            cfg.unlink(missing_ok=True)


class CLI(unittest.TestCase):
    def setUp(self):
        clean()
        write_reading(five=50, seven=20)

    def code(self, *args, env=IN_CC):
        return run("cli.py", args, env=env).returncode

    def test_exit_codes(self):
        self.assertEqual(self.code(), 0)
        self.assertEqual(self.code("--check", "90"), 0)
        self.assertEqual(self.code("--check", "50"), 2)
        self.assertEqual(self.code("--check", "90", "--check-7d", "20"), 2)
        self.assertEqual(self.code("--check-7d", "90"), 0)
        self.assertEqual(self.code("--check-7d", "10"), 2)

    def test_unknown_cases_exit_3(self):
        clean()
        self.assertEqual(self.code("--check", "90"), 3)
        write_reading(available=False)
        self.assertEqual(self.code("--check", "90"), 3)

    def test_outside_claude_code(self):
        p = run("cli.py", env=OUT_CC)
        self.assertEqual(p.returncode, 3)
        self.assertIn("only runs inside Claude Code", p.stderr)
        self.assertEqual(p.stdout, "")

    def test_json(self):
        r = json.loads(run("cli.py", ["--json"]).stdout)
        self.assertEqual(r["five_hour_pct"], 50)

    def test_bad_arg(self):
        self.assertEqual(self.code("--check", "abc"), 2)  # argparse usage error


class MCP(unittest.TestCase):
    def setUp(self):
        clean()
        write_reading(five=50, seven=20)

    def rpc(self, *msgs, env=IN_CC):
        p = run("mcp_server.py", stdin="\n".join(m if isinstance(m, str) else json.dumps(m) for m in msgs) + "\n", env=env)
        return p, [json.loads(l) for l in p.stdout.splitlines()]

    def call(self, args):
        _, out = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_usage", "arguments": args}})
        return out[0]["result"]

    def test_handshake_and_list(self):
        _, out = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                          {"jsonrpc": "2.0", "method": "notifications/initialized"},
                          {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                          {"jsonrpc": "2.0", "id": 3, "method": "ping"})
        self.assertEqual([m["id"] for m in out], [1, 2, 3])  # notification got no reply
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")
        props = out[1]["result"]["tools"][0]["inputSchema"]["properties"]
        self.assertEqual(set(props), {"stop_at_pct", "stop_at_7d_pct"})

    def test_errors(self):
        _, out = self.rpc("{bad json", {"jsonrpc": "2.0", "id": 1, "method": "nope"},
                          {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "other"}})
        self.assertEqual([m["error"]["code"] for m in out], [-32601, -32602])

    def test_plain_call(self):
        r = self.call({})
        self.assertFalse(r["isError"])
        data = json.loads(r["content"][1]["text"])
        self.assertNotIn("verdict", data)
        self.assertNotIn("session_id", data)  # private fields stripped
        self.assertNotIn("cwd", data)

    def test_verdicts(self):
        self.assertEqual(json.loads(self.call({"stop_at_pct": 90})["content"][1]["text"])["verdict"], "OK")
        self.assertEqual(json.loads(self.call({"stop_at_pct": 40})["content"][1]["text"])["verdict"], "STOP")
        r = self.call({"stop_at_pct": 90, "stop_at_7d_pct": 15})
        self.assertTrue(r["content"][0]["text"].startswith("STOP (7-day 20% >= 15%)"))
        self.assertEqual(json.loads(self.call({"stop_at_7d_pct": 15})["content"][1]["text"])["verdict"], "STOP")
        clean()
        self.assertEqual(json.loads(self.call({"stop_at_pct": 90})["content"][1]["text"])["verdict"], "UNKNOWN")

    def test_outside_claude_code(self):
        p, out = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, env=OUT_CC)
        self.assertEqual((p.returncode, out), (1, []))
        _, out = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_usage"}}, env=OUT_CC)
        self.assertTrue(out[0]["result"]["isError"])


class Static(unittest.TestCase):
    STDLIB = {"argparse", "datetime", "json", "os", "sys", "pathlib"}

    def test_stdlib_only_no_network_no_subprocess(self):
        for f in TOOL.glob("*.py"):
            for node in ast.walk(ast.parse(f.read_text())):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
                    for n in names:
                        root = n.split(".")[0]
                        allowed = self.STDLIB | {"usage_lib"} | ({"subprocess"} if f.name == "statusline.py" else set())
                        self.assertIn(root, allowed, f"{f.name}: imports {n}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
