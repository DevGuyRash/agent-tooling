"""How each launcher starts its executor: the command line and environment it builds for an arm's turns and for a
judge, checked against what the removed drivers passed, with the executor itself replaced by a recorder."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]


class Launched:
    """A stand-in for subprocess.run that records each command and writes the events a real executor would print."""

    def __init__(self, events):
        self.calls, self.events = [], events

    def __call__(self, cmd, input=None, stdout=None, stderr=None, env=None, **_):
        self.calls.append({"cmd": cmd, "env": env, "input": input})
        if stdout is not None:
            stdout.write(("\n".join(json.dumps(e) for e in self.events.pop(0)) + "\n").encode())
        return mock.Mock(returncode=0, stderr=b"")


class LauncherCase(unittest.TestCase):
    name = ""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="launcher-invocation-"))
        self.home, self.work, self.job = self.tmp / "home", self.tmp / "work", self.tmp
        self.home.mkdir()
        self.work.mkdir()
        (self.tmp / "instructions.md").write_text("Be brief.\n")
        (self.tmp / "turn.md").write_text("do it")
        self.env = {"HOME": str(self.home), "TRIAL_MODEL": "model-a", "TRIAL_INSTRUCTIONS": str(self.tmp / "instructions.md"),
                    "TRIAL_PROMPT_FILE": str(self.tmp / "turn.md"), "TRIAL_RECORD": str(self.tmp / "record.json"),
                    "TRIAL_JOB_DIR": str(self.job), "TRIAL_TURNS": "2", "TRIAL_CONFINED": "1"}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def launcher(self, **env):
        """The launcher module loaded afresh with this environment, as a run's process would see it."""
        with mock.patch.dict(os.environ, {**self.env, **env}, clear=False):
            spec = importlib.util.spec_from_file_location(f"invoked_{self.name}", HERE / f"{self.name}.py")
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def turn(self, module, number, launched, **env):
        with mock.patch.dict(os.environ, {**self.env, "TRIAL_TURN": str(number),
                                          "TRIAL_REPLY": str(self.tmp / f"final-{number - 1}.md"), **env}), \
                mock.patch.object(module.subprocess, "run", launched), mock.patch("os.getcwd", return_value=str(self.work)):
            return module.main()


class CodexInvocationTest(LauncherCase):
    name = "codex"

    def test_setup_turns_and_resume_match_the_old_driver(self):
        (self.home / ".launcher").mkdir()
        (self.home / ".launcher" / "host-codex.toml").write_text(
            'model_provider = "proxy"\n[model_providers.proxy]\nbase_url = "https://proxy.example/v1"\nenv_key = "K"\n')
        module = self.launcher()
        with mock.patch.dict(os.environ, {**self.env, "TRIAL_TURN": "0"}):
            self.assertEqual(module.main(), 0)
        self.assertFalse((self.home / ".launcher" / "host-codex.toml").exists())  # nothing but the provider block stays
        self.assertIn('base_url = "https://proxy.example/v1"', (self.home / ".codex" / "config.toml").read_text())
        self.assertEqual((self.home / ".codex" / "AGENTS.md").read_text(), "Be brief.\n")
        launched = Launched([[{"type": "thread.started", "thread_id": "T9"}, {"type": "turn.completed", "usage": {}}],
                             [{"type": "turn.completed", "usage": {}}]])
        self.assertEqual(self.turn(module, 1, launched, TRIAL_EFFORT="low", K="secret-value"), 0)
        first = launched.calls[0]["cmd"]
        self.assertEqual(first[1:2], ["exec"])
        for flag in (["-s", "danger-full-access"], ["-m", "model-a"], ["-c", "model_reasoning_effort=low"], ["-C", str(self.work)]):
            self.assertIn(flag, [first[i:i + 2] for i in range(len(first) - 1)])
        self.assertEqual(launched.calls[0]["input"], b"do it")
        self.assertEqual(launched.calls[0]["env"]["CODEX_HOME"], str(self.home / ".codex"))
        self.assertEqual(self.turn(module, 2, launched, TRIAL_EFFORT="low"), 0)
        second = launched.calls[1]["cmd"]
        self.assertEqual(second[second.index("resume"):second.index("resume") + 2], ["resume", "T9"])

    def test_a_judge_runs_read_only_at_high_effort_with_the_schema_and_prints_only_its_verdict(self):
        module = self.launcher()
        with mock.patch.dict(os.environ, {**self.env, "TRIAL_TURN": "0", "TRIAL_INSTRUCTIONS": ""}):
            module.main()
        schema = self.tmp / "schema.json"
        schema.write_text("{}")
        (self.tmp / "final-0.md").write_text('{"verdict": "pass", "reason": "ok"}')
        launched = Launched([[{"type": "thread.started", "thread_id": "J"}, {"type": "turn.completed", "usage": {}}]])
        out = []
        with mock.patch.object(sys, "stdout", mock.Mock(write=out.append)):
            self.assertEqual(self.turn(module, 1, launched, TRIAL_SCHEMA_FILE=str(schema), TRIAL_TURNS="1"), 0)
        cmd = launched.calls[0]["cmd"]
        pairs = [cmd[i:i + 2] for i in range(len(cmd) - 1)]
        for flag in (["-s", "read-only"], ["-c", "model_reasoning_effort=high"], ["--output-schema", str(schema)]):
            self.assertIn(flag, pairs)
        self.assertIn("--ephemeral", cmd)
        self.assertEqual(json.loads("".join(out)), {"verdict": "pass", "reason": "ok"})


class ClaudeInvocationTest(LauncherCase):
    name = "claude"

    def test_turns_resume_the_first_session_with_the_old_drivers_flags(self):
        module = self.launcher()
        with mock.patch.dict(os.environ, {**self.env, "TRIAL_TURN": "0"}):
            module.main()
        init = {"type": "system", "subtype": "init", "session_id": "S7", "model": "model-a"}
        result = {"type": "result", "subtype": "success", "is_error": False, "result": "done", "session_id": "S7", "usage": {}}
        launched = Launched([[init, result], [result]])
        env = {"TRIAL_EFFORT": "medium", "TRIAL_API_KEY_VAR": "MY_KEY", "MY_KEY": "secret-value",
               "TRIAL_BASE_URL": "https://proxy.example"}
        self.assertEqual(self.turn(module, 1, launched, **env), 0)
        first = launched.calls[0]["cmd"]
        pairs = [first[i:i + 2] for i in range(len(first) - 1)]
        self.assertEqual(first[1:3], ["-p", "--bare"])
        for flag in (["--model", "model-a"], ["--effort", "medium"], ["--permission-mode", "bypassPermissions"],
                     ["--append-system-prompt-file", str(self.tmp / "instructions.md")], ["--output-format", "stream-json"]):
            self.assertIn(flag, pairs)
        self.assertNotIn("--resume", first)
        self.assertEqual(launched.calls[0]["env"]["ANTHROPIC_API_KEY"], "secret-value")
        self.assertEqual(launched.calls[0]["env"]["ANTHROPIC_BASE_URL"], "https://proxy.example")
        self.assertEqual((self.tmp / "final-0.md").read_text(), "done")
        self.assertEqual(self.turn(module, 2, launched, **env), 0)
        second = launched.calls[1]["cmd"]
        self.assertEqual(second[second.index("--resume"):second.index("--resume") + 2], ["--resume", "S7"])

    def test_an_unconfined_run_accepts_edits_and_a_judge_has_no_tools(self):
        module = self.launcher()
        with mock.patch.dict(os.environ, {**self.env, "TRIAL_TURN": "0"}):
            module.main()
        schema = self.tmp / "schema.json"
        schema.write_text('{"type": "object"}')
        result = {"type": "result", "subtype": "success", "is_error": False, "session_id": "S",
                  "structured_output": {"verdict": "fail", "reason": "no"}, "usage": {}}
        launched = Launched([[{"type": "system", "subtype": "init", "session_id": "S"}, result]])
        out = []
        with mock.patch.object(sys, "stdout", mock.Mock(write=out.append)):
            self.turn(module, 1, launched, TRIAL_CONFINED="0", TRIAL_SCHEMA_FILE=str(schema), TRIAL_TURNS="1")
        cmd = launched.calls[0]["cmd"]
        pairs = [cmd[i:i + 2] for i in range(len(cmd) - 1)]
        for flag in (["--permission-mode", "acceptEdits"], ["--tools", ""], ["--json-schema", '{"type": "object"}']):
            self.assertIn(flag, pairs)
        self.assertEqual(json.loads("".join(out)), {"verdict": "fail", "reason": "no"})


if __name__ == "__main__":
    unittest.main()
