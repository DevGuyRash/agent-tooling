"""Behavior of the trial runner, exercised with the deterministic command executor."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "trial.py"
sys.path.insert(0, str(SCRIPT.parent))
import trial  # noqa: E402


def write(path: Path, text: str, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mode:
        path.chmod(mode)


class TrialRunnerTest(unittest.TestCase):
    def setUp(self):
        # Confinement needs bubblewrap; a host without it (macOS, or Linux missing the package) runs every
        # plain command-arm test unconfined instead of refusing outright. Tests specific to confinement
        # itself are separately @unittest.skipUnless(shutil.which("bwrap"), ...).
        self.default_sandbox = "confined" if shutil.which("bwrap") else "none"
        self.tmp = Path(tempfile.mkdtemp(prefix="trial-test-", dir=Path.home() / ".cache"))
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file", "tool_called"]}))
        write(s / "fixture" / "seed.txt", "seed\n")
        write(s / "setup.sh", "echo prepared > prepared.txt\n")
        write(s / "bin" / "faketool", '#!/bin/sh\necho "{\\"tool\\": \\"faketool\\", \\"args\\": \\"$*\\"}" >> "$TRIAL_HARNESS/calls.jsonl"\n', 0o755)
        write(s / "check.py", (
            "def check(run):\n"
            "    return {'made_file': run.file('out.txt').strip() == 'hi',\n"
            "            'saw_fixture': run.file('seed.txt') == 'seed\\n',\n"
            "            'setup_ran': run.file('prepared.txt').strip() == 'prepared',\n"
            "            'tool_called': any(c.get('tool') == 'faketool' for c in run.calls),\n"
            "            'prompt_seen': run.file('prompt.txt').strip() == 'create out.txt'}\n"))
        write(self.tmp / "plan.json", json.dumps({
            "name": "unit", "repeats": 2, "seed": 3, "sandbox": self.default_sandbox,
            "arms": {"good": {"executor": "command", "command": 'echo hi > out.txt; faketool x; printf "%s" "$TRIAL_PROMPT" > prompt.txt'},
                     "bad": {"executor": "command", "command": "true"}},
            "scenarios": ["scenarios/make-file"]}))
        self.out = self.tmp / "out"

    def tearDown(self):
        subprocess.run(["chmod", "-R", "u+rwx", str(self.tmp)], capture_output=True)
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=300)

    def results(self):
        return {p.parent.name: json.loads(p.read_text()) for p in (self.out / "runs").glob("*/result.json")}

    def judge_cell(self, job_name, out=None):
        """The opaque directory (see trial._judge_cell_dir/judge_run) a job's judge verdict actually lives
        under, looked up the same way a person would: from the run's own result.json. One level below the
        cell trial._judge_cell_dir names, exactly as judge_run itself nests the real work (see its own
        docstring for why: an unconfined escape two directories up from a judge's own cwd must land on
        this one run's own cell, never the .cells directory every run's cell sits in side by side)."""
        return (out or self.out) / "judges" / ".cells" / self.results()[job_name]["judge_cell"] / "judge"

    def test_runs_every_arm_repeatedly_and_scores_required_checks(self):
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--jobs", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()
        self.assertEqual(len(res), 4)
        for job, v in res.items():
            self.assertTrue(v["checks"]["saw_fixture"] and v["checks"]["setup_ran"], job)
            self.assertEqual(v["passed"], v["arm"] == "good", job)
        self.assertTrue(res["make-file__good__r1"]["checks"]["prompt_seen"])
        self.assertIn("| make-file | 0/2", r.stdout)
        self.assertIn("2/2", r.stdout)

    def test_fixture_copy_skips_git_and_pycache_like_copy_workdir_does(self):
        write(self.tmp / "scenarios" / "make-file" / "fixture" / ".git" / "config", "[core]\n")
        write(self.tmp / "scenarios" / "make-file" / "fixture" / "__pycache__" / "m.pyc", "x")
        write(self.tmp / "scenarios" / "make-file" / "fixture" / "kept.txt", "kept\n")
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--arms", "good", "--repeats", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        work = self.out / "runs" / "make-file__good__r1" / "work"
        self.assertTrue((work / "kept.txt").exists())
        self.assertFalse((work / ".git").exists())
        self.assertFalse((work / "__pycache__").exists())

    def test_rerun_reuses_finished_results_and_replaces_partial_ones(self):
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        done = self.out / "runs" / "make-file__good__r1" / "result.json"
        stamp = done.stat().st_mtime_ns
        partial = self.out / "runs" / "make-file__bad__r2"
        (partial / "result.json").unlink()
        (partial / "work" / "stale.txt").write_text("stale")
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(done.stat().st_mtime_ns, stamp)
        self.assertFalse((partial / "work" / "stale.txt").exists())
        self.assertTrue((partial / "result.json").exists())
        # A result.json from an attempt the runner never finished (an agent can write one) is not trusted.
        (partial / "result.json").write_text(json.dumps(dict(json.loads((partial / "result.json").read_text()), passed=True)))
        (self.out / "runs" / "make-file__bad__r2.pending").touch()
        self.assertNotIn("make-file__bad__r2", self.run_cli("summarize", str(self.out), "--json").stdout.replace("|", " "))
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        self.assertFalse(self.results()["make-file__bad__r2"]["passed"])
        self.assertFalse((self.out / "runs" / "make-file__bad__r2.pending").exists())

    def test_interleaves_arms_within_each_repeat(self):
        plan = trial.load_plan(self.tmp / "plan.json", None, None, None)
        jobs = trial.schedule(plan)
        self.assertEqual([r for _, _, r in jobs], [1, 1, 2, 2])
        self.assertEqual(sorted(a for a, _, _ in jobs[:2]), ["bad", "good"])

    def test_refuses_output_inside_a_git_repository(self):
        repo = self.tmp / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)])
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(repo / "out"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("inside a git repository", r.stderr)

    def test_unknown_arm_names_valid_ones(self):
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--arms", "nope", "--dry-run")
        self.assertEqual(r.returncode, 2)
        self.assertIn("valid arms: good, bad", r.stderr)

    def test_broken_check_is_reported_not_passed(self):
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    raise ValueError('boom')\n")
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--arms", "good", "--repeats", "1")
        v = self.results()["make-file__good__r1"]
        self.assertIsNone(v["passed"])
        self.assertIn("boom", v["checks"]["check_error"])

    def test_check_that_cannot_load_is_reported_and_the_trial_continues(self):
        write(self.tmp / "scenarios" / "make-file" / "check.py", "from helper import missing\n")
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()
        self.assertEqual(len(res), 2)
        self.assertTrue(all(v["passed"] is None and "loading check.py" in v["checks"]["check_error"] for v in res.values()))

    def test_shared_helpers_edited_during_a_trial_are_reloaded(self):
        shared = self.tmp / "scenarios" / "_shared"
        write(shared / "helper.py", "VALUE = 'old'\n")
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1] / '_shared'))\n"
              "from helper import VALUE\ndef check(run):\n    return {'value': VALUE}\n")
        spec = {"name": "make-file", "dir": str(self.tmp / "scenarios" / "make-file")}
        self.assertEqual(trial._load_checks(spec).check(None)["value"], "old")
        write(shared / "helper.py", "VALUE = 'new'\nEXTRA = 1\n")
        self.assertEqual(trial._load_checks(spec).check(None)["value"], "new")

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap: unconfined mode intentionally forwards the parent PATH")
    def test_isolated_environment_hides_user_paths_and_scenario_location(self):
        write(self.tmp / "scenarios" / "make-file" / "check.py", (
            "def check(run):\n"
            "    env = dict(l.split('=', 1) for l in run.file('env.txt').splitlines() if '=' in l)\n"
            "    return {'fake_home': env.get('HOME', '').endswith('/harness/home'),\n"
            "            'no_user_prefix_bin': '.local/bin' not in env.get('PATH', ''),\n"
            "            'tools_copied': env.get('PATH', '').split(':')[0].endswith('/tools'),\n"
            "            'no_ssh_agent': 'SSH_AUTH_SOCK' not in env,\n"
            "            'private_git': env.get('GIT_CONFIG_GLOBAL', '').endswith('/harness/.gitconfig')}\n"))
        write(self.tmp / "plan.json", json.dumps({"name": "env", "repeats": 1, "arms": {"a": {"executor": "command", "command": "env > env.txt"}},
                                                  "scenarios": ["scenarios/make-file"]}))
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        checks = self.results()["make-file__a__r1"]["checks"]
        self.assertTrue(all(checks.values()), checks)

    def test_failure_breaker_skips_a_failing_family_and_a_rerun_picks_it_up(self):
        write(self.tmp / "plan.json", json.dumps({
            "name": "breaker", "repeats": 8, "seed": 3, "sandbox": self.default_sandbox,
            "arms": {"down": {"executor": "command", "model": "m-down", "pass_env": ["TRIAL_TEST_UP"],
                              "command": '[ -n "$TRIAL_TEST_UP" ] || exit 1; echo hi > out.txt; faketool x'},
                     "up": {"executor": "command", "command": 'echo hi > out.txt; faketool x', "model": "m-up"}},
            "scenarios": ["scenarios/make-file"]}))
        env = dict(os.environ, TRIAL_FAILURE_STREAK="3")
        r = subprocess.run([sys.executable, str(SCRIPT), "run", str(self.tmp / "plan.json"), "--out", str(self.out), "--jobs", "1"],
                           capture_output=True, text=True, timeout=300, env=env)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("runs skipped", r.stderr)
        self.assertIn("breaker:", r.stdout)
        res = self.results()
        self.assertEqual(sum(1 for k in res if "__down__" in k), 3)
        self.assertEqual(sum(1 for k in res if "__up__" in k), 8)
        env["TRIAL_TEST_UP"] = "1"  # the cause is fixed outside the plan, as an exhausted quota would be
        r = subprocess.run([sys.executable, str(SCRIPT), "run", str(self.tmp / "plan.json"), "--out", str(self.out), "--jobs", "1"],
                           capture_output=True, text=True, timeout=300, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sum(1 for k in self.results() if "__down__" in k), 8)

    def test_recheck_rescores_stored_runs_without_rerunning(self):
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1")
        self.assertFalse(self.results()["make-file__bad__r1"]["passed"])
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    return {'made_file': True, 'tool_called': True}\n")
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.results()["make-file__bad__r1"]["passed"])
        self.assertIn("rechecked 2 runs", r.stdout)

    def test_derive_turns_produced_artifacts_into_arms_and_groups_them(self):
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        consumer = self.tmp / "scenarios" / "consume"
        write(consumer / "scenario.json", json.dumps({"prompt": "go", "required": ["saw_hi"]}))
        write(consumer / "check.py", "def check(run):\n    return {'saw_hi': run.file('seen.txt').strip() == 'hi'}\n")
        plan = self.tmp / "derived.json"
        r = self.run_cli("derive", str(self.out), "--scenario", "make-file", "--artifact", "out.txt", "--consumer", str(consumer),
                         "--executor", json.dumps({"executor": "command", "command": "cp \"$TRIAL_INSTRUCTIONS\" seen.txt"}),
                         "--repeats", "1", "--plan", str(plan))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 derived arms", r.stdout)
        arms = json.loads(plan.read_text())["arms"]
        self.assertEqual(sorted(arms), ["good~r1", "good~r2"])
        rel = os.path.relpath(self.tmp / "keys.env")
        r = self.run_cli("derive", str(self.out), "--scenario", "make-file", "--artifact", "out.txt", "--consumer", str(consumer),
                         "--executor", json.dumps({"executor": "command", "command": "true", "env_file": rel}),
                         "--plan", str(self.tmp / "gen" / "rel.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        derived = json.loads((self.tmp / "gen" / "rel.json").read_text())["arms"]["good~r1"]["env_file"]
        self.assertEqual((self.tmp / "gen" / derived).resolve(), (self.tmp / "keys.env").resolve())
        r = self.run_cli("derive", str(self.out), "--scenario", "make-file", "--artifact", "out.txt", "--consumer", str(consumer),
                         "--executor", "not json", "--plan", str(plan))
        self.assertIn("--executor is not valid JSON", r.stderr)
        out2 = self.tmp / "out2"
        # derive's own generated plan names no sandbox default; --sandbox here is the test's, not derive's.
        self.run_cli("run", str(plan), "--out", str(out2), "--sandbox", self.default_sandbox)
        s = self.run_cli("summarize", str(out2), "--group").stdout
        self.assertIn("| consume | 2/2", s)

    def test_stops_before_the_disk_fills(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "run", str(self.tmp / "plan.json"), "--out", str(self.out)],
                           capture_output=True, text=True, env={**__import__("os").environ, "TRIAL_MIN_FREE_GB": "999999"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("stopping before the disk fills", r.stderr)

    def test_claude_executor_passes_proxy_settings_and_captures_the_result(self):
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\n"
                    "[ -n \"$ANTHROPIC_API_KEY\" ] && k=set || k=unset\n"
                    "printf '%s %s\\n' \"$ANTHROPIC_BASE_URL\" \"$k\" > seen.txt\n"
                    "cat >/dev/null\n"
                    "echo '{\"type\": \"result\", \"result\": \"all done\", \"usage\": {\"output_tokens\": 3}}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip(), 'final': run.final_message}\n")
        # Confined where bubblewrap exists; hosts without it (CI runners) exercise the same proxy path unconfined.
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), sandbox="confined" if shutil.which("bwrap") else "none")))
        write(self.tmp / "plan.json", json.dumps({"name": "claude", "repeats": 1, "scenarios": ["scenarios/make-file"],
            "arms": {"c": {"executor": "claude", "model": "m", "binary": str(fake), "base_url": "http://proxy.invalid",
                           "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()["make-file__c__r1"]
        self.assertEqual(res["checks"]["seen"], "http://proxy.invalid set")
        self.assertEqual(res["checks"]["final"], "all done")
        self.assertEqual(res["usage"].get("output_tokens"), 3)
        # the effective default permission_mode (which differs between confined and unconfined - bypassing
        # permissions is only safe inside the sandbox) is recorded in the run's identity, not left implicit,
        # so a rerun comparing a confined and an unconfined Claude arm under different defaults is refused.
        expected_mode = "bypassPermissions" if shutil.which("bwrap") else "acceptEdits"
        self.assertEqual(res["identity"]["permission_mode"], expected_mode)

    # A fake `gemini` that records what it was invoked with and replies in Gemini CLI's own "-o stream-json"
    # shape (see trials.md): "message"/"assistant" text arrives as delta chunks (never one complete-message
    # event), so a turn's final message is their concatenation; usage is a per-call "stats" object on the
    # final "result" event, not a running total (see run_gemini, _usage).
    # No "-p" is ever passed any more (see run_gemini): the prompt always arrives on stdin, read once
    # before argv is even parsed, the same way the real CLI is documented to run headless whenever stdin
    # is not a terminal - which a subprocess's own piped stdin always is (see _run).
    GEMINI_FAKE = ("#!/bin/sh\n"
                  "promptval=$(cat)\n"
                  "skiptrust=no; approval=\"\"; outfmt=\"\"; model=\"\"; sid=\"\"; mode=new; prev=\"\"\n"
                  "for a in \"$@\"; do\n"
                  "  case \"$a\" in --skip-trust) skiptrust=yes ;; esac\n"
                  "  case \"$prev\" in\n"
                  "    -m) model=$a ;;\n"
                  "    --approval-mode) approval=$a ;;\n"
                  "    -o) outfmt=$a ;;\n"
                  "    --session-id) sid=$a; mode=new ;;\n"
                  "    --resume) sid=$a; mode=resume ;;\n"
                  "  esac\n"
                  "  prev=$a\n"
                  "done\n"
                  "printf '%s %s\\n' \"$mode\" \"$sid\" >> session-ids.txt\n"
                  "if [ \"$mode\" = new ]; then printf '%s' \"$promptval\" > turn0-prompt.txt\n"
                  "else printf '%s' \"$promptval\" > turn1-prompt.txt\n"
                  "fi\n"
                  "printf '%s %s %s %s %s\\n' \"$model\" \"$approval\" \"$skiptrust\" \"${GEMINI_API_KEY:+set}\" "
                  "\"$GOOGLE_GEMINI_BASE_URL\" > seen.txt\n"
                  "cat \"$HOME/.gemini/GEMINI.md\" 2>/dev/null > gemini-md-seen.txt || echo MISSING > gemini-md-seen.txt\n"
                  "printf '%s\\n' \"$HOME\" > home-seen.txt\n"
                  "echo \"{\\\"type\\\": \\\"init\\\", \\\"session_id\\\": \\\"$sid\\\", \\\"model\\\": \\\"$model\\\"}\"\n"
                  "if [ \"$mode\" = new ]; then\n"
                  "  echo '{\"type\": \"message\", \"role\": \"assistant\", \"content\": \"hello \", \"delta\": true}'\n"
                  "  echo '{\"type\": \"message\", \"role\": \"assistant\", \"content\": \"world\", \"delta\": true}'\n"
                  "else\n"
                  "  echo '{\"type\": \"message\", \"role\": \"assistant\", \"content\": \"again\", \"delta\": true}'\n"
                  "fi\n"
                  "echo '{\"type\": \"tool_use\", \"tool_name\": \"run_shell_command\", \"tool_id\": \"1\", "
                  "\"parameters\": {\"command\": \"echo hi\"}}'\n"
                  "echo '{\"type\": \"tool_result\", \"tool_id\": \"1\", \"status\": \"success\", \"output\": \"hi\"}'\n"
                  "echo '{\"type\": \"result\", \"status\": \"success\", "
                  "\"stats\": {\"input_tokens\": 5, \"output_tokens\": 3, \"total_tokens\": 8}}'\n")

    def test_gemini_executor_passes_settings_and_captures_the_result(self):
        fake = self.tmp / "bin" / "gemini"
        write(fake, self.GEMINI_FAKE, 0o755)
        write(self.tmp / "arms" / "k.md", "be terse\n")
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip(), 'final': run.final_message, "
              "'gemini_md': run.file('gemini-md-seen.txt').strip()}\n")
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        write(self.tmp / "plan.json", json.dumps({"name": "gemini", "repeats": 1, "sandbox": self.default_sandbox,
            "scenarios": ["scenarios/make-file"],
            "arms": {"g": {"executor": "gemini", "model": "m", "binary": str(fake), "instructions": "arms/k.md",
                           "base_url": "https://gateway.invalid", "api_key_var": "TRIAL_TEST_KEY",
                           "env_file": str(env_file)}}}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()["make-file__g__r1"]
        expected_approval = "yolo" if shutil.which("bwrap") else "auto_edit"
        self.assertEqual(res["checks"]["seen"], f"m {expected_approval} yes set https://gateway.invalid")
        self.assertEqual(res["checks"]["final"], "hello world")
        self.assertEqual(res["checks"]["gemini_md"], "be terse")
        self.assertEqual(res["usage"].get("input_tokens"), 5)
        self.assertEqual(res["usage"].get("output_tokens"), 3)
        self.assertEqual(res["commands"], 1)  # the run_shell_command tool_use event
        self.assertEqual(res["identity"]["approval_mode"], expected_approval)

    def test_gemini_home_is_the_runs_private_home_and_a_followup_resumes_the_session(self):
        fake = self.tmp / "bin" / "gemini"
        write(fake, self.GEMINI_FAKE, 0o755)
        write(self.tmp / "scenarios" / "make-file" / "scenario.json",
              json.dumps({"prompt": "go", "followups": ["again"], "required": ["home_is_private", "same_session_both_turns"]}))
        write(self.tmp / "scenarios" / "make-file" / "check.py", (
            "def check(run):\n"
            "    expected_home = str(run.dir / 'harness' / 'home')\n"
            "    ids = [l.split() for l in run.file('session-ids.txt').splitlines() if l.strip()]\n"
            "    sessions = {sid for _mode, sid in ids}\n"
            "    return {'home_is_private': run.file('home-seen.txt').strip() == expected_home,\n"
            "            'same_session_both_turns': len(ids) == 2 and len(sessions) == 1 and sessions != {''},\n"
            "            'first_turn_used_session_id': ids[0][0] == 'new',\n"
            "            'followup_used_resume': ids[1][0] == 'resume',\n"
            "            'followup_prompt': run.file('turn1-prompt.txt').strip() == 'again'}\n"))
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        gemini = {"g": {"executor": "gemini", "model": "m", "binary": str(fake),
                       "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(gemini), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        result = self.results()["make-file__g__r1"]
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(all(result["checks"].values()), result["checks"])
        self.assertTrue(result["passed"])

    def test_a_planted_gemini_geminimd_refuses_the_run_instead_of_being_silently_overwritten(self):
        # Mirrors test_a_planted_agents_md_refuses_the_run_even_for_an_arm_with_no_instructions_of_its_own for
        # codex: a scenario's setup.sh (which runs before the executor, with the same $HOME) may already have
        # put a GEMINI.md there, which must never be silently overwritten or silently kept while another arm
        # gets its own (see trials.md, "no plugins, skills, memories, or user instructions load beyond the arm's").
        s = self.tmp / "scenarios" / "make-file"
        write(s / "setup.sh", 'mkdir -p "$HOME/.gemini" && echo "SCENARIO GLOBAL GEMINI.MD" > "$HOME/.gemini/GEMINI.md"\n')
        gemini = {"g": {"executor": "gemini", "model": "m", "binary": str(self.tmp / "bin" / "gemini")}}  # no "instructions"
        r = self.run_cli("run", self._plan(gemini), "--out", str(self.out))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("GEMINI.md", r.stderr)
        self.assertIn("already exists", r.stderr)

    def test_gemini_copy_auth_is_an_explicit_opt_in_and_needs_no_key(self):
        fake_oauth = self.tmp / "fake-oauth_creds.json"
        fake_oauth.write_text('{"fake": "gemini-oauth"}')
        fake_accounts = self.tmp / "fake-google_accounts.json"
        fake_accounts.write_text('{"fake": "gemini-account"}')
        saved = trial._GEMINI_AUTH_FILES
        trial._GEMINI_AUTH_FILES = ((fake_oauth, "oauth_creds.json", True), (fake_accounts, "google_accounts.json", False))
        try:
            write(self.tmp / "scenarios" / "make-file" / "check.py",
                  "def check(run):\n    return {'oauth': run.file('oauth-seen.txt').strip(), "
                  "'accounts': run.file('accounts-seen.txt').strip(), 'gca': run.file('gca-seen.txt').strip()}\n")
            fake = self.tmp / "bin" / "gemini"
            write(fake, "#!/bin/sh\n"
                        "cat \"$HOME/.gemini/oauth_creds.json\" > oauth-seen.txt 2>/dev/null || echo MISSING > oauth-seen.txt\n"
                        "cat \"$HOME/.gemini/google_accounts.json\" > accounts-seen.txt 2>/dev/null || echo MISSING > accounts-seen.txt\n"
                        "printf '%s' \"${GOOGLE_GENAI_USE_GCA:-unset}\" > gca-seen.txt\n"
                        "echo '{\"type\": \"result\", \"status\": \"success\"}'\n", 0o755)
            gemini = {"g": {"executor": "gemini", "model": "m", "binary": str(fake), "copy_auth": True}}
            # in-process (trial.main), not the subprocess self.run_cli uses: a subprocess re-imports trial.py
            # and would read this host's own real ~/.gemini login instead of this test's monkeypatched files.
            self.assertEqual(trial.main(["run", self._plan(gemini), "--out", str(self.out)]), 0)
            res = self.results()["make-file__g__r1"]["checks"]
            self.assertEqual(res["oauth"], '{"fake": "gemini-oauth"}')
            self.assertEqual(res["accounts"], '{"fake": "gemini-account"}')
            self.assertEqual(res["gca"], "true")
            # the optional file's absence is not an error, only the required token file's is
            fake_accounts.unlink()
            self.assertEqual(trial.main(["run", self._plan(gemini), "--out", str(self.tmp / "out2")]), 0)
            fake_oauth.unlink()
            with self.assertRaisesRegex(trial.TrialError, 'copy_auth.*true.*does not exist'):
                trial._copy_gemini_auth({"copy_auth": True}, self.tmp / "dest-home", "arm using gemini")
        finally:
            trial._GEMINI_AUTH_FILES = saved

    def test_gemini_as_judge_parses_json_from_its_response_field(self):
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1")
        self.assertTrue(self.results()["make-file__good__r1"]["judge_missing"])
        fake = self.tmp / "bin" / "gemini"
        write(fake, r"""#!/bin/sh
promptval=$(cat)
prev=""; approval=""; outfmt=""; policy=""
for a in "$@"; do
  case "$prev" in
    --approval-mode) approval=$a ;;
    -o) outfmt=$a ;;
    --admin-policy) policy=$a ;;
  esac
  prev=$a
done
printf '%s' "$promptval" > judge-prompt-seen.txt
haskey=no
[ -n "$GEMINI_API_KEY" ] && haskey=yes
haspolicy=no
[ -n "$policy" ] && [ -f "$policy" ] && grep -q run_shell_command "$policy" && haspolicy=yes
printf '%s %s %s %s\n' "$approval" "$outfmt" "$haskey" "$haspolicy" > judge-seen.txt
json='{"response": "{\"verdict\": \"fail\", \"reason\": \"no\"}", "stats": {"input_tokens": 2, "output_tokens": 1}}'
printf '%s' "$json"
""", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "gemini", "model": "m2", "binary": str(fake), "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()["make-file__good__r1"]
        self.assertEqual((res["judge"]["verdict"], res["judge"]["judge_model"]), ("fail", "m2"))
        self.assertFalse(res["passed"])
        self.assertEqual(res["judge"]["usage"].get("input_tokens"), 2)
        cell = self.judge_cell("make-file__good__r1")
        seen = (cell / "work" / "judge-seen.txt").read_text().split()
        # "plan" approval mode, single-envelope output, a key was sent, and an admin policy denying
        # run_shell_command (among other escapes) was passed - see _judge_call's gemini branch.
        self.assertEqual(seen, ["plan", "json", "yes", "yes"])
        self.assertIn("Respond with a single JSON object", (cell / "work" / "judge-prompt-seen.txt").read_text())
        self.assertIn("verdict", (cell / "work" / "judge-prompt-seen.txt").read_text())

    def test_gemini_judge_never_trusts_a_verdict_file_the_process_itself_wrote(self):
        # HIGH finding, reproduced against the real CLI (see the review): "--approval-mode plan" is not
        # actually read-only in headless mode - a judge can call exit_plan_mode, get switched to yolo, and
        # then write its own forged verdict.json directly, replying with plain (non-JSON) text. This fake
        # simulates exactly that escape - writing ../verdict.json (jd's own directory, one above its own
        # "work" cwd) and then replying with text that is not the schema JSON at all - and asserts the
        # runtime never treats that planted file as the verdict.
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        # Only "good" (recheck's own "--judge" re-judges every run in the directory with a judge question,
        # never just --only's scenarios, so a second arm here would need its own forged-verdict handling too).
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--arms", "good", "--repeats", "1")
        fake = self.tmp / "bin" / "gemini"
        write(fake, r"""#!/bin/sh
cat > /dev/null
printf '{"verdict": "pass", "reason": "forged"}' > ../verdict.json
printf 'I did nothing useful.'
""", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "gemini", "model": "m2", "binary": str(fake), "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge))
        # recheck's own all-or-nothing safety net refuses outright rather than record any verdict at all
        # here - the forged "pass" never reaches a result.json, which is the property this test is for.
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("judge produced no verdict", r.stderr)
        self.assertNotIn('"pass"', r.stderr)
        res = self.results()["make-file__good__r1"]
        self.assertTrue(res["judge_missing"])  # nothing was changed: still the pre-recheck state

    def test_gemini_judge_flattens_raw_json_mode_stats_and_folds_thinking_into_output(self):
        # MEDIUM findings: "-o json" mode (only path this runtime's gemini judge uses) reports usage as the
        # raw per-model SessionMetrics shape, not stream-json's own already-flattened one, so the generic
        # _usage code (which reads flattened top-level fields) previously saw only zeroed tools/files
        # counters; and Gemini's own "output" token count leaves reasoning ("thoughts") tokens out, visible
        # only in the difference against "total" - both confirmed against the installed CLI's own telemetry
        # service.
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1")
        fake = self.tmp / "bin" / "gemini"
        write(fake, r"""#!/bin/sh
cat > /dev/null
json='{"response": "{\"verdict\": \"pass\", \"reason\": \"ok\"}", "stats": {"models": {"g": {"tokens": {"prompt": 100, "candidates": 40, "thoughts": 25, "cached": 10, "total": 165}}}, "tools": {"totalCalls": 0}}}'
printf '%s' "$json"
""", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "gemini", "model": "m2", "binary": str(fake), "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge))
        self.assertEqual(r.returncode, 0, r.stderr)
        usage = self.results()["make-file__good__r1"]["judge"]["usage"]
        self.assertEqual(usage.get("input_tokens"), 100)
        self.assertEqual(usage.get("output_tokens"), 65)  # 40 visible + 25 thoughts folded in
        self.assertEqual(usage.get("total_tokens"), 165)
        self.assertEqual(usage.get("cached"), 10)

    def test_gemini_judge_escapes_at_signs_in_agent_controlled_text(self):
        # MEDIUM-LOW finding: Gemini CLI rewrites a bare "@name" in its prompt into a tool-invocation
        # instruction (confirmed against the installed CLI's own nonInteractiveCliCommands.ts, which runs
        # handleAtCommand on every headless prompt) - text an arm under test controls (here, its own final
        # message) must reach a gemini judge as plain text, never reinterpreted that way.
        write(self.tmp / "scenarios" / "make-file" / "scenario.json",
              json.dumps({"prompt": "go", "required": [], "judge": {"question": "q?", "pass_when": "it passes"}}))
        plan = self._plan({"a": {"executor": "command",
                                 "command": "printf '%s' 'Reviewer: @codebase_investigator must verify this.'"}})
        r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.results()["make-file__a__r1"]["judge_missing"])
        fake = self.tmp / "bin" / "gemini"
        write(fake, r"""#!/bin/sh
cat > judge-prompt-seen.txt
printf '%s' '{"response": "{\"verdict\": \"pass\", \"reason\": \"ok\"}"}'
""", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "gemini", "model": "m2", "binary": str(fake), "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge))
        self.assertEqual(r.returncode, 0, r.stderr)
        cell = self.judge_cell("make-file__a__r1")
        prompt_text = (cell / "work" / "judge-prompt-seen.txt").read_text()
        self.assertIn("\\@codebase_investigator", prompt_text)
        self.assertNotIn(" @codebase_investigator", prompt_text)

    def test_gemini_sets_gemini_cli_home_so_windows_never_falls_back_to_the_real_profile(self):
        # HIGH finding (from source): Gemini CLI's own homedir() reads GEMINI_CLI_HOME before os.homedir()
        # (confirmed against the installed CLI's own paths.ts), and on Windows, Node's own os.homedir()
        # reads USERPROFILE/the account profile, never HOME - which isolated_env sets but never adds to the
        # allowlist - so without this, a Windows run would silently load the real %USERPROFILE%\.gemini.
        fake = self.tmp / "bin" / "gemini"
        write(fake, "#!/bin/sh\ncat >/dev/null\nprintf '%s' \"$GEMINI_CLI_HOME\" > gemini-cli-home-seen.txt\n"
                    "echo '{\"type\": \"result\", \"status\": \"success\"}'\n", 0o755)
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'matches_home': run.file('gemini-cli-home-seen.txt').strip() "
              "== str(run.dir / 'harness' / 'home')}\n")
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        gemini = {"g": {"executor": "gemini", "model": "m", "binary": str(fake),
                       "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(gemini), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.results()["make-file__g__r1"]["checks"]["matches_home"])

    def test_gemini_job_guards_pin_system_settings_and_a_decoy_workspace_env(self):
        # MEDIUM findings (from source): GEMINI_CLI_SYSTEM_SETTINGS_PATH/_DEFAULTS_PATH point at this run's
        # own files - the highest-priority settings tier, confirmed against the installed CLI's own
        # settings.ts - so a workspace settings.json can never turn confinement settings back off; a decoy,
        # empty <job_dir>/.gemini/.env is found by Gemini CLI's own upward .env search (confirmed against
        # its own env.ts) before it would otherwise reach a real ancestor .env.
        fake = self.tmp / "bin" / "gemini"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    "printf '%s\\n%s\\n' \"$GEMINI_CLI_SYSTEM_SETTINGS_PATH\" \"$GEMINI_CLI_SYSTEM_DEFAULTS_PATH\" "
                    "> guard-env-seen.txt\necho '{\"type\": \"result\", \"status\": \"success\"}'\n", 0o755)
        write(self.tmp / "scenarios" / "make-file" / "check.py", (
            "def check(run):\n"
            "    lines = run.file('guard-env-seen.txt').splitlines()\n"
            "    settings_path, defaults_path = lines[0], lines[1]\n"
            "    decoy = run.dir / '.gemini' / '.env'\n"
            "    return {'settings_is_own_file': settings_path == str(run.dir / 'gemini-system-settings.json'),\n"
            "            'defaults_is_own_file': defaults_path == str(run.dir / 'gemini-system-defaults.json'),\n"
            "            'settings_denies_mcp': 'mcpServers' in open(settings_path).read(),\n"
            "            'decoy_env_is_empty_file': decoy.is_file() and decoy.read_text() == ''}\n"))
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        gemini = {"g": {"executor": "gemini", "model": "m", "binary": str(fake),
                       "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(gemini), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()["make-file__g__r1"]["checks"]
        self.assertTrue(all(res.values()), res)

    def test_gemini_refuses_a_followup_when_the_workspace_gemini_settings_changed(self):
        # MEDIUM finding (from source): --skip-trust makes the workspace trusted, so a <work>/.gemini/
        # settings.json overrides this runtime's own settings.json - confirmed against the installed CLI's
        # own settings merge order (system > workspace > user > ...) - and an agent's own tool calls can
        # write one mid-turn. A later turn must never silently load whatever it left there.
        write(self.tmp / "scenarios" / "make-file" / "scenario.json",
              json.dumps({"prompt": "go", "followups": ["again"], "required": []}))
        fake = self.tmp / "bin" / "gemini"
        write(fake, r"""#!/bin/sh
cat > /dev/null
mode=new; prev=""
for a in "$@"; do
  case "$prev" in
    --session-id) mode=new ;;
    --resume) mode=resume ;;
  esac
  prev=$a
done
if [ "$mode" = new ]; then
  mkdir -p .gemini
  echo '{"planted": true}' > .gemini/settings.json
fi
echo '{"type": "result", "status": "success"}'
""", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        gemini = {"g": {"executor": "gemini", "model": "m", "binary": str(fake),
                       "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(gemini), "--out", str(self.out))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(".gemini", r.stderr)
        self.assertIn("changed since the previous turn", r.stderr)

    def test_gemini_prompt_goes_on_stdin_even_when_it_would_overflow_argv(self):
        # MEDIUM-HIGH finding: the prompt used to be a "-p" argv entry; Linux caps a single argument at
        # 128 KiB, and a long final message or judge prompt made the whole trial crash with E2BIG. Sending
        # it on stdin instead (see run_gemini) has no such limit; this prompt is well past that cap.
        fake = self.tmp / "bin" / "gemini"
        write(fake, "#!/bin/sh\nwc -c < /dev/stdin > prompt-size-seen.txt\n"
                    "echo '{\"type\": \"result\", \"status\": \"success\"}'\n", 0o755)
        big_prompt = "x" * (256 * 1024)
        write(self.tmp / "scenarios" / "make-file" / "scenario.json",
              json.dumps({"prompt": big_prompt, "required": []}))
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'size': int(run.file('prompt-size-seen.txt').strip())}\n")
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        gemini = {"g": {"executor": "gemini", "model": "m", "binary": str(fake),
                       "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(gemini), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.results()["make-file__g__r1"]["status"], "ok")
        self.assertEqual(self.results()["make-file__g__r1"]["checks"]["size"], len(big_prompt))

    def test_gemini_final_message_excludes_narration_before_the_last_tool_call(self):
        # HIGH finding: Gemini's own stream-json resets its own response text at each tool call, so text
        # written before a tool call ("I will look at X first") is narration, never the turn's real final
        # reply, and run.messages must not fragment one logical reply into per-chunk entries either.
        fake = self.tmp / "bin" / "gemini"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    "echo '{\"type\": \"message\", \"role\": \"assistant\", \"content\": \"I will look \", \"delta\": true}'\n"
                    "echo '{\"type\": \"message\", \"role\": \"assistant\", \"content\": \"first.\", \"delta\": true}'\n"
                    "echo '{\"type\": \"tool_use\", \"tool_name\": \"run_shell_command\", \"tool_id\": \"1\", "
                    "\"parameters\": {\"command\": \"echo hi\"}}'\n"
                    "echo '{\"type\": \"tool_result\", \"tool_id\": \"1\", \"status\": \"success\", \"output\": \"hi\"}'\n"
                    "echo '{\"type\": \"message\", \"role\": \"assistant\", \"content\": \"All done: \", \"delta\": true}'\n"
                    "echo '{\"type\": \"message\", \"role\": \"assistant\", \"content\": \"nothing else.\", \"delta\": true}'\n"
                    "echo '{\"type\": \"result\", \"status\": \"success\"}'\n", 0o755)
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'final': run.final_message, 'messages': run.messages}\n")
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        gemini = {"g": {"executor": "gemini", "model": "m", "binary": str(fake),
                       "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(gemini), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()["make-file__g__r1"]["checks"]
        self.assertEqual(res["final"], "All done: nothing else.")
        self.assertEqual(res["messages"], ["I will look first.", "All done: nothing else."])

    def test_gemini_copy_auth_with_base_url_is_refused(self):
        # LOW finding: with "copy_auth", run_gemini's own key-resolution branch never reads "base_url" at
        # all (it only reaches GOOGLE_GEMINI_BASE_URL on the api-key path), so it would be silently ignored.
        with self.assertRaisesRegex(trial.TrialError, 'both "copy_auth" and "base_url"'):
            trial.resolve_arm({"executor": "gemini", "model": "m", "copy_auth": True, "base_url": "http://x.invalid"},
                              "arm 'g'")

    def test_gemini_latest_no_match_hint_includes_gemini_flag(self):
        # LOW finding: the hint's own suggested `trial.py models --match ...` command omitted "--gemini",
        # so running it as printed would list the Codex provider (or, with --base-url, Claude format) - the
        # wrong catalog entirely - instead of the Gemini one the arm actually resolves against. resolve_arm
        # and `models --gemini --latest` both build this same "flags" suffix and pass it to latest_model.
        with self.assertRaisesRegex(trial.TrialError, r"models --match 'nope-\*' --gemini"):
            trial.latest_model("nope-*", ["gemini-2.5-pro"], "arm 'g'", " --gemini")
        # sanity check, same function: a non-gemini caller's own (empty) flags string is untouched
        with self.assertRaisesRegex(trial.TrialError, r"models --match 'nope-\*'`$"):
            trial.latest_model("nope-*", ["claude-x"], "arm 'g'", "")

    def test_gemini_model_listing_strips_the_models_prefix_and_paginates(self):
        import http.server
        import threading
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append((self.path, self.headers.get("x-goog-api-key")))
                second = "pageToken=" in self.path
                body = ({"models": [{"name": "models/gemini-2.5-flash"}]} if second else
                       {"models": [{"name": "models/gemini-2.5-pro"}], "nextPageToken": "p2"})
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            env_file = self.tmp / "keys.env"
            env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
            r = self.run_cli("models", "--gemini", "--base-url", f"http://127.0.0.1:{server.server_address[1]}",
                             "--env-file", str(env_file), "--api-key-var", "TRIAL_TEST_KEY")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(sorted(r.stdout.split()), ["gemini-2.5-flash", "gemini-2.5-pro"])
            self.assertEqual({k for _, k in seen}, {"not-a-real-key"})
        finally:
            server.shutdown()
            server.server_close()

    def test_gemini_default_key_variable_and_valid_judge_executor(self):
        self.assertEqual(trial._default_key_var("gemini"), "GEMINI_API_KEY")
        trial._check_judge({"executor": "gemini", "model": "m"}, "judge")  # does not raise
        with self.assertRaisesRegex(trial.TrialError, "codex, claude, gemini"):
            trial._check_judge({"executor": "nope", "model": "m"}, "judge")

    def test_gemini_preflight_checks_a_path_discovered_binary_before_scheduling_jobs(self):
        if not shutil.which("bwrap"):
            self.skipTest("needs bubblewrap")
        pathbin = self.tmp / "pathbin"
        write(pathbin / "gemini", "#!/bin/sh\nexit 7\n", 0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{pathbin}{os.pathsep}{old_path}"
        saved_bin = os.environ.pop("TRIAL_GEMINI_BIN", None)
        try:
            plan = self._plan({"g": {"executor": "gemini", "model": "m"}})  # no "binary": found on PATH
            out = self.tmp / "preflight-out"
            code = trial.main(["run", plan, "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertFalse(list(out.glob("runs/*")))  # nothing was scheduled at all
        finally:
            os.environ["PATH"] = old_path
            if saved_bin is not None:
                os.environ["TRIAL_GEMINI_BIN"] = saved_bin

    # --- Between-turn reseed must never follow a link an agent's own turn planted (HIGH, confirmed) -----

    def test_seed_gemini_home_refuses_when_home_itself_was_replaced_with_a_symlink(self):
        # Reproduces the confirmed finding: from inside its own turn, an agent can do `rm -rf $HOME/.gemini;
        # ln -s <host dir> $HOME/.gemini`. The next between-turn reseed must refuse rather than transparently
        # write through that link into whatever real host directory it points at.
        host_dir = self.tmp / "host-gemini-dir"
        write(host_dir / "GEMINI.md", "HOST OWNED\n")
        write(host_dir / "settings.json", '{"host": "owned"}')
        home_parent = self.tmp / "harness-home-a"
        home_parent.mkdir()
        home = home_parent / ".gemini"
        home.symlink_to(host_dir)
        with self.assertRaisesRegex(trial.TrialError, "no longer a real directory"):
            trial._seed_gemini_home(home, {})
        self.assertEqual((host_dir / "GEMINI.md").read_text(), "HOST OWNED\n")
        self.assertEqual((host_dir / "settings.json").read_text(), '{"host": "owned"}')

    def test_seed_gemini_home_replaces_a_symlinked_settings_file_without_following_it(self):
        host_file = self.tmp / "host-settings.json"
        host_file.write_text('{"host": "owned"}')
        home = self.tmp / "gemini-home-b" / ".gemini"
        home.mkdir(parents=True)
        (home / "settings.json").symlink_to(host_file)
        trial._seed_gemini_home(home, {})
        self.assertEqual(host_file.read_text(), '{"host": "owned"}')  # the host file itself was never touched
        self.assertFalse((home / "settings.json").is_symlink())  # replaced, not written through
        self.assertIn("checkpointing", (home / "settings.json").read_text())

    def test_seed_gemini_home_deletes_a_symlinked_geminimd_without_following_it(self):
        host_file = self.tmp / "host-gemini.md"
        host_file.write_text("HOST OWNED\n")
        home = self.tmp / "gemini-home-c" / ".gemini"
        home.mkdir(parents=True)
        (home / "GEMINI.md").symlink_to(host_file)
        trial._seed_gemini_home(home, {})  # no "instructions": the planted link should be removed, not followed
        self.assertEqual(host_file.read_text(), "HOST OWNED\n")
        self.assertFalse((home / "GEMINI.md").exists())

    def test_seed_gemini_home_writes_arm_instructions_without_following_a_symlinked_geminimd(self):
        host_file = self.tmp / "host-gemini2.md"
        host_file.write_text("HOST OWNED\n")
        instructions = self.tmp / "arm-instructions.md"
        instructions.write_text("be terse\n")
        home = self.tmp / "gemini-home-d" / ".gemini"
        home.mkdir(parents=True)
        (home / "GEMINI.md").symlink_to(host_file)
        trial._seed_gemini_home(home, {"instructions": str(instructions)})
        self.assertEqual(host_file.read_text(), "HOST OWNED\n")
        self.assertFalse((home / "GEMINI.md").is_symlink())
        self.assertEqual((home / "GEMINI.md").read_text(), "be terse\n")

    def test_seed_codex_home_refuses_when_home_itself_was_replaced_with_a_symlink(self):
        host_dir = self.tmp / "host-codex-dir"
        write(host_dir / "AGENTS.md", "HOST OWNED\n")
        home_parent = self.tmp / "harness-home-e"
        home_parent.mkdir()
        home = home_parent / ".codex"
        home.symlink_to(host_dir)
        with self.assertRaisesRegex(trial.TrialError, "no longer a real directory"):
            trial._seed_codex_home(home, {"model": "m"})
        self.assertEqual((host_dir / "AGENTS.md").read_text(), "HOST OWNED\n")

    def test_seed_codex_home_replaces_a_symlinked_config_without_following_it(self):
        host_file = self.tmp / "host-config.toml"
        host_file.write_text("[host]\nowned = true\n")
        home = self.tmp / "codex-home-f" / ".codex"
        home.mkdir(parents=True)
        (home / "config.toml").symlink_to(host_file)
        trial._seed_codex_home(home, {"model": "m"})
        self.assertEqual(host_file.read_text(), "[host]\nowned = true\n")
        self.assertFalse((home / "config.toml").is_symlink())
        self.assertIn('model = "m"', (home / "config.toml").read_text())

    def test_recheck_with_another_judge_replaces_verdicts(self):
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        # The plan names no judge yet: a judge question under a judge-less plan is invalid, never a silent pass.
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1")
        first = self.results()["make-file__good__r1"]
        self.assertIsNone(first["passed"])
        self.assertTrue(first["judge_missing"])
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\n"
                    "[ -n \"$ANTHROPIC_API_KEY\" ] && [ \"$ANTHROPIC_BASE_URL\" = http://proxy.invalid ] || exit 3\n"
                    "cat >/dev/null\n"
                    "echo '{\"structured_output\": {\"verdict\": \"fail\", \"reason\": \"no\"}}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "claude", "model": "m2", "binary": str(fake), "base_url": "http://proxy.invalid",
                 "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()["make-file__good__r1"]
        self.assertEqual((res["judge"]["verdict"], res["judge"]["judge_model"]), ("fail", "m2"))
        self.assertFalse(res["passed"])

    def test_git_on_the_agents_repository_does_not_run_its_configured_commands(self):
        job = self.tmp / "job"
        repo = job / "work"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        marker = self.tmp / "escaped"
        subprocess.run(["git", "-C", str(repo), "config", "core.fsmonitor", f"sh -c 'touch {marker}; exit 1'"], check=True)
        (repo / "f").write_text("x\n")
        run = trial.Run(job, "ok", unconfined=not shutil.which("bwrap"))
        self.assertIn("f", run.git("status", "--porcelain"))
        self.assertEqual(run.git_rc("rev-parse", "--is-inside-work-tree"), 0)
        self.assertFalse(marker.exists())

    def test_git_diff_commands_survive_an_agent_configured_external_diff(self):
        """A "diff.external" the agent set in its own repo config used to be neutralized with an empty
        "-c diff.external=" override - which current git treats as an actual (empty) command to run,
        failing every diff-producing command with "external diff died" and leaving a check with an empty
        diff it never noticed was missing (run.git swallows the failure; run.git_rc exposes it to a check
        that asks). --no-ext-diff/--no-textconv on diff/log/show fixes this without giving the agent's own
        external diff driver a chance to run either."""
        job = self.tmp / "job"
        repo = job / "work"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "diff.external", "sh -c 'exit 1'"], check=True)
        (repo / "f").write_text("one\n")
        subprocess.run(["git", "-C", str(repo), "add", "f"], check=True)
        run = trial.Run(job, "ok", unconfined=not shutil.which("bwrap"))
        self.assertEqual(run.git_rc("diff", "--cached"), 0)
        self.assertIn("+one", run.git("diff", "--cached"))
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=a", "-c", "user.email=a@a.com",
                       "commit", "-q", "-m", "one"], check=True)
        (repo / "f").write_text("one\ntwo\n")
        self.assertIn("+two", run.git("diff"))
        self.assertEqual(run.git_rc("show", "-p", "HEAD"), 0)
        self.assertIn("+one", run.git("show", "-p", "HEAD"))
        self.assertEqual(run.git_rc("log", "-p", "-1"), 0)
        self.assertIn("+one", run.git("log", "-p", "-1"))
        # a genuinely broken git invocation is still visible through git_rc, not just an empty string
        self.assertNotEqual(run.git_rc("show", "-p", "not-a-real-ref"), 0)
        self.assertEqual(run.git("show", "-p", "not-a-real-ref"), "")

    def test_run_reads_do_not_follow_links_out_of_the_run(self):
        job = self.tmp / "job"
        (job / "work").mkdir(parents=True)
        secret = self.tmp / "secret.txt"
        secret.write_text("host secret\n")
        (job / "work" / "AGENTS.md").symlink_to(secret)
        (job / "final-0.md").symlink_to(secret)
        (job / "work" / "inside.txt").write_text("fine\n")
        (job / "work" / "link-inside").symlink_to(job / "work" / "inside.txt")
        run = trial.Run(job, "ok")
        self.assertEqual((run.file("AGENTS.md"), run.final_message), ("", ""))
        self.assertEqual(run.file("link-inside"), "fine\n")

    def test_copy_workdir_keeps_links_and_skips_special_files(self):
        job = self.tmp / "job"
        (job / "work").mkdir(parents=True)
        (job / "work" / "a.txt").write_text("a\n")
        (job / "work" / "link").symlink_to("/etc/hostname")
        os.mkfifo(job / "work" / "pipe")
        copy = trial.Run(job, "ok").copy_workdir()
        self.assertEqual(sorted(p.name for p in copy.iterdir()), ["a.txt", "link"])
        self.assertTrue((copy / "link").is_symlink())

    def test_only_the_provider_key_leaves_the_credential_file(self):
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\nOTHER_SECRET=nope\nexport EXPORTED_SECRET=nope\n")
        prefix = trial._key_prefix(env_file, "TRIAL_TEST_KEY", "ANTHROPIC_API_KEY")
        out = subprocess.run(prefix + ["sh", "-c", 'printf "%s|%s|%s" "$ANTHROPIC_API_KEY" "${OTHER_SECRET-unset}" "${EXPORTED_SECRET-unset}"'],
                             capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"}).stdout
        self.assertEqual(out, "not-a-real-key|unset|unset")
        with self.assertRaises(trial.TrialError):
            trial._key_prefix(env_file, "BAD; rm -rf /", None)

    def test_links_an_agent_plants_never_lead_the_runner_outside_the_run(self):
        victims = self.tmp / "victims"
        for d in ("home/skills", "harness/home/.cache/keep", "judge"):
            (victims / d).mkdir(parents=True)
        (victims / "home" / "models_cache.json").write_text("keep")
        (victims / "final.txt").write_text("original")
        (victims / "events.jsonl").write_text('{"type": "result", "result": "HOST-SECRET"}\n')
        (victims / "secret.txt").write_text("HOST-SECRET")
        (victims / "artifact.md").write_text("HOST-SECRET")
        state = lambda: sorted((str(p.relative_to(victims)), p.read_bytes() if p.is_file() else None) for p in victims.rglob("*"))
        before = state()
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    "case \"$*\" in *--json-schema*) echo '{\"structured_output\": {\"verdict\": \"pass\", \"reason\": \"ok\"}}'; exit 0;; esac\n"
                    "rm -f out.txt; mkfifo out.txt\n"  # a check reading it must not hang
                    "echo '{\"type\": \"result\", \"result\": \"agent done\"}'\n"
                    f"cd .. && rm -rf judge harness home final-0.md events.jsonl && ln -s {victims}/final.txt final-0.md && "
                    f"ln -s {victims}/judge judge && ln -s {victims}/harness harness && ln -s {victims}/home home && "
                    f"ln -s {victims}/events.jsonl events.jsonl && chmod 000 stderr.log && chmod 500 .\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        s = self.tmp / "scenarios" / "make-file"
        # this test also recheck --rejudge's, which needs the judge (not just the claude arm) to run
        # unconfined on a host without bubblewrap: only the literal "none" does that.
        write(s / "scenario.json", json.dumps({"prompt": "go", "followups": ["again"], "required": [],
                                               "sandbox": "confined" if shutil.which("bwrap") else "none",
                                               "judge": {"question": "q?", "pass_when": "it passes"}}))
        write(s / "check.py", "def check(run):\n    return {'final': run.final_message, 'out': run.file('out.txt')}\n")
        claude = {"executor": "claude", "model": "m", "binary": str(fake), "base_url": "http://proxy.invalid",
                  "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        r = self.run_cli("run", self._plan({"c": claude}, claude), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(stat.S_ISFIFO(os.lstat(self.out / "runs" / "make-file__c__r1" / "work" / "out.txt").st_mode))
        self.assertNotIn("HOST-SECRET", json.dumps(self.results()["make-file__c__r1"]))
        self.assertEqual(state(), before)
        self.assertEqual(self.run_cli("recheck", str(self.out), "--rejudge").returncode, 0)
        self.assertEqual(state(), before)
        # derive copies only a regular file inside the run's working directory
        cmd = {"executor": "command", "command": f"ln -s {victims}/secret.txt artifact.md"}
        swap = {"executor": "command", "command": f"cd .. && rm -rf work events.jsonl && mkdir events.jsonl && ln -s {victims} work"}
        r = self.run_cli("run", self._plan({"k": cmd, "w": swap}), "--out", str(self.tmp / "out2"))
        self.assertEqual(r.returncode, 0, r.stderr)  # a directory in a record's place ends nothing
        swapped = trial.Run(self.tmp / "out2" / "runs" / "make-file__w__r1", "ok")
        self.assertEqual(list(swapped.copy_workdir().iterdir()), [])
        r = self.run_cli("derive", str(self.tmp / "out2"), "--scenario", "make-file", "--artifact", "artifact.md",
                         "--consumer", str(s), "--plan", str(self.tmp / "derived.json"))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(state(), before)

    def test_what_an_agent_leaves_never_stops_the_runner(self):
        s = self.tmp / "scenarios" / "make-file"
        spec = json.loads((s / "scenario.json").read_text())
        write(s / "scenario.json", json.dumps(dict(spec, judge={"question": "q?", "pass_when": "it passes"})))
        flag = self.tmp / "break-judge-context"
        with open(s / "check.py", "a") as f:
            f.write(f"\ndef judge_context(run):\n    import os\n"
                    f"    if '__plain__' in run.dir.name and os.path.exists({str(flag)!r}):\n        raise KeyError('boom')\n"
                    f"    return 'evidence'\n")
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judges = {}
        for name in ("j1", "j2"):
            fake = self.tmp / "bin" / name  # plants a directory where the runner writes the verdict
            write(fake, "#!/bin/sh\ncat >/dev/null\nmkdir -p ../verdict.json/locked; chmod 000 ../verdict.json/locked\n"
                        "touch ../../judge-was-here 2>/dev/null; chmod 500 ../.. 2>/dev/null; chmod 500 ..\n"
                        "echo '{\"structured_output\": {\"verdict\": \"pass\", \"reason\": \"ok\"}}'\n", 0o755)
            judges[name] = {"executor": "claude", "model": name, "binary": str(fake), "base_url": "http://proxy.invalid",
                            "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        made = "echo hi > out.txt; faketool x"
        leave = (made + "; cd .. && mkdir result.json final-0.md && mkdir -p judge/locked judge.next/locked && "
                 "touch judge/locked/f judge.next/locked/f && chmod 000 judge/locked judge.next/locked && "
                 "mkdir home && touch home/models_cache.json && chmod 500 home && chmod 500 .")
        odd = ("echo '{\"type\": \"assistant\", \"message\": \"x\"}'; "
               "echo '{\"type\": \"assistant\", \"message\": {\"content\": [{\"type\": \"tool_use\", \"name\": \"Bash\", \"input\": 1}]}}'; "
               "echo '{\"type\": \"result\", \"usage\": 5}'; " + made)
        plan = self._plan({"leave": {"executor": "command", "command": leave}, "plain": {"executor": "command", "command": made},
                           "odd": {"executor": "command", "command": odd}}, judges["j1"])
        r = self.run_cli("run", plan, "--out", str(self.out), "--jobs", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.out / "summary.md").exists())
        expected = {"make-file__leave__r1": True, "make-file__plain__r1": True, "make-file__odd__r1": True}
        self.assertEqual({k: v["passed"] for k, v in self.results().items()}, expected)
        self.assertEqual(self.run_cli("recheck", str(self.out), "--judge", json.dumps(judges["j2"])).returncode, 0)
        before = {k: v["judge_identity"]["model"] for k, v in self.results().items()}
        self.assertEqual(set(before.values()), {"j2"})
        flag.write_text("")
        r = self.run_cli("recheck", str(self.out), "--rejudge")
        self.assertEqual(r.returncode, 2)
        self.assertIn("judge_context: KeyError: 'boom'", r.stderr)
        self.assertIn("nothing was changed", r.stderr)
        self.assertTrue((self.judge_cell("make-file__plain__r1") / "verdict.json").is_file())
        self.assertEqual({k: v["passed"] for k, v in self.results().items()}, expected)
        if shutil.which("bwrap"):  # confined, the judge reaches only its own opaque cell directory
            self.assertEqual(list(self.out.glob("runs/*/judge-was-here")), [])
            self.assertEqual(list((self.out / "judges" / ".cells").glob("*/judge-was-here")), [])
        else:  # unconfined, the escape is contained to this one run's own cell, never the shared .cells/
            self.assertEqual(list((self.out / "judges" / ".cells").glob("judge-was-here")), [])

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap")
    def test_processes_a_confined_run_starts_end_with_it(self):
        write(self.tmp / "plan.json", json.dumps({"name": "pid", "repeats": 1, "scenarios": ["scenarios/make-file"],
            "arms": {"a": {"executor": "command", "command": '(sleep 3; touch "$TRIAL_JOB_DIR/survivor") & exit 0'}}}))
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        subprocess.run(["sleep", "4"])
        self.assertFalse((self.out / "runs" / "make-file__a__r1" / "survivor").exists())

    def _models_file(self, *extra):
        f = self.tmp / "models.txt"
        f.write_text("\n".join(["claude-sonnet-4-20250514", "claude-sonnet-4-5-20250929", "claude-sonnet-4-6-thinking",
                                 "claude-sonnet-5", "claude-sonnet-5-5", "claude-opus-5-5", "gpt-5.5", "gpt-5.6-luna",
                                 "gpt-6-luna", "gpt-6.1-sol", *extra]) + "\n")
        return f

    def _plan(self, arms, judge=None, path=None):
        plan = {"name": "p", "repeats": 1, "sandbox": self.default_sandbox, "scenarios": ["scenarios/make-file"], "arms": arms}
        if judge:
            plan["judge"] = judge
        write(path or self.tmp / "plan.json", json.dumps(plan))
        return str(path or self.tmp / "plan.json")

    def test_plan_settings_expand_environment_references(self):
        self._plan({"a": {"executor": "command", "model": "${TRIAL_TEST_MODEL:-fallback-model}", "effort": "${TRIAL_TEST_EFFORT:-}",
                          "base_url": "http://proxy.invalid/", "env_file": "keys.env",
                          "command": 'echo "${TRIAL_SCENARIO_DIR}" > seen.txt'}})
        os.environ.pop("TRIAL_TEST_MODEL", None)
        os.environ["TRIAL_TEST_EFFORT"] = ""
        try:
            arm = trial.load_plan(self.tmp / "plan.json", None, None, None)["arms"]["a"]
            self.assertEqual((arm["model"], arm["model_spec"]), ("fallback-model", "${TRIAL_TEST_MODEL:-fallback-model}"))
            self.assertNotIn("effort", arm)  # empty means unset
            self.assertEqual(arm["base_url"], "http://proxy.invalid")
            self.assertEqual(arm["env_file"], str(self.tmp / "keys.env"))  # relative to the plan
            self.assertIn("${TRIAL_SCENARIO_DIR}", arm["command"])
            os.environ["TRIAL_TEST_MODEL"] = "from-env"
            self.assertEqual(trial.load_plan(self.tmp / "plan.json", None, None, None)["arms"]["a"]["model"], "from-env")
        finally:
            os.environ.pop("TRIAL_TEST_MODEL", None)
            del os.environ["TRIAL_TEST_EFFORT"]
        self._plan({"c": {"executor": "claude", "model": "m", "env_file": "missing.env"}})
        with self.assertRaisesRegex(trial.TrialError, "missing.env does not exist"):
            trial.load_plan(self.tmp / "plan.json", None, None, None)
        for model, error in [("${TRIAL_TEST_UNSET}", "TRIAL_TEST_UNSET}, which is unset or empty"),
                             ("${TRIAL_TEST_UNSET:-${TRIAL_TEST_B:-x}}", "without nesting"),
                             ("${TRIAL_TEST_UNSET", "without nesting"), (5, "model must be a string")]:
            self._plan({"a": {"executor": "command", "model": model, "command": "true"}})
            with self.assertRaisesRegex(trial.TrialError, error):
                trial.load_plan(self.tmp / "plan.json", None, None, None)

    def test_latest_model_picks_the_newest_numeric_version(self):
        ids = self._models_file().read_text().split()
        self.assertEqual(trial.latest_model("claude-sonnet-*", ids), "claude-sonnet-5-5")
        self.assertEqual(trial.latest_model("gpt-*-luna", ids), "gpt-6-luna")
        self.assertEqual(trial.latest_model("gpt-*", ids), "gpt-5.5")  # a wildcard is a version, never a family suffix
        self.assertEqual(trial.latest_model("claude-sonnet-4-*", ids), "claude-sonnet-4-5-20250929")
        self.assertEqual(trial.latest_model("gpt-*", ["gpt-5.2", "gpt-5-2025-08-07"]), "gpt-5.2")  # dates only break ties
        self.assertEqual(trial.latest_model("gpt-*", ["gpt-4.1", "gpt-4-0613"]), "gpt-4.1")
        self.assertEqual(trial.latest_model("m-*", ["m-9\n", "m-5"]), "m-5")
        self.assertEqual(trial.latest_model("m-*", ["m-\uff19\uff19", "m-5"]), "m-5")  # ASCII digits only
        self.assertEqual(trial.latest_model("m-*", ["m-" + "9" * 5000, "m-5"]), "m-5")  # a 5000-digit run is a date stamp
        with self.assertRaisesRegex(trial.TrialError, "models --match 'claude-haiku-\\*'"):
            trial.latest_model("claude-haiku-*", ids)
        with self.assertRaisesRegex(trial.TrialError, "only \\*"):
            trial.latest_model("gpt-?-luna", ids)
        self.assertEqual(trial.latest_model("m-*-*", ["m-" + "1-" * 200 + "1", "m-5-5"]), "m-5-5")  # overlong IDs skipped
        with self.assertRaisesRegex(trial.TrialError, "at most three"):
            trial.latest_model("m-*-*-*-*", ids)
        os.environ["TRIAL_MODELS_FILE"] = str(self._models_file())
        try:
            with self.assertRaises(trial.TrialError) as caught:
                trial.resolve_arm({"executor": "codex", "model": "latest:claude-zzz-*", "env_file": "/x/k.env",
                                   "api_key_var": "K"}, "arm 'a'")
            self.assertIn("--match 'claude-zzz-*' --env-file /x/k.env --api-key-var K`", str(caught.exception))
        finally:
            del os.environ["TRIAL_MODELS_FILE"]

    def test_a_run_directory_resolves_each_model_spec_once_and_never_mixes_settings(self):
        spec = {"executor": "command", "model": "latest:claude-sonnet-*", "effort": "high", "command": "true"}
        os.environ["TRIAL_MODELS_FILE"] = str(self._models_file())
        try:
            r = self.run_cli("run", self._plan({"a": spec}), "--out", str(self.out))
            self.assertEqual(r.returncode, 0, r.stderr)
            stored = json.loads((self.out / "plan.json").read_text())["arms"]["a"]
            self.assertEqual((stored["model"], stored["model_spec"], stored["model_query"]),
                             ("claude-sonnet-5-5", "latest:claude-sonnet-*", "latest:claude-sonnet-*"))
            self._models_file("claude-sonnet-6")  # a newer model ships: this directory keeps what it resolved
            r = self.run_cli("run", self._plan({"a": spec, "k[1]": spec}), "--out", str(self.out), "--repeats", "2")
            self.assertEqual(r.returncode, 0, r.stderr)
            res = self.results()
            self.assertEqual({v["identity"]["model"] for v in res.values()}, {"claude-sonnet-5-5"})
            self.assertEqual(len(res), 4)
            r = self.run_cli("run", self._plan({"a": spec}), "--out", str(self.tmp / "fresh"))
            self.assertEqual(json.loads((self.tmp / "fresh" / "plan.json").read_text())["arms"]["a"]["model"], "claude-sonnet-6")
            r = self.run_cli("run", self._plan({"a": dict(spec, permission_mode="plan", allowed_tools=[])}), "--out", str(self.out))
            self.assertEqual(r.returncode, 0, r.stderr)  # a command arm reads neither setting
            for arm, change, message in [("a", {"model": "claude-sonnet-5"}, "model claude-sonnet-5 (was claude-sonnet-5-5)"),
                                         ("a", {"effort": "medium"}, "effort medium (was high)"),
                                         ("k[1]", {"command": "echo x"}, "different command")]:
                for dry in ([], ["--dry-run"]):
                    r = self.run_cli("run", self._plan({arm: dict(spec, **change)}), "--out", str(self.out), *dry)
                    self.assertEqual(r.returncode, 2, (arm, change, dry, r.stdout))
                    self.assertIn(message, r.stderr)
                    self.assertIn("use a new --out", r.stderr)
            # A pinned rerun keeps the directory's resolution for an arm added later with the same spec.
            pinned = self.tmp / "pinned"
            self._models_file()
            for arms in ({"a": spec}, {"a": dict(spec, model="claude-sonnet-5-5")}):
                self.assertEqual(self.run_cli("run", self._plan(arms), "--out", str(pinned)).returncode, 0)
            self._models_file("claude-sonnet-6")
            self.assertEqual(self.run_cli("run", self._plan({"b": spec}), "--out", str(pinned)).returncode, 0)
            b = json.loads((pinned / "runs" / "make-file__b__r1" / "result.json").read_text())
            self.assertEqual(b["identity"]["model"], "claude-sonnet-5-5")
            r = self.run_cli("models", "--match", "gpt-*-sol", "--latest")
            self.assertEqual(r.stdout.strip(), "gpt-6.1-sol")
            r = self.run_cli("models", "--match", "claude-opus-*")
            self.assertEqual(r.stdout.split(), ["claude-opus-5-5"])
            os.environ["TRIAL_MODELS_FILE"] = str(self.tmp / "missing.txt")
            r = self.run_cli("models")
            self.assertEqual((r.returncode, r.stderr.startswith("error: cannot read TRIAL_MODELS_FILE")), (2, True), r.stderr)
        finally:
            del os.environ["TRIAL_MODELS_FILE"]
        # A dry run asks no endpoint: a spec the directory has not resolved shows unresolved.
        r = self.run_cli("run", self._plan({"c": {"executor": "claude", "model": "latest:claude-sonnet-*",
                                                  "base_url": "http://127.0.0.1:9"}}), "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("latest:claude-sonnet-* (resolved when the run starts)", r.stdout)
        r = self.run_cli("run", self._plan({"a": dict(spec, model="latest:claude-opus-*")}), "--out", str(self.out), "--dry-run")
        self.assertIn("holds these runs with claude-sonnet-5-5, so the run is refused unless", r.stdout)

    def test_executors_read_the_instructions_the_run_recorded(self):
        write(self.tmp / "arms" / "k.md", "version one\n")
        plan = self._plan({"k": {"executor": "command", "instructions": "arms/k.md", "command": 'cp "$TRIAL_INSTRUCTIONS" out.txt'}})
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'made_file': run.file('out.txt') == 'version one\\n', 'tool_called': True}\n")
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        stored = json.loads((self.out / "plan.json").read_text())["arms"]["k"]
        self.assertTrue(Path(stored["instructions"]).is_relative_to(self.out / "instructions"))
        self.assertTrue(self.results()["make-file__k__r1"]["passed"])
        write(self.tmp / "arms" / "k.md", "version two\n")
        r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("different instructions", r.stderr)

    def test_resources_are_copied_read_only_into_the_private_home(self):
        write(self.tmp / "resources" / "demo-skill" / "SKILL.md", "a demo skill\n")
        plan = self._plan({"k": {"executor": "command", "resources": {"skills/demo": "resources/demo-skill"},
                                 "command": 'cat "$HOME/skills/demo/SKILL.md" > out.txt; '
                                            'touch "$HOME/skills/demo/SKILL.md" 2>write-failed.txt || true'}})
        write(self.tmp / "scenarios" / "make-file" / "check.py", (
            "def check(run):\n"
            "    import stat, os\n"
            "    p = run.workdir.parent / 'harness' / 'home' / 'skills' / 'demo' / 'SKILL.md'\n"
            "    return {'made_file': run.file('out.txt') == 'a demo skill\\n',\n"
            "            'read_only': not (os.lstat(p).st_mode & stat.S_IWUSR),\n"
            "            'write_refused': 'write-failed' in run.file('write-failed.txt') or "
            "run.file('write-failed.txt') == '',\n"
            "            'tool_called': True}\n"))
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        checks = self.results()["make-file__k__r1"]["checks"]
        self.assertTrue(checks["made_file"], checks)
        self.assertTrue(checks["read_only"], checks)
        stored = json.loads((self.out / "plan.json").read_text())["arms"]["k"]
        self.assertIn("resources_sha256", stored)

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap: only it can actually block a chmod, "
                         "not just a cleared write bit an agent still owns the directory around")
    def test_confined_resources_survive_a_chmod_back_to_writable(self):
        # Clearing a copy's own write bit (see _copy_readonly) is advisory only: the agent still owns the
        # writable directory it sits in and can chmod its way back before overwriting it. Confined, the
        # resource's own path is re-bound read-only after the job directory itself, so bwrap - not merely a
        # permission bit the agent controls - is what actually stops the write.
        write(self.tmp / "resources" / "demo-skill" / "SKILL.md", "original\n")
        plan = self._plan({"k": {"executor": "command", "resources": {"skills/demo": "resources/demo-skill"},
                                 "confine": True,
                                 "command": 'chmod -R u+w "$HOME/skills" 2>/dev/null; '
                                            'echo tampered > "$HOME/skills/demo/SKILL.md" 2>write-failed.txt; '
                                            'cat "$HOME/skills/demo/SKILL.md" > seen.txt'}})
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip(), 'tool_called': True}\n")
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        checks = self.results()["make-file__k__r1"]["checks"]
        self.assertEqual(checks["seen"], "original")  # not "tampered": the write never landed

    def test_resources_digest_refuses_a_changed_rerun(self):
        write(self.tmp / "resources" / "demo-skill" / "SKILL.md", "version one\n")
        plan = self._plan({"k": {"executor": "command", "resources": {"skills/demo": "resources/demo-skill"},
                                 "command": "true"}})
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        write(self.tmp / "resources" / "demo-skill" / "SKILL.md", "version two\n")
        r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("different resources", r.stderr)
        self.assertIn("use a new --out", r.stderr)

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap to prove confinement, not just the arm setting")
    def test_readable_reaches_a_confined_claude_arm_too(self):
        # "readable" was always read by run_claude, but nothing exercised it end to end under real
        # confinement; this confirms a path it names is actually reachable by a confined claude arm, not
        # only by codex (which had its own coverage already).
        toolchain = self.tmp / "extra-toolchain"
        write(toolchain / "marker.txt", "reachable\n")
        fake = self.tmp / "bin" / "claude"
        write(fake, f"#!/bin/sh\ncat {toolchain}/marker.txt > seen.txt 2>/dev/null || echo MISSING > seen.txt\n"
                    "cat >/dev/null\necho '{\"type\": \"result\", \"result\": \"ok\"}'\n", 0o755)
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        claude = {"c": {"executor": "claude", "model": "m", "binary": str(fake), "readable": [str(toolchain)],
                        "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        self.assertEqual(self.run_cli("run", self._plan(claude), "--out", str(self.out)).returncode, 0)
        self.assertEqual(self.results()["make-file__c__r1"]["checks"]["seen"], "reachable")

    def test_the_judge_of_a_run_directory_changes_only_through_recheck(self):
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        good = {"good": {"executor": "command", "command": 'echo hi > out.txt; faketool x'}}
        self.assertEqual(self.run_cli("run", self._plan(good), "--out", str(self.out)).returncode, 0)
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\ncat >/dev/null\necho '{\"structured_output\": {\"verdict\": \"pass\", \"reason\": \"ok\"}}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "claude", "model": "m2", "binary": str(fake), "base_url": "http://proxy.invalid",
                 "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file), "instructions": "unused.md"}
        r = self.run_cli("run", self._plan(good, judge), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("scored without a judge", r.stderr)
        check = self.tmp / "scenarios" / "make-file" / "check.py"
        working = check.read_text()
        check.write_text("def check(run):\n    raise RuntimeError('broken')\n")
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge))
        self.assertEqual(r.returncode, 2)
        self.assertIn("fail to run", r.stderr)
        self.assertNotIn("judge", json.loads((self.out / "plan.json").read_text()))
        check.write_text(working)
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge), "--only", "other")
        self.assertEqual(r.returncode, 2)
        self.assertIn("drop --only", r.stderr)
        self.assertEqual(self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge)).returncode, 0)
        self.assertEqual(json.loads((self.out / "plan.json").read_text())["judge"]["model"], "m2")
        self.assertEqual(self.run_cli("run", self._plan(good, judge), "--out", str(self.out), "--repeats", "2").returncode, 0)
        self.assertEqual({v["judge_identity"]["model"] for v in self.results().values()}, {"m2"})
        for plan_judge, message in [(dict(judge, model="m3"), "model m3 (was m2)"), (None, "has no judge")]:
            r = self.run_cli("run", self._plan(good, plan_judge), "--out", str(self.out))
            self.assertEqual(r.returncode, 2)
            self.assertIn(message, r.stderr)
        # A verdict on a run whose checks now fail still belongs to its judge.
        check.write_text("def check(run):\n    raise RuntimeError('broken')\n")
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        check.write_text(working)
        r = self.run_cli("run", self._plan(good, dict(judge, model="m3")), "--out", str(self.out))
        self.assertIn("model m3 (was m2)", r.stderr)
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps({"executor": "cladue", "model": "m3"}))
        self.assertIn("valid judge executors: codex, claude", r.stderr)
        self.assertEqual(json.loads((self.out / "plan.json").read_text())["judge"]["model"], "m2")
        # A verdict from another judge does not score until it is re-judged.
        stale = self.out / "runs" / "make-file__good__r1" / "result.json"
        stale.write_text(json.dumps(dict(json.loads(stale.read_text()), judge_identity={"executor": "claude", "model": "m1"})))
        r = self.run_cli("recheck", str(self.out))
        self.assertIn("judge-stale", r.stdout)
        self.assertIsNone(json.loads(stale.read_text())["passed"])
        self.assertEqual(self.run_cli("recheck", str(self.out), "--rejudge").returncode, 0)
        self.assertTrue(json.loads(stale.read_text())["passed"])

    def test_a_judge_that_gives_no_verdict_changes_nothing(self):
        good = {"good": {"executor": "command", "command": 'echo hi > out.txt; faketool x'}}
        self.assertEqual(self.run_cli("run", self._plan(good), "--out", str(self.out)).returncode, 0)
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judges = {}
        for name, reply in [("works", '{"structured_output": {"verdict": "pass", "reason": "ok"}}'), ("broken", '{"structured_output": [1]}')]:
            fake = self.tmp / "bin" / name
            write(fake, f"#!/bin/sh\ncat >/dev/null\necho '{reply}'\n", 0o755)
            judges[name] = {"executor": "claude", "model": name, "binary": str(fake), "base_url": "http://proxy.invalid",
                            "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        self.assertEqual(self.run_cli("recheck", str(self.out), "--judge", json.dumps(judges["works"])).returncode, 0)
        stored = json.loads((self.out / "plan.json").read_text())
        self.assertIn("judge", stored["scenarios"][0])  # the spec it judged with
        r = self.run_cli("run", self._plan(good), "--out", str(self.out))
        self.assertIn("has no judge", r.stderr)
        verdict = self.judge_cell("make-file__good__r1") / "verdict.json"
        self.assertTrue(verdict.exists())
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judges["broken"]))
        self.assertEqual(r.returncode, 2)
        self.assertIn("nothing was changed", r.stderr)
        self.assertEqual(json.loads((self.out / "plan.json").read_text())["judge"]["model"], "works")
        self.assertTrue(verdict.exists() and self.results()["make-file__good__r1"]["passed"])
        # the failed attempt's not-yet-committed judge.next cell was cleaned up, not left behind
        self.assertFalse(trial._judge_cell_dir(self.out, "make-file__good__r1", "judge.next").exists())
        r = self.run_cli("run", self._plan(good, judges["broken"]), "--out", str(self.tmp / "fresh"))
        self.assertIn("invalid 1: judge-error", r.stdout)  # invalid, never a failure of the arm
        self.assertIsNone(json.loads((self.tmp / "fresh" / "runs" / "make-file__good__r1" / "result.json").read_text())["passed"])
        for bad, error in [('"claude"', "must be a JSON object"), ("null", "must be a JSON object"), ("{", "not valid JSON")]:
            r = self.run_cli("recheck", str(self.out), "--judge", bad)
            self.assertEqual(r.returncode, 2, bad)
            self.assertIn(error, r.stderr)

    def test_one_run_or_recheck_uses_a_run_directory_at_a_time(self):
        self.out.mkdir()
        with trial._lock(self.out):
            r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("in use by another trial.py run", r.stderr)

    def test_model_listing_keeps_the_key_from_redirects_and_reads_every_page(self):
        import http.server
        import threading
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                port = self.server.server_address[1]
                seen.append((port, self.path, self.headers.get("x-api-key")))
                if self.path.startswith("/r/"):
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{target.server_address[1]}{self.path[2:]}")
                    self.end_headers()
                    return
                second = "after_id=" in self.path
                body = {"data": [{"id": "claude-sonnet-5-5" if second else "claude-sonnet-5"}],
                        "has_more": not second, "last_id": "claude-sonnet-5"}
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        target = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        relay = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        for server in (target, relay):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            env_file = self.tmp / "keys.env"
            env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
            r = self.run_cli("models", "--base-url", f"http://127.0.0.1:{relay.server_address[1]}/r",
                             "--env-file", str(env_file), "--api-key-var", "TRIAL_TEST_KEY")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split(), ["claude-sonnet-5", "claude-sonnet-5-5"])
            self.assertEqual({k for port, _, k in seen if port == relay.server_address[1]}, {"not-a-real-key"})
            self.assertEqual({k for port, _, k in seen if port == target.server_address[1]}, {None})
            port = relay.server_address[1]
            crlf = self.tmp / "crlf.env"
            crlf.write_bytes("CRLF_KEY=secret-crlf\r\nQUOTE_KEY=secret\u201dquote\n".encode())
            for args, error in [(["--base-url", f"http://u:secret@127.0.0.1:{port}"], "carries credentials"),
                                (["--base-url", f"http://127.0.0.1:{port}", "--env-file", str(self.tmp / "missing.env")], "does not exist"),
                                (["--base-url", f"http://127.0.0.1:{port}", "--env-file", str(env_file), "--api-key-var", "TRIAL_UNSET"],
                                 "TRIAL_UNSET is unset or empty in"),
                                (["--base-url", f"http://127.0.0.1:{port}/a#secret"], "a fragment"),
                                (["--base-url", f"http://127.0.0.1:{port}", "--env-file", str(crlf), "--api-key-var", "CRLF_KEY"],
                                 "holds a line break"),
                                (["--base-url", f"http://127.0.0.1:{port}", "--env-file", str(crlf), "--api-key-var", "QUOTE_KEY"],
                                 "non-ASCII character")]:
                r = self.run_cli("models", *args)
                self.assertEqual(r.returncode, 2, args)
                self.assertIn(error, r.stderr)
                self.assertNotIn("secret", r.stderr)
        finally:
            for server in (target, relay):
                server.shutdown()
                server.server_close()

    def test_wilson_interval_bounds(self):
        lo, hi = trial.wilson(5, 5)
        self.assertAlmostEqual(lo, 0.566, places=2)
        self.assertEqual(hi, 1.0)
        self.assertEqual(trial.wilson(0, 0), (0.0, 1.0))

    def test_environment_is_an_explicit_allowlist(self):
        os.environ["TRIAL_TEST_SECRET"] = "leak-me-not"
        os.environ["TRIAL_TEST_PASS"] = "should-pass-through"
        os.environ["LC_ALL"] = "C"
        try:
            write(self.tmp / "scenarios" / "make-file" / "check.py", (
                "def check(run):\n"
                "    env = dict(l.split('=', 1) for l in run.file('env.txt').splitlines() if '=' in l)\n"
                "    return {'no_secret': 'TRIAL_TEST_SECRET' not in env,\n"
                "            'pass_env_arrives': env.get('TRIAL_TEST_PASS') == 'should-pass-through',\n"
                "            'lc_all_arrives': env.get('LC_ALL') == 'C',\n"
                "            'tmpdir_private': env.get('TMPDIR', '').endswith('/harness/tmp')}\n"))
            write(self.tmp / "plan.json", json.dumps({"name": "env", "repeats": 1, "sandbox": self.default_sandbox,
                "arms": {"a": {"executor": "command", "command": "env > env.txt", "pass_env": ["TRIAL_TEST_PASS"]}},
                "scenarios": ["scenarios/make-file"]}))
            self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
            checks = self.results()["make-file__a__r1"]["checks"]
            self.assertTrue(all(checks.values()), checks)
        finally:
            del os.environ["TRIAL_TEST_SECRET"]
            del os.environ["TRIAL_TEST_PASS"]
            del os.environ["LC_ALL"]

    def test_key_sourcing_without_a_default_file(self):
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\ncat >/dev/null\nprintf '%s' \"$ANTHROPIC_API_KEY\" > seen.txt\n"
                    "echo '{\"type\": \"result\", \"result\": \"ok\"}'\n", 0o755)
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()),
                                     sandbox="confined" if shutil.which("bwrap") else "none")))
        claude = {"executor": "claude", "model": "m", "binary": str(fake)}

        def seen(out_dir):
            return json.loads((out_dir / "runs" / "make-file__c__r1" / "result.json").read_text())["checks"]["seen"]

        saved = {k: os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "TRIAL_ENV_FILE")}
        try:
            os.environ.pop("TRIAL_ENV_FILE", None)
            # (a) neither env_file nor TRIAL_ENV_FILE: the key comes straight from this process's environment.
            os.environ["ANTHROPIC_API_KEY"] = "from-parent-env"
            out_a = self.tmp / "out-a"
            self.assertEqual(self.run_cli("run", self._plan({"c": claude}), "--out", str(out_a)).returncode, 0)
            self.assertEqual(seen(out_a), "from-parent-env")
            del os.environ["ANTHROPIC_API_KEY"]

            # (b) TRIAL_ENV_FILE names a file when the arm names none.
            env_file = self.tmp / "trial-env-file.env"
            env_file.write_text("ANTHROPIC_API_KEY=from-trial-env-file\n")
            os.environ["TRIAL_ENV_FILE"] = str(env_file)
            out_b = self.tmp / "out-b"
            self.assertEqual(self.run_cli("run", self._plan({"c": claude}), "--out", str(out_b)).returncode, 0)
            self.assertEqual(seen(out_b), "from-trial-env-file")

            # (c) the arm's own env_file wins over TRIAL_ENV_FILE.
            arm_env_file = self.tmp / "arm.env"
            arm_env_file.write_text("ANTHROPIC_API_KEY=from-arm-env-file\n")
            out_c = self.tmp / "out-c"
            self.assertEqual(self.run_cli("run", self._plan({"c": dict(claude, env_file=str(arm_env_file))}),
                                          "--out", str(out_c)).returncode, 0)
            self.assertEqual(seen(out_c), "from-arm-env-file")

            # (d) none of the three: a clear error naming all three ways to supply it.
            del os.environ["TRIAL_ENV_FILE"]
            clean_env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "TRIAL_ENV_FILE")}
            r = subprocess.run([sys.executable, str(SCRIPT), "run", self._plan({"c": claude}), "--out", str(self.tmp / "out-d")],
                               capture_output=True, text=True, env=clean_env, timeout=300)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("env_file", r.stderr)
            self.assertIn("TRIAL_ENV_FILE", r.stderr)
            self.assertIn("environment", r.stderr)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_binary_discovery_handles_shallow_paths_and_symlinks(self):
        # A shallow path (no nested install layout) must resolve without the IndexError the old
        # parents[3]-based _codex_readable raised.
        shallow = self.tmp / "usr" / "bin" / "codex"
        write(shallow, "#!/bin/sh\necho hi\n", 0o755)
        self.assertEqual(trial._resolve_binary("codex", {"binary": str(shallow)}, "TRIAL_CODEX_BIN_UNUSED"), str(shallow))
        readable = trial._executor_readable(str(shallow))
        self.assertIn(shallow.parent, readable)

        # A symlinked launcher (npm/pnpm/volta-style shim) resolves to its real target's own directory too,
        # and a shebang naming an interpreter (the node runtime a JS launcher needs) adds that directory.
        real_bin = self.tmp / "lib" / "node_modules" / "codex" / "bin" / "codex"
        write(real_bin, "#!/usr/bin/env node\n", 0o755)
        shim_dir = self.tmp / "shim" / "bin"
        shim_dir.mkdir(parents=True)
        shim = shim_dir / "codex"
        shim.symlink_to(real_bin)
        readable = trial._executor_readable(str(shim))
        self.assertIn(shim.parent, readable)
        self.assertIn(real_bin.parent, readable)
        node_dir = self.tmp / "custom-node" / "bin"
        node_dir.mkdir(parents=True)
        write(node_dir / "node", "#!/bin/sh\n", 0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{node_dir}{os.pathsep}{old_path}"
        try:
            self.assertIn(node_dir, trial._executor_readable(str(real_bin)))
        finally:
            os.environ["PATH"] = old_path

        # arm "binary" wins, then the TRIAL_*_BIN environment variable, then PATH; missing everywhere is an error.
        os.environ["TRIAL_CODEX_BIN_TEST"] = str(shallow)
        try:
            self.assertEqual(trial._resolve_binary("codex", {}, "TRIAL_CODEX_BIN_TEST"), str(shallow))
        finally:
            del os.environ["TRIAL_CODEX_BIN_TEST"]
        with self.assertRaisesRegex(trial.TrialError, "cannot find nonexistent-binary-xyz on PATH"):
            trial._resolve_binary("nonexistent-binary-xyz", {}, "TRIAL_NONEXISTENT_BIN_VAR_XYZ")

    def test_resolve_binary_expands_bare_names_and_tilde_like_a_shell(self):
        # A bare name in "binary" or TRIAL_*_BIN used to be returned verbatim, treated as a path relative
        # to the current directory, and fail inside bwrap with an opaque "Can't mkdir parents".
        real = self.tmp / "usr" / "bin" / "codex"
        write(real, "#!/bin/sh\necho hi\n", 0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{real.parent}{os.pathsep}{old_path}"
        try:
            self.assertEqual(trial._resolve_binary("codex", {"binary": "codex"}, "TRIAL_CODEX_BIN_UNUSED"), str(real))
            # a "~" binary is expanded the same way a shell would, not treated as a literal path segment
            home_bin = Path.home() / (".trial-test-tilde-" + os.urandom(4).hex())
            write(home_bin, "#!/bin/sh\necho hi\n", 0o755)
            try:
                rel = "~/" + home_bin.name
                self.assertEqual(trial._resolve_binary("codex", {"binary": rel}, "TRIAL_CODEX_BIN_UNUSED"), str(home_bin))
            finally:
                home_bin.unlink()
        finally:
            os.environ["PATH"] = old_path
        with self.assertRaisesRegex(trial.TrialError, "not a path that exists and no such name is on PATH"):
            trial._resolve_binary("codex", {"binary": "nonexistent-binary-xyz"}, "TRIAL_CODEX_BIN_UNUSED")

    def test_executor_readable_never_exposes_root_or_an_ancestor_of_home(self):
        # A binary directly under "/" must never end up in the readable set: binding "/" back read-only
        # would undo the tmpfs bwrap puts over the user's home, re-exposing it whole.
        with mock.patch("trial.Path.home", return_value=Path("/nonexistent-fake-home-for-test")):
            readable = trial._executor_readable("/nonexistent-binary-for-test")
        self.assertNotIn(Path("/"), readable)
        # An ancestor of home (not just an immediate child, which too_broad already covered) must be
        # excluded too, for the same reason: it would remount over the tmpfs bwrap puts at home itself.
        fake_home = self.tmp / "fake" / "nested" / "home"
        write(fake_home.parent / "bin" / "codex", "#!/bin/sh\necho hi\n", 0o755)
        with mock.patch("trial.Path.home", return_value=fake_home):
            readable = trial._executor_readable(str(fake_home.parent / "bin" / "codex"))
        self.assertNotIn(fake_home.parent, readable)
        self.assertNotIn(fake_home.parent.parent, readable)

    def test_sandbox_refuses_without_bubblewrap_unless_none_is_explicit(self):
        write(self.tmp / "plan.json", json.dumps({"name": "sb", "repeats": 1,
            "arms": {"a": {"executor": "command", "command": 'echo hi > out.txt; faketool x'}},
            "scenarios": ["scenarios/make-file"]}))
        real_which = shutil.which

        def fake_which(name, *a, **k):
            return None if name == "bwrap" else real_which(name, *a, **k)

        out = self.tmp / "sbout"
        with mock.patch("trial.shutil.which", side_effect=fake_which):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                code = trial.main(["run", str(self.tmp / "plan.json"), "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertIn("bubblewrap", buf.getvalue())
            # a partial attempt is left behind, never a silent unconfined run
            self.assertFalse(list((out / "runs").glob("*/result.json")))
            # explicit --sandbox none is honored even with bubblewrap still unavailable
            code2 = trial.main(["run", str(self.tmp / "plan.json"), "--out", str(out), "--sandbox", "none"])
        self.assertEqual(code2, 0)
        result = json.loads(next((out / "runs").glob("*/result.json")).read_text())
        self.assertTrue(result["passed"])
        self.assertIn("**Unconfined**", (out / "summary.md").read_text())
        # also exercised directly: run_command and confine_prefix never fall back silently
        with mock.patch("trial.shutil.which", side_effect=fake_which):
            with self.assertRaisesRegex(trial.TrialError, "bubblewrap"):
                trial.confine_prefix(self.tmp, [])
            job = self.tmp / "direct-job"
            (job / "work").mkdir(parents=True)
            (job / "harness").mkdir()
            spec = {"dir": str(self.tmp / "scenarios" / "make-file"), "prompt": "x"}
            with self.assertRaisesRegex(trial.TrialError, "bubblewrap"):
                trial.run_command({"command": "true"}, spec, job, {"PATH": "/usr/bin:/bin"})

    def test_typo_or_unrelated_sandbox_value_never_runs_claude_or_command_unconfined(self):
        """A typo ("confinde") or a Codex-native sandbox mode name (meaningless to claude/command, which
        have no sandbox vocabulary of their own) must fail safe to confined - never silently drop this
        runtime's own bubblewrap the way any value other than the literal "confined" used to for these two
        executors (see _unconfined; only the literal "none" is the documented opt-out)."""
        write(self.tmp / "scenarios" / "make-file" / "scenario.json",
              json.dumps({"prompt": "create out.txt", "required": [], "sandbox": "confinde"}))
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\necho SHOULD-NOT-RUN > escaped.txt\n"
                    "echo '{\"type\": \"result\", \"result\": \"ok\"}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        claude = {"c": {"executor": "claude", "model": "m", "binary": str(fake),
                        "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        command = {"k": {"executor": "command", "command": "echo SHOULD-NOT-RUN > escaped.txt"}}
        real_which = shutil.which

        def fake_which(name, *a, **k):
            return None if name == "bwrap" else real_which(name, *a, **k)

        with mock.patch("trial.shutil.which", side_effect=fake_which):
            for arms, out_name in [(claude, "typo-claude"), (command, "typo-command")]:
                out = self.tmp / out_name
                code = trial.main(["run", self._plan(arms), "--out", str(out)])
                self.assertEqual(code, 2, out_name)
                self.assertFalse(list(out.glob("runs/*/work/escaped.txt")), out_name)

    def test_unconfined_mode_includes_the_parent_path(self):
        extra = self.tmp / "custom-extra-bin"
        extra.mkdir()
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              f"def check(run):\n    return {{'has_extra': {str(extra)!r} in run.file('path.txt')}}\n")
        write(self.tmp / "plan.json", json.dumps({"name": "p", "repeats": 1, "sandbox": "none",
            "arms": {"a": {"executor": "command", "command": "printf '%s' \"$PATH\" > path.txt"}},
            "scenarios": ["scenarios/make-file"]}))
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{extra}{os.pathsep}{old_path}"
        try:
            self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        finally:
            os.environ["PATH"] = old_path
        self.assertTrue(self.results()["make-file__a__r1"]["checks"]["has_extra"])

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap to start out confined")
    def test_recheck_sandbox_none_updates_the_unconfined_notice(self):
        # recheck --sandbox none used to leave every stored result saying "confined" and the summary
        # showing no notice at all, even though checks and the judge now ran unconfined.
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        self.assertNotIn("**Unconfined**", self.run_cli("summarize", str(self.out)).stdout)
        for v in self.results().values():
            self.assertEqual(v["sandbox"], "confined")
        r = self.run_cli("recheck", str(self.out), "--sandbox", "none")
        self.assertEqual(r.returncode, 0, r.stderr)
        for v in self.results().values():
            self.assertEqual(v["sandbox"], "none")
        self.assertIn("**Unconfined**", self.run_cli("summarize", str(self.out)).stdout)

    def test_copy_auth_is_an_explicit_opt_in(self):
        fake_auth = self.tmp / "fake-auth.json"
        fake_auth.write_text('{"fake": true}')
        saved = dict(trial._AUTH_FILE)
        trial._AUTH_FILE["codex"] = (fake_auth, Path("auth.json"))
        try:
            dest_home = self.tmp / "dest-home"
            dest_home.mkdir()
            # not set: nothing is copied
            trial._copy_auth("codex", {}, dest_home, "arm using codex")
            self.assertFalse((dest_home / "auth.json").exists())
            # the explicit opt-in copies it
            trial._copy_auth("codex", {"copy_auth": True}, dest_home, "arm using codex")
            self.assertEqual((dest_home / "auth.json").read_text(), '{"fake": true}')
            # a missing source with the opt-in set is a clear error, not a silent no-op
            fake_auth.unlink()
            with self.assertRaisesRegex(trial.TrialError, 'copy_auth.*true.*does not exist'):
                trial._copy_auth("codex", {"copy_auth": True}, self.tmp / "dest-home-2", "arm using codex")
        finally:
            trial._AUTH_FILE.clear()
            trial._AUTH_FILE.update(saved)

    def test_copy_auth_reaches_a_claude_arms_actual_run(self):
        fake_creds = self.tmp / "fake-claude-creds.json"
        fake_creds.write_text('{"fake": "claude-creds"}')
        saved = dict(trial._AUTH_FILE)
        trial._AUTH_FILE["claude"] = (fake_creds, Path(".claude") / ".credentials.json")
        try:
            write(self.tmp / "scenarios" / "make-file" / "check.py",
                  "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
            fake = self.tmp / "bin" / "claude"
            write(fake, "#!/bin/sh\ncat \"$HOME/.claude/.credentials.json\" > seen.txt 2>/dev/null || "
                        "echo MISSING > seen.txt\ncat >/dev/null\necho '{\"type\": \"result\", \"result\": \"ok\"}'\n", 0o755)
            env_file = self.tmp / "keys.env"
            env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
            claude = {"c": {"executor": "claude", "model": "m", "binary": str(fake), "copy_auth": True,
                            "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
            # in-process (trial.main), not the subprocess self.run_cli uses: a subprocess re-imports trial.py
            # and would read the real host's own credentials instead of this test's monkeypatched _AUTH_FILE.
            self.assertEqual(trial.main(["run", self._plan(claude), "--out", str(self.out)]), 0)
            self.assertEqual(self.results()["make-file__c__r1"]["checks"]["seen"], '{"fake": "claude-creds"}')
        finally:
            trial._AUTH_FILE.clear()
            trial._AUTH_FILE.update(saved)

    def test_preflight_checks_a_path_discovered_binary_before_scheduling_jobs(self):
        """A codex/claude binary found only via a bare PATH lookup (no explicit "binary", no TRIAL_*_BIN) is
        checked with --version, confined, before any job directory is created - catching a broken PATH shim
        once, cleanly, rather than after plan.json is written and every job's setup.sh has already run. An
        arm that names its own "binary" is trusted as given and never preflighted."""
        if not shutil.which("bwrap"):
            self.skipTest("needs bubblewrap")
        pathbin = self.tmp / "pathbin"
        write(pathbin / "claude", "#!/bin/sh\nexit 7\n", 0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{pathbin}{os.pathsep}{old_path}"
        saved_bin = os.environ.pop("TRIAL_CLAUDE_BIN", None)
        try:
            plan = self._plan({"c": {"executor": "claude", "model": "m"}})  # no "binary": found on PATH
            out = self.tmp / "preflight-out"
            code = trial.main(["run", plan, "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertFalse(list(out.glob("runs/*")))  # nothing was scheduled at all
        finally:
            os.environ["PATH"] = old_path
            if saved_bin is not None:
                os.environ["TRIAL_CLAUDE_BIN"] = saved_bin
        # an explicit "binary" is never preflighted: the same broken script now runs as the real job, and
        # its failure surfaces the ordinary way (an invalid run), not as an upfront refusal.
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        plan2 = self._plan({"c": {"executor": "claude", "model": "m", "binary": str(pathbin / "claude"),
                                  "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}})
        out2 = self.tmp / "preflight-out2"
        code2 = trial.main(["run", plan2, "--out", str(out2)])
        self.assertEqual(code2, 0)
        res = json.loads(next((out2 / "runs").glob("*/result.json")).read_text())
        self.assertEqual(res["status"], "exit-7")

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap")
    def test_preflight_failure_hint_names_version_manager_shims(self):
        # A version-manager shim (volta, mise, asdf) commonly re-execs the real CLI by re-reading $HOME,
        # which confinement replaces with a throwaway one - the preflight failure this causes used to name
        # only "binary", TRIAL_*_BIN, and "readable" without saying what a shim-specific fix looks like.
        pathbin = self.tmp / "pathbin"
        write(pathbin / "claude", "#!/bin/sh\necho 'real claude CLI not found in PATH' >&2\nexit 2\n", 0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{pathbin}{os.pathsep}{old_path}"
        saved_bin = os.environ.pop("TRIAL_CLAUDE_BIN", None)
        try:
            plan = self._plan({"c": {"executor": "claude", "model": "m"}})
            r = self.run_cli("run", plan, "--out", str(self.tmp / "shim-out"))
        finally:
            os.environ["PATH"] = old_path
            if saved_bin is not None:
                os.environ["TRIAL_CLAUDE_BIN"] = saved_bin
        self.assertEqual(r.returncode, 2)
        self.assertIn("volta which claude", r.stderr)
        self.assertIn("mise which claude", r.stderr)
        self.assertIn("asdf which claude", r.stderr)

    def test_extend_path_keeps_the_scenarios_own_tools_first(self):
        # A confined executor's own directories and interpreter used to be prepended ahead of everything,
        # including the scenario's own fake-tools directory (always isolated_env's first PATH entry) -
        # contradicting "fake tools first on PATH": a version-manager or ~/.local/bin directory could then
        # shadow a scenario's fake gh/curl/make.
        tools = self.tmp / "tools"
        extra = self.tmp / "extra-bin"
        tools.mkdir()
        extra.mkdir()
        base = os.pathsep.join([str(tools), "/usr/bin", "/bin"])
        extended = trial._extend_path(base, [extra])
        self.assertEqual(extended.split(os.pathsep), [str(tools), str(extra), "/usr/bin", "/bin"])
        # a directory already on PATH is not duplicated, and nothing to add leaves PATH untouched
        self.assertEqual(trial._extend_path(base, [extra]).split(os.pathsep).count(str(extra)), 1)
        self.assertEqual(trial._extend_path(base, []), base)

    def test_judge_question_under_a_judgeless_plan_is_invalid_not_a_silent_pass(self):
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--arms", "good", "--repeats", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.results()["make-file__good__r1"]
        self.assertIsNone(v["passed"])
        self.assertTrue(v["judge_missing"])
        self.assertIn("judge-missing", r.stdout)
        # judge_required: false keeps the lenient behavior: required checks alone decide.
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge_required=False)))
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        rescored = self.results()["make-file__good__r1"]
        self.assertTrue(rescored["passed"])
        self.assertNotIn("judge_missing", rescored)

    def test_command_stdout_becomes_final_message_when_no_final_md(self):
        job = self.tmp / "job"
        (job / "work").mkdir(parents=True)
        (job / "events.jsonl").write_text("plain stdout, not json and no final-*.md\nsecond line\n")
        run = trial.Run(job, "ok")
        self.assertIn("plain stdout, not json and no final-*.md", run.final_message)
        job2 = self.tmp / "job2"
        (job2 / "work").mkdir(parents=True)
        (job2 / "events.jsonl").write_text("x" * 20000)
        self.assertLessEqual(len(trial.Run(job2, "ok").final_message), trial.COMMAND_TAIL)

    def test_missing_scenario_artifact_is_an_explicit_marker_not_a_silent_transcript_fallback(self):
        # Before this fix, a missing scenario "artifact" quietly fell back to the executor's own transcript,
        # so the judge scored what the agent *said* it produced rather than what it actually produced -
        # exactly the failure the artifact feature exists to catch.
        job = self.tmp / "job"
        (job / "work").mkdir(parents=True)
        (job / "events.jsonl").write_text('{"type": "result", "result": "I wrote the report!"}\n')
        run = trial.Run(job, "ok", artifact="report.md")
        self.assertTrue(run.artifact_missing)
        self.assertIn("report.md", run.final_message)
        self.assertNotIn("I wrote the report", run.final_message)
        # once the artifact is actually there, it wins, and artifact_missing is false
        (job / "work" / "report.md").write_text("the actual report\n")
        run2 = trial.Run(job, "ok", artifact="report.md")
        self.assertFalse(run2.artifact_missing)
        self.assertEqual(run2.final_message, "the actual report\n")

    def test_missing_artifact_is_recorded_on_the_result(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json",
              json.dumps({"prompt": "write report.md", "required": [], "artifact": "report.md"}))
        r = self.run_cli("run", self._plan({"a": {"executor": "command", "command": "true"}}), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.results()["make-file__a__r1"]["artifact_missing"])

    def test_command_arm_stdout_reaches_the_judge(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json",
              json.dumps({"prompt": "echo something", "judge": {"question": "did it print DISTINCTIVE-MARKER-OUTPUT?",
                                                                 "pass_when": "it did"}}))
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\ncat >/dev/null\necho '{\"structured_output\": {\"verdict\": \"pass\", \"reason\": \"ok\"}}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "claude", "model": "m", "binary": str(fake), "base_url": "http://proxy.invalid",
                 "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        plan = self._plan({"c": {"executor": "command", "command": "echo DISTINCTIVE-MARKER-OUTPUT"}}, judge)
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        cell_dir = self.judge_cell("make-file__c__r1")
        prompt = (cell_dir / "prompt.md").read_text()
        self.assertIn("DISTINCTIVE-MARKER-OUTPUT", prompt)
        self.assertIn("one run of the task below", prompt)  # the neutral role, not "an AI agent"
        # the judge's own working directory reveals neither the arm nor the scenario (some agent CLIs put
        # their own cwd in the model's context, which would otherwise tell it what it is judging)
        self.assertNotIn("make-file", str(cell_dir))
        self.assertNotIn("__c__", str(cell_dir))
        self.assertTrue(cell_dir.is_relative_to(self.out / "judges" / ".cells"))

    def test_usage_aggregation_uses_the_last_running_total_and_sums_per_call_fields(self):
        # Codex's own "turn.completed" usage is a running total across the whole thread (confirmed on real
        # session records: it only ever increases across `codex exec resume`) - summing every such event,
        # one per follow-up, used to multiply a multi-turn run's real spend several times over. Only the
        # LAST one counts.
        codex_events = [
            {"type": "turn.completed", "usage": {"input_tokens": 100, "output": {"tokens": 10}, "cached": True}},
            {"type": "turn.completed", "usage": {"input_tokens": 130, "output": {"tokens": 15}}},
        ]
        usage = trial._usage(codex_events)
        self.assertEqual(usage["input_tokens"], 130)
        self.assertEqual(usage["output.tokens"], 15)
        self.assertNotIn("cached", usage)  # a boolean leaf is never summed as a number

        # Claude's own per-call "usage" on a "result" event is NOT a running total (each follow-up reports
        # only that turn's own tokens, confirmed the same way), so these ARE summed; "total_cost_usd" on
        # the same event type IS already a running total across `--continue` on real records, so only the
        # last one counts, never summed.
        claude_events = [
            {"type": "result", "usage": {"input_tokens": 16, "output": {"tokens": 5}}, "total_cost_usd": 0.02},
            {"type": "result", "usage": {"input_tokens": 8, "output": {"tokens": 3}}, "total_cost_usd": 0.05},
        ]
        usage2 = trial._usage(claude_events)
        self.assertEqual(usage2["input_tokens"], 24)
        self.assertEqual(usage2["output.tokens"], 8)
        self.assertAlmostEqual(usage2["total_cost_usd"], 0.05)

        # A value the runner never produced itself (the run directory is writable inside the sandbox, so an
        # agent's own process can append to events.jsonl) is dropped rather than corrupting the total.
        tampered = [{"type": "result", "usage": {"output_tokens": -6000, "input_tokens": float("nan")},
                    "total_cost_usd": float("inf")}]
        usage3 = trial._usage(tampered)
        self.assertNotIn("output_tokens", usage3)
        self.assertNotIn("input_tokens", usage3)
        self.assertNotIn("total_cost_usd", usage3)

    def test_summarize_baseline_percentages(self):
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        for job_name, output_tokens, seconds in [("make-file__good__r1", 100, 10), ("make-file__good__r2", 100, 10),
                                                 ("make-file__bad__r1", 150, 15), ("make-file__bad__r2", 150, 15)]:
            p = self.out / "runs" / job_name / "result.json"
            r = json.loads(p.read_text())
            r["usage"], r["seconds"] = {"output_tokens": output_tokens}, seconds
            p.write_text(json.dumps(r))
        md = self.run_cli("summarize", str(self.out), "--baseline", "good").stdout
        self.assertIn("+50% med / +50% avg, n=1", md)
        payload = json.loads(self.run_cli("summarize", str(self.out), "--json", "--baseline", "good").stdout)
        # a single scenario contributes one percentage, so its median and mean both equal it
        self.assertEqual(payload["pct_vs_baseline"]["bad"]["output_tokens"],
                         {"median": 0.5, "mean": 0.5, "n_scenarios": 1})
        self.assertEqual(payload["pct_vs_baseline"]["bad"]["seconds_mean"],
                         {"median": 0.5, "mean": 0.5, "n_scenarios": 1})
        self.assertNotIn("good", payload["pct_vs_baseline"])  # the baseline arm is never compared to itself
        self.assertEqual(payload["arms"]["good"]["usage_mean"]["output_tokens"], 100)
        self.assertIsInstance(payload["arms"]["bad"]["commands_mean"], float)
        self.assertEqual(payload["arms"]["good"]["no_usage"], 0)  # every run here reported usage

    def test_baseline_percentages_are_per_scenario_and_include_invalid_runs(self):
        """The bug this replaces: pooling every run across every scenario, valid only, could flip the sign
        of the whole comparison when one scenario's expensive runs happened to be excluded as invalid. Two
        scenarios where B is cheaper on every valid run, but one scenario's B runs are all excluded as
        invalid because they are more expensive still: pooling would make B look far cheaper than A, when
        it actually cost more. Computing the percentage per scenario first (each scenario contributing one
        number, on ALL its runs, valid or not) does not let that happen."""
        s2 = self.tmp / "scenarios" / "make-file-2"
        write(s2 / "scenario.json", json.dumps({"prompt": "x", "required": []}))
        write(self.tmp / "plan.json", json.dumps({
            "name": "cost", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"a": {"executor": "command", "command": "true"}, "b": {"executor": "command", "command": "true"}},
            "scenarios": ["scenarios/make-file", "scenarios/make-file-2"]}))
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        # scenario 1: B is 20% cheaper than A, both valid.
        # scenario 2: A is valid and cheap; B's run is invalid (a broken check) but spent far more.
        updates = {"make-file__a__r1": {"usage": {"output_tokens": 100}, "passed": True},
                  "make-file__b__r1": {"usage": {"output_tokens": 80}, "passed": True},
                  "make-file-2__a__r1": {"usage": {"output_tokens": 100}, "passed": True},
                  "make-file-2__b__r1": {"usage": {"output_tokens": 20000}, "passed": None,
                                         "checks": {"check_error": "boom"}}}
        for job_name, fields in updates.items():
            p = self.out / "runs" / job_name / "result.json"
            r = json.loads(p.read_text())
            r.update(fields)
            p.write_text(json.dumps(r))
        payload = json.loads(self.run_cli("summarize", str(self.out), "--json", "--baseline", "a").stdout)
        pct = payload["pct_vs_baseline"]["b"]["output_tokens"]
        # both scenarios show B costing more (not less): -20% and +19900%, never pooled into one number
        # that could show B as cheaper overall.
        self.assertEqual(pct["n_scenarios"], 2)
        self.assertAlmostEqual(pct["median"], (-0.2 + 199.0) / 2)  # median of two values is their average
        self.assertGreater(pct["mean"], 0)  # never negative overall, unlike the pooled-and-valid-only bug
        # the expensive invalid run is not silently dropped from the mean either
        self.assertEqual(payload["arms"]["b"]["usage_mean"]["output_tokens"], (80 + 20000) / 2)
        self.assertEqual(payload["arms"]["b"]["no_usage"], 0)

    def test_artifact_arm_copies_content_and_is_judged(self):
        single = self.tmp / "artifacts" / "plan-a.md"
        write(single, "A bakery selling artisan bread to local restaurants.\n")
        directory = self.tmp / "artifacts" / "plan-b"
        write(directory / "index.md", "index\n")
        write(directory / "appendix.md", "appendix\n")
        write(self.tmp / "scenarios" / "eval-plan" / "scenario.json", json.dumps({
            "prompt": "You are an investor judging this business plan for viability.",
            "judge": {"question": "does it look investable?", "pass_when": "it does"}}))
        write(self.tmp / "plan.json", json.dumps({
            "name": "artifact", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"a": {"executor": "artifact", "artifact": "artifacts/plan-a.md"},
                     "b": {"executor": "artifact", "artifact": "artifacts/plan-b"}},
            "judge": {"executor": "claude", "model": "stub"},  # never invoked: judge_run is stubbed below
            "scenarios": ["scenarios/eval-plan"]}))
        with mock.patch("trial.judge_run", return_value=({"verdict": "pass", "reason": "looks fine"}, "stub-cell")):
            code = trial.main(["run", str(self.tmp / "plan.json"), "--out", str(self.out)])
        self.assertEqual(code, 0)
        res = self.results()
        self.assertTrue(res["eval-plan__a__r1"]["passed"])
        self.assertTrue(res["eval-plan__b__r1"]["passed"])
        # a single-file artifact's own content becomes the judged output
        self.assertEqual((self.out / "runs" / "eval-plan__a__r1" / "final-0.md").read_text(),
                         "A bakery selling artisan bread to local restaurants.\n")
        # a directory artifact with more than one file leaves a bounded listing instead
        listing = (self.out / "runs" / "eval-plan__b__r1" / "final-0.md").read_text().split()
        self.assertEqual(sorted(listing), ["appendix.md", "index.md"])
        stored = json.loads((self.out / "plan.json").read_text())["arms"]
        self.assertEqual(stored["a"]["artifact_sha256"], hashlib.sha256(single.read_bytes()).hexdigest())
        self.assertIn("artifact_sha256", stored["b"])
        # a rerun whose source content changed is refused, the same guarantee instructions get
        single.write_text("a completely different plan\n")
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("different artifact", r.stderr)

    def test_pairwise_outcome_and_win_rate(self):
        self.assertEqual(trial._pair_outcome({"winner": "1"}, {"winner": "2"}), "a_wins")
        self.assertEqual(trial._pair_outcome({"winner": "2"}, {"winner": "1"}), "b_wins")
        self.assertEqual(trial._pair_outcome({"winner": "tie"}, {"winner": "tie"}), "tie")
        self.assertEqual(trial._pair_outcome({"winner": "1"}, {"winner": "1"}), "inconsistent")  # a position bias
        self.assertEqual(trial._pair_outcome({"winner": "1"}, {"winner": "tie"}), "inconsistent")
        self.assertEqual(trial._pair_outcome({"winner": "error"}, {"winner": "1"}), "invalid")
        stats = trial._pairwise_stats([{"outcome": "a_wins"}, {"outcome": "a_wins"}, {"outcome": "b_wins"},
                                       {"outcome": "tie"}, {"outcome": "inconsistent"}, {"outcome": "invalid"}])
        self.assertEqual((stats["a_wins"], stats["b_wins"], stats["tie"], stats["inconsistent"], stats["invalid"]),
                         (2, 1, 1, 1, 1))
        self.assertEqual(stats["pairs"], 6)
        self.assertEqual(stats["decisive"], 3)  # ties, order-inconsistent, and invalid pairs are excluded
        self.assertAlmostEqual(stats["a_win_rate"], 2 / 3)
        self.assertEqual(stats["a_win_rate_interval"], list(trial.wilson(2, 3)))
        empty = trial._pairwise_stats([{"outcome": "tie"}])
        self.assertIsNone(empty["a_win_rate"])
        self.assertIsNone(empty["a_win_rate_interval"])

    def test_pairwise_judges_matched_runs_in_both_orders(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt",
            "judge": {"question": "which output looks more thorough?", "pass_when": "n/a"}}))
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/usr/bin/env python3\n"
                    "import re, sys\n"
                    "data = sys.stdin.read()\n"
                    "m = re.search(r'<response_1>\\n(.*?)\\n</response_1>', data, re.S)\n"
                    "r1 = m.group(1) if m else ''\n"
                    "w = '1' if 'ALPHA_OUTPUT' in r1 else '2'\n"
                    "print('{\"structured_output\": {\"winner\": \"%s\", \"reason\": \"seen\"}}' % w)\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "claude", "model": "j", "binary": str(fake), "base_url": "http://proxy.invalid",
                 "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        write(self.tmp / "plan.json", json.dumps({"name": "pw", "repeats": 2, "sandbox": self.default_sandbox,
            "arms": {"alpha": {"executor": "command", "command": "echo ALPHA_OUTPUT"},
                     "beta": {"executor": "command", "command": "echo BETA_OUTPUT"}},
            "judge": judge, "scenarios": ["scenarios/make-file"]}))
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("alpha win rate 100%", r.stdout)
        self.assertIn("alpha 2 - beta 0 - tie 0 - inconsistent 0", r.stdout)
        detail = json.loads((self.out / "pairwise" / "alpha__beta" / "make-file__r1.json").read_text())
        self.assertEqual(detail["outcome"], "a_wins")
        self.assertEqual(detail["orders"][0]["order"], ["alpha", "beta"])
        self.assertEqual(detail["orders"][0]["verdict"]["winner"], "1")  # alpha shown first, and wins as "1"
        self.assertEqual(detail["orders"][1]["order"], ["beta", "alpha"])
        self.assertEqual(detail["orders"][1]["verdict"]["winner"], "2")  # alpha shown second, and wins as "2"
        summary = json.loads((self.out / "pairwise" / "alpha__beta.json").read_text())
        self.assertEqual(summary["overall"]["a_wins"], 2)
        self.assertAlmostEqual(summary["overall"]["a_win_rate"], 1.0)
        # the judge sees each output's own text, never an arm's name - and its own working directory,
        # which some agent CLIs put in the model's context, names neither the arms nor the scenario either
        cell = detail["cell"]
        self.assertNotIn("alpha", cell)
        self.assertNotIn("beta", cell)
        self.assertNotIn("make-file", cell)
        cell_dir = self.out / "pairwise" / ".cells" / cell
        self.assertTrue(cell_dir.is_dir())
        prompt = (cell_dir / "order-1" / "prompt.md").read_text()
        self.assertNotIn("alpha", prompt)
        self.assertNotIn("beta", prompt)
        # surfaced in both summarize --json and the markdown summary
        payload = json.loads(self.run_cli("summarize", str(self.out), "--json").stdout)
        self.assertEqual(payload["pairwise"]["alpha__beta"]["overall"]["a_wins"], 2)
        self.assertIn("Pairwise comparisons", self.run_cli("summarize", str(self.out)).stdout)
        # an unknown arm is refused by name
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no arm nope", r.stderr)

    def test_report_json_contents_and_size_bounds(self):
        write(self.tmp / "arms" / "k.md", "be terse\n")
        long_text = "x" * (trial.REPORT_EXCERPT_CHARS * 3)
        write(self.tmp / "plan.json", json.dumps({
            "name": "rep", "repeats": 1, "baseline": "good", "decision_rule": "ship whichever passes more scenarios",
            "sandbox": self.default_sandbox,
            "arms": {"good": {"executor": "command", "instructions": "arms/k.md", "command": f"printf '%s' '{long_text}'"},
                     "bad": {"executor": "command", "command": "true"}},
            "scenarios": ["scenarios/make-file"]}))
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        payload = trial.report(self.out)
        self.assertEqual(payload["name"], "rep")
        self.assertEqual(payload["plan"]["decision_rule"], "ship whichever passes more scenarios")
        self.assertEqual(payload["plan"]["scenarios"][0]["prompt"], "create out.txt")
        self.assertIn("instructions_sha256", payload["plan"]["arms"]["good"])
        good_run = next(r for r in payload["runs"] if r["arm"] == "good")
        self.assertEqual((good_run["scenario"], good_run["repeat"]), ("make-file", 1))
        self.assertIn("valid", good_run)
        self.assertLessEqual(len(good_run["final_message_excerpt"]), trial.REPORT_EXCERPT_CHARS)
        self.assertTrue(good_run["final_message_excerpt"])
        self.assertIn("interval", payload["arms"]["good"])
        self.assertEqual(payload["baseline"], "good")
        self.assertIn("bad", payload["pct_vs_baseline"])
        self.assertEqual(payload["pairwise"], {})
        # the document stays bounded even with a long final message somewhere in it
        self.assertLess(len(json.dumps(payload)), 20000)
        out_file = self.tmp / "report.json"
        r = self.run_cli("report", str(self.out), "--out", str(out_file))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(out_file.read_text())["name"], "rep")

    def test_executor_readable_never_exposes_home_or_its_immediate_children(self):
        fake_home = self.tmp / "fakehome"
        # ~/bin/codex: the "parent of a bin/ directory" rule used to expose the whole home directory.
        shallow = fake_home / "bin" / "codex"
        write(shallow, "#!/bin/sh\necho hi\n", 0o755)
        with mock.patch("trial.Path.home", return_value=fake_home):
            readable = trial._executor_readable(str(shallow))
        self.assertNotIn(fake_home, readable)
        self.assertIn(fake_home / "bin", readable)  # the binary's own, narrow directory is still needed

        # ~/.local/bin/codex and ~/.cargo/bin/codex: a shim placed directly in one of these broad,
        # multi-purpose directories one level below home (which can hold unrelated credentials - a real
        # host's ~/.cargo/credentials.toml, for example, or unrelated user scripts) gets only the single
        # binary FILE exposed, never the whole shared directory around it.
        for sub in (".local", ".cargo"):
            b = fake_home / sub / "bin" / "codex"
            write(b, "#!/bin/sh\necho hi\n", 0o755)
            with mock.patch("trial.Path.home", return_value=fake_home):
                readable = trial._executor_readable(str(b))
            self.assertNotIn(fake_home / sub, readable, sub)
            self.assertNotIn(fake_home / sub / "bin", readable, sub)
            self.assertIn(b, readable, sub)  # the binary itself still runs

        # a package root that sits well below home (a real npm-style global install under $HOME) is still
        # exposed: only the broad, shallow directories immediately under home are guarded against.
        real_bin = fake_home / ".npm-global" / "lib" / "node_modules" / "codex" / "bin" / "codex"
        write(real_bin, "#!/usr/bin/env node\n", 0o755)
        with mock.patch("trial.Path.home", return_value=fake_home):
            readable = trial._executor_readable(str(real_bin))
        self.assertIn(fake_home / ".npm-global" / "lib" / "node_modules" / "codex", readable)

        # a native-installer layout (~/.local/bin/claude -> ~/.local/share/claude/versions/2.1.0/claude):
        # the symlink's own directory is the same broad, shared ~/.local/bin as above (never exposed whole,
        # only the symlink file itself), while the resolved target sits well below home and keeps its whole
        # versioned directory exposed.
        target = fake_home / ".local" / "share" / "claude" / "versions" / "2.1.0" / "claude"
        write(target, "#!/bin/sh\necho hi\n", 0o755)
        shim = fake_home / ".local" / "bin" / "claude"
        shim.parent.mkdir(parents=True, exist_ok=True)
        shim.symlink_to(target)
        with mock.patch("trial.Path.home", return_value=fake_home):
            readable = trial._executor_readable(str(shim))
        self.assertNotIn(fake_home / ".local" / "bin", readable)
        self.assertIn(shim, readable)
        self.assertIn(target.parent, readable)

    def test_codex_sandbox_maps_the_documented_modes_and_passes_through_others(self):
        self.assertEqual(trial._codex_sandbox({}), ("danger-full-access", True))
        self.assertEqual(trial._codex_sandbox({"sandbox": "confined"}), ("danger-full-access", True))
        # Codex itself rejects "-s none"; the runtime's own "none" opt-out maps to Codex's fully-open mode.
        self.assertEqual(trial._codex_sandbox({"sandbox": "none"}), ("danger-full-access", False))
        # anything else is a Codex-native mode name, passed straight through, never bwrap-wrapped by us.
        self.assertEqual(trial._codex_sandbox({"sandbox": "workspace-write"}), ("workspace-write", False))

    def test_only_literal_none_turns_off_checks_git_and_judge_confinement(self):
        self.assertFalse(trial._unconfined({}))
        self.assertFalse(trial._unconfined({"sandbox": "confined"}))
        # a Codex-native mode name changes only what run_codex passes to Codex's own -s flag; it must never
        # silently drop the bubblewrap protection checks, git, and judges rely on the way "none" does.
        self.assertFalse(trial._unconfined({"sandbox": "workspace-write"}))
        self.assertTrue(trial._unconfined({"sandbox": "none"}))
        jd = self.tmp / "judge-confinement-dir"
        (jd / "work").mkdir(parents=True)
        self.assertEqual(trial._judge_confinement(jd, [], {"sandbox": "none"}, self.tmp), [])
        if shutil.which("bwrap"):
            self.assertTrue(trial._judge_confinement(jd, [], {"sandbox": "workspace-write"}, self.tmp))
            self.assertTrue(trial._judge_confinement(jd, [], {}, self.tmp))
        else:
            with self.assertRaisesRegex(trial.TrialError, "bubblewrap"):
                trial._judge_confinement(jd, [], {"sandbox": "workspace-write"}, self.tmp)

    def test_lock_uses_flock_and_releases_the_instant_the_holder_exits(self):
        out = self.tmp / "lockdir"
        out.mkdir()
        lock = out / ".trial.lock"
        # A live holder in a genuinely separate process (so flock's own mutual exclusion applies, not just
        # an in-process guess) blocks a second run cleanly, with no stale-lock heuristic involved at all.
        holder = subprocess.Popen([sys.executable, "-c",
            "import fcntl, sys, time\n"
            "f = open(sys.argv[1], 'wb')\n"
            "fcntl.flock(f, fcntl.LOCK_EX)\n"
            "sys.stdout.write('locked\\n'); sys.stdout.flush()\n"
            "time.sleep(2)\n", str(lock)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(out))
            self.assertEqual(r.returncode, 2)
            self.assertIn("in use by another trial.py run", r.stderr)
        finally:
            holder.wait(timeout=10)
        # released the instant the holder exited: no age-based waiting, no pid-liveness guessing needed.
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_lock_falls_back_to_the_pid_age_scheme_without_fcntl(self):
        out = self.tmp / "lockdir2"
        out.mkdir()
        lock = out / ".trial.lock"
        with mock.patch("trial.fcntl", None):
            # a lock naming a pid that is not running is reclaimed immediately, however fresh it is.
            lock.write_text(f"999999999@{socket.gethostname()}")
            with trial._lock(out):
                self.assertTrue(lock.exists())
                self.assertEqual(lock.read_text().split("@")[0], str(os.getpid()))
            self.assertFalse(lock.exists())  # released on the way out, since this process still owned it

            # a lock naming a pid that IS running (standing in for a long trial, not a crashed one) is
            # never reclaimed no matter how old it looks - the 6-hour age was only ever a fallback.
            lock.write_text(f"{os.getpid()}@{socket.gethostname()}")
            old = time.time() - 100 * 3600
            os.utime(lock, (old, old))
            with self.assertRaisesRegex(trial.TrialError, "in use by another"):
                with trial._lock(out):
                    pass
            self.assertTrue(lock.exists())  # never deleted: it was never ours to release

            # an unparseable or pre-existing-format lock (no "pid@host") falls back to the age-based rule.
            lock.write_text("")
            os.utime(lock, (old, old))
            with trial._lock(out):
                pass
            self.assertFalse(lock.exists())

    def test_artifact_arm_ignores_fixture_files_when_counting_produced_output(self):
        single = self.tmp / "artifacts" / "pitch-a.md"
        write(single, "Pitch A: a bakery selling artisan bread.\n")
        write(self.tmp / "scenarios" / "eval-plan" / "scenario.json", json.dumps({
            "prompt": "You are an investor judging this business plan for viability.",
            "judge": {"question": "does it look investable?", "pass_when": "it does"}}))
        # a fixture the scenario supplies to every arm (shared context an investor would also see) sits
        # alongside the artifact in work/, and must never be mistaken for part of the artifact itself.
        write(self.tmp / "scenarios" / "eval-plan" / "fixture" / "brief.txt", "shared investor brief\n")
        write(self.tmp / "plan.json", json.dumps({
            "name": "artifact-fixture", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"a": {"executor": "artifact", "artifact": "artifacts/pitch-a.md"}},
            "judge": {"executor": "claude", "model": "stub"},  # never invoked: judge_run is stubbed below
            "scenarios": ["scenarios/eval-plan"]}))
        with mock.patch("trial.judge_run", return_value=({"verdict": "pass", "reason": "looks fine"}, "stub-cell")):
            code = trial.main(["run", str(self.tmp / "plan.json"), "--out", str(self.out)])
        self.assertEqual(code, 0)
        job = self.out / "runs" / "eval-plan__a__r1"
        self.assertTrue((job / "work" / "brief.txt").exists())  # the fixture is still there
        # ... but the single-file artifact's own content, not a two-file listing, is the judged output
        self.assertEqual((job / "final-0.md").read_text(), "Pitch A: a bakery selling artisan bread.\n")

    def test_pairwise_includes_each_runs_judge_context_evidence(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt",
            "judge": {"question": "which output looks more thorough?", "pass_when": "n/a"}}))
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {}\n\n\n"
              "def judge_context(run):\n    return 'EVIDENCE_FOR_' + run.final_message.strip()\n")
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    "echo '{\"structured_output\": {\"winner\": \"tie\", \"reason\": \"n/a\"}}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "claude", "model": "j", "binary": str(fake), "base_url": "http://proxy.invalid",
                 "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        write(self.tmp / "plan.json", json.dumps({"name": "pw-evidence", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"alpha": {"executor": "command", "command": "echo ALPHA_OUTPUT"},
                     "beta": {"executor": "command", "command": "echo BETA_OUTPUT"}},
            "judge": judge, "scenarios": ["scenarios/make-file"]}))
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 0, r.stderr)
        detail = json.loads((self.out / "pairwise" / "alpha__beta" / "make-file__r1.json").read_text())
        prompt = (self.out / "pairwise" / ".cells" / detail["cell"] / "order-1" / "prompt.md").read_text()
        self.assertIn("<evidence_1>\nEVIDENCE_FOR_ALPHA_OUTPUT\n</evidence_1>", prompt)
        self.assertIn("<evidence_2>\nEVIDENCE_FOR_BETA_OUTPUT\n</evidence_2>", prompt)

    def test_pairwise_gives_neither_side_evidence_when_either_ones_fails(self):
        # judge_context raising for only one side used to silently give evidence to the other side alone,
        # skewing a supposedly blind comparison toward whichever response happened to have evidence.
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt",
            "judge": {"question": "which output looks more thorough?", "pass_when": "n/a"}}))
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {}\n\n\n"
              "def judge_context(run):\n"
              "    if 'BETA' in run.final_message:\n        raise ValueError('no evidence for beta')\n"
              "    return 'EVIDENCE_FOR_' + run.final_message.strip()\n")
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    "echo '{\"structured_output\": {\"winner\": \"tie\", \"reason\": \"n/a\"}}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "claude", "model": "j", "binary": str(fake), "base_url": "http://proxy.invalid",
                 "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        write(self.tmp / "plan.json", json.dumps({"name": "pw-evidence-fail", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"alpha": {"executor": "command", "command": "echo ALPHA_OUTPUT"},
                     "beta": {"executor": "command", "command": "echo BETA_OUTPUT"}},
            "judge": judge, "scenarios": ["scenarios/make-file"]}))
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 0, r.stderr)
        detail = json.loads((self.out / "pairwise" / "alpha__beta" / "make-file__r1.json").read_text())
        self.assertIn("b", detail["evidence_errors"])
        self.assertIn("no evidence for beta", detail["evidence_errors"]["b"])
        prompt = (self.out / "pairwise" / ".cells" / detail["cell"] / "order-1" / "prompt.md").read_text()
        # neither side got evidence, even though alpha's own judge_context call would have succeeded
        self.assertNotIn("<evidence_1>", prompt)
        self.assertNotIn("<evidence_2>", prompt)

    def test_native_windows_is_refused_with_a_clear_error(self):
        with mock.patch("trial.os.name", "nt"):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                code = trial.main(["run", str(self.tmp / "plan.json"), "--out", str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("WSL", buf.getvalue())
        self.assertFalse(self.out.exists())  # refused before anything was scheduled

    def test_missing_tomllib_gives_a_clear_error_only_when_a_config_is_actually_read(self):
        # tomllib is 3.11+ stdlib; macOS's own /usr/bin/python3 is often older. It is only ever needed to
        # read an existing ~/.codex/config.toml - never for the common case of no custom provider at all.
        with mock.patch("trial.tomllib", None):
            with self.assertRaisesRegex(trial.TrialError, "Python 3.11 or newer"):
                trial._require_tomllib()
            with mock.patch("trial.CODEX_HOME_SRC", self.tmp / "no-such-codex-home"):
                self.assertEqual(trial._provider_block(), {})  # no config.toml to read: no error
                trial._provider_config("m", "medium")  # likewise
            codex_home = self.tmp / "codex-home-with-config"
            write(codex_home / "config.toml", 'model_provider = "x"\n[model_providers.x]\nbase_url = "https://x"\n')
            with mock.patch("trial.CODEX_HOME_SRC", codex_home):
                with self.assertRaisesRegex(trial.TrialError, "Python 3.11 or newer"):
                    trial._provider_block()

    def test_default_codex_key_variable_is_codex_api_key_absent_a_custom_provider(self):
        # Most people running Codex against its own default endpoint have no `model_providers` block in
        # ~/.codex/config.toml at all - OPENAI_API_KEY is not read by `codex exec` itself in that case
        # (confirmed against real codex-cli and OpenAI's own docs); CODEX_API_KEY is.
        with mock.patch("trial.CODEX_HOME_SRC", self.tmp / "no-such-codex-home"):
            self.assertEqual(trial._default_key_var("codex"), "CODEX_API_KEY")
        codex_home = self.tmp / "codex-home-with-provider"
        write(codex_home / "config.toml", 'model_provider = "custom"\n[model_providers.custom]\n'
                                          'base_url = "https://x"\nenv_key = "MY_CUSTOM_KEY"\n')
        with mock.patch("trial.CODEX_HOME_SRC", codex_home):
            self.assertEqual(trial._default_key_var("codex"), "MY_CUSTOM_KEY")  # a configured provider still wins
        self.assertEqual(trial._default_key_var("claude"), "ANTHROPIC_API_KEY")

    def test_copy_auth_lets_a_codex_arm_run_with_no_api_key(self):
        # Before this fix, an arm with "copy_auth": true still demanded an API key even though the copied
        # ChatGPT login is its whole authentication - defeating the "no API key available" case copy_auth
        # exists for (see trials.md, "Logging in without an API key").
        fake_auth = self.tmp / "fake-auth.json"
        fake_auth.write_text('{"fake": true}')
        saved = dict(trial._AUTH_FILE)
        trial._AUTH_FILE["codex"] = (fake_auth, Path("auth.json"))
        try:
            fake = self.tmp / "bin" / "codex"
            write(fake, "#!/bin/sh\n"
                        "cat \"$CODEX_HOME/auth.json\" > seen.txt 2>/dev/null || echo MISSING > seen.txt\n"
                        "[ -n \"$OPENAI_API_KEY$CODEX_API_KEY\" ] && echo LEAKED >> seen.txt\n"
                        "cat >/dev/null\n"
                        "echo '{\"type\": \"turn.completed\", \"usage\": {}}'\n", 0o755)
            write(self.tmp / "scenarios" / "make-file" / "check.py",
                  "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
            saved_env = {k: os.environ.pop(k, None) for k in ("OPENAI_API_KEY", "CODEX_API_KEY")}
            try:
                codex = {"c": {"executor": "codex", "model": "m", "binary": str(fake), "copy_auth": True}}
                # in-process (trial.main), not the subprocess self.run_cli uses: a subprocess re-imports
                # trial.py and would read the real host's own _AUTH_FILE, not this test's monkeypatch.
                self.assertEqual(trial.main(["run", self._plan(codex), "--out", str(self.out)]), 0)
            finally:
                for k, v in saved_env.items():
                    if v is not None:
                        os.environ[k] = v
            self.assertEqual(self.results()["make-file__c__r1"]["checks"]["seen"], '{"fake": true}')
            # and the copied login does not survive the finished run - CODEX_HOME is ~/.codex inside the
            # run's own private home (harness/home), not a bare top-level "home", so the glob has to look
            # there too, or this would pass vacuously no matter what the runner actually did.
            self.assertEqual(list(self.out.glob("**/auth.json")), [])
        finally:
            trial._AUTH_FILE.clear()
            trial._AUTH_FILE.update(saved)

    def test_copy_auth_login_is_removed_even_when_the_arm_never_finishes(self):
        # A copied login used to survive a job whose executor raised before completing (a missing binary,
        # here) - the file was never pruned because _run_job_once's own _prune() is only reached on normal
        # completion.
        fake_auth = self.tmp / "fake-auth.json"
        fake_auth.write_text('{"fake": true}')
        saved = dict(trial._AUTH_FILE)
        trial._AUTH_FILE["codex"] = (fake_auth, Path("auth.json"))
        try:
            codex = {"c": {"executor": "codex", "model": "m", "binary": str(self.tmp / "no-such-codex"),
                          "copy_auth": True}}
            r = self.run_cli("run", self._plan(codex), "--out", str(self.out))
            self.assertEqual(r.returncode, 2, r.stderr)  # the whole run stops: a missing binary is fatal
            self.assertEqual(list(self.out.glob("**/auth.json")), [])
        finally:
            trial._AUTH_FILE.clear()
            trial._AUTH_FILE.update(saved)

    def test_codex_home_matches_a_real_install_and_a_followup_still_resumes(self):
        # CODEX_HOME is ~/.codex inside the run's own private home, not a sibling directory outside it: a
        # scenario (or the agent itself) can plant a session log under $HOME/.codex/sessions and expect
        # both to see it and to find it unchanged afterward, and a follow-up prompt still resumes the same
        # thread.
        s = self.tmp / "scenarios" / "make-file"
        write(s / "setup.sh", 'mkdir -p "$HOME/.codex/sessions" && echo PLANTED-MARKER > "$HOME/.codex/sessions/marker.jsonl"\n')
        fake = self.tmp / "bin" / "codex"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    "echo \"$CODEX_HOME\" > codex-home-seen.txt\n"
                    "case \"$*\" in\n"
                    "  *resume*)\n"
                    "    cp \"$CODEX_HOME/sessions/marker.jsonl\" marker-after-resume.txt\n"
                    "    echo '{\"type\": \"turn.completed\", \"usage\": {}}'\n"
                    "    ;;\n"
                    "  *)\n"
                    "    cp \"$CODEX_HOME/sessions/marker.jsonl\" marker-before-resume.txt\n"
                    "    echo 'own-rollout' >> \"$CODEX_HOME/sessions/own.jsonl\"\n"
                    "    echo '{\"type\": \"thread.started\", \"thread_id\": \"T1\"}'\n"
                    "    echo '{\"type\": \"turn.completed\", \"usage\": {}}'\n"
                    "    ;;\n"
                    "esac\n", 0o755)
        write(s / "scenario.json", json.dumps({"prompt": "go", "followups": ["again"],
                                               "required": ["codex_home_is_dollar_home_codex", "marker_seen_before_resume",
                                                            "marker_unchanged_after_resume"]}))
        write(s / "check.py", (
            "def check(run):\n"
            "    expected = str(run.dir / 'harness' / 'home' / '.codex')\n"
            "    return {'codex_home_is_dollar_home_codex': run.file('codex-home-seen.txt').strip() == expected,\n"
            "            'marker_seen_before_resume': run.file('marker-before-resume.txt').strip() == 'PLANTED-MARKER',\n"
            "            'marker_unchanged_after_resume': run.file('marker-after-resume.txt').strip() == 'PLANTED-MARKER'}\n"))
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        codex = {"c": {"executor": "codex", "model": "m", "binary": str(fake),
                      "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(codex), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        result = self.results()["make-file__c__r1"]
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(all(result["checks"].values()), result["checks"])
        self.assertTrue(result["passed"])
        # codex's own new rollout landed beside the planted one, both under the same ~/.codex/sessions
        codex_home = next(self.out.glob("runs/*/harness/home/.codex"))
        self.assertEqual((codex_home / "sessions" / "own.jsonl").read_text().strip(), "own-rollout")
        self.assertEqual((codex_home / "sessions" / "marker.jsonl").read_text().strip(), "PLANTED-MARKER")

    def test_the_codex_judges_home_matches_a_codex_arms_own_layout(self):
        # Before this fix, judge_run's own codex branch still used a bare "home" sibling of the judge's
        # private home (jd / "home"), while run_codex (above) had already moved to env["HOME"] / ".codex" -
        # so a judge "resources" entry keyed under ".codex/..." (trials.md: the judge accepts the same
        # "resources" as an arm) never reached the judge the way it reaches a codex arm.
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file"],
                                               "judge": {"question": "q?", "pass_when": "it passes"}}))
        write(s / "check.py", "def check(run):\n    return {'made_file': run.file('out.txt').strip() == 'hi'}\n")
        fake_judge = self.tmp / "bin" / "judge-codex"
        write(fake_judge, "#!/bin/sh\ncat >/dev/null\n"
                          "echo \"$CODEX_HOME\" > codex-home-seen.txt\n"
                          "out=\"\"; prev=\"\"\n"
                          "for a in \"$@\"; do [ \"$prev\" = \"-o\" ] && out=\"$a\"; prev=\"$a\"; done\n"
                          "echo '{\"verdict\": \"pass\", \"reason\": \"ok\"}' > \"$out\"\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = {"executor": "codex", "model": "m", "binary": str(fake_judge),
                "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        codex_plan = self._plan({"good": {"executor": "command", "command": "echo hi > out.txt"}}, judge)
        r = self.run_cli("run", codex_plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.results()["make-file__good__r1"]["judge"]["verdict"], "pass")
        jd = self.judge_cell("make-file__good__r1")
        self.assertEqual((jd / "work" / "codex-home-seen.txt").read_text().strip(),
                         str(jd / "harness" / "home" / ".codex"))

    def test_a_planted_codex_config_refuses_the_run_instead_of_being_silently_overwritten(self):
        # Before this fix, run_codex unconditionally overwrote ~/.codex/config.toml even when a scenario's
        # setup.sh (which runs before the executor, with the same $HOME) had already put one there -
        # silently discarding it instead of telling the plan author their planted config never took effect.
        s = self.tmp / "scenarios" / "make-file"
        write(s / "setup.sh", 'mkdir -p "$HOME/.codex" && echo planted > "$HOME/.codex/config.toml"\n')
        codex = {"c": {"executor": "codex", "model": "m", "binary": str(self.tmp / "bin" / "codex")}}
        r = self.run_cli("run", self._plan(codex), "--out", str(self.out))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("config.toml", r.stderr)
        self.assertIn("already exists", r.stderr)
        home = next(self.out.glob("runs/*/harness/home/.codex"))
        self.assertEqual((home / "config.toml").read_text().strip(), "planted")  # never overwritten

    def test_a_planted_agents_md_refuses_the_run_even_for_an_arm_with_no_instructions_of_its_own(self):
        # Before this fix, a planted AGENTS.md was copied over only when the arm had its own "instructions"
        # - so a baseline arm with none silently kept a scenario's planted global instructions while a
        # treatment arm silently lost them to its own, biasing whatever the trial was comparing (see
        # trials.md: "no plugins, skills, memories, or user instructions load beyond the arm's").
        s = self.tmp / "scenarios" / "make-file"
        write(s / "setup.sh", 'mkdir -p "$HOME/.codex" && echo "SCENARIO GLOBAL AGENTS" > "$HOME/.codex/AGENTS.md"\n')
        codex = {"c": {"executor": "codex", "model": "m", "binary": str(self.tmp / "bin" / "codex")}}  # no "instructions"
        r = self.run_cli("run", self._plan(codex), "--out", str(self.out))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("AGENTS.md", r.stderr)

    def test_resources_that_would_make_codex_home_read_only_refuse_the_run(self):
        # A "resources" entry keyed ".codex" (or, below, ".codex/sessions") is copied read-only
        # (_copy_readonly) - live, this left real Codex unable to record its own rollout at all ("Read-only
        # file system"), and a follow-up "resume" then failed outright. Refusing before codex ever starts
        # is clearer than either failure.
        whole_codex = self.tmp / "planted-codex-home"
        write(whole_codex / "config.toml", "planted\n")
        codex = {"c": {"executor": "codex", "model": "m", "binary": str(self.tmp / "bin" / "codex"),
                      "resources": {".codex": str(whole_codex)}}}
        r = self.run_cli("run", self._plan(codex), "--out", str(self.out))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(".codex", r.stderr)

    def test_resources_that_would_make_codex_sessions_read_only_refuse_the_run(self):
        sessions = self.tmp / "planted-sessions"
        write(sessions / "old" / "log.jsonl", "{}\n")
        codex = {"c": {"executor": "codex", "model": "m", "binary": str(self.tmp / "bin" / "codex"),
                      "resources": {".codex/sessions": str(sessions)}}}
        r = self.run_cli("run", self._plan(codex), "--out", str(self.out))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("sessions", r.stderr)

    def test_a_mid_run_rewrite_of_codex_home_never_reaches_the_next_turn(self):
        # In a Codex-native "sandbox" such as "workspace-write", it is Codex's own internal sandbox - not
        # this runtime's bubblewrap - that decides whether an agent's shell tool calls can write inside
        # CODEX_HOME; this test is about run_codex's own restore, not that boundary (a fake binary has no
        # sandbox of its own to bypass either way): it proves a config.toml or AGENTS.md an agent rewrote
        # during one turn is never what the *next* codex process (here, a "resume") actually reads.
        instructions = self.tmp / "instructions.md"
        instructions.write_text("PRISTINE INSTRUCTIONS\n")
        fake = self.tmp / "bin" / "codex"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    "case \"$*\" in\n"
                    "  *resume*)\n"
                    "    cp \"$CODEX_HOME/config.toml\" config-seen.txt\n"
                    "    cp \"$CODEX_HOME/AGENTS.md\" agents-seen.txt\n"
                    "    echo '{\"type\": \"turn.completed\", \"usage\": {}}'\n"
                    "    ;;\n"
                    "  *)\n"
                    "    echo TAMPERED > \"$CODEX_HOME/config.toml\"\n"
                    "    echo TAMPERED-AGENTS > \"$CODEX_HOME/AGENTS.md\"\n"
                    "    echo '{\"type\": \"thread.started\", \"thread_id\": \"T1\"}'\n"
                    "    echo '{\"type\": \"turn.completed\", \"usage\": {}}'\n"
                    "    ;;\n"
                    "esac\n", 0o755)
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "go", "followups": ["again"],
                                               "required": ["config_restored", "agents_restored"]}))
        write(s / "check.py", (
            "def check(run):\n"
            "    config = run.file('config-seen.txt')\n"
            "    agents = run.file('agents-seen.txt')\n"
            "    return {'config_restored': 'TAMPERED' not in config and 'model = \"m\"' in config,\n"
            "            'agents_restored': agents.strip() == 'PRISTINE INSTRUCTIONS'}\n"))
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        codex = {"c": {"executor": "codex", "model": "m", "binary": str(fake), "instructions": str(instructions),
                      "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(codex), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        result = self.results()["make-file__c__r1"]
        self.assertTrue(all(result["checks"].values()), result["checks"])

    def test_replacing_codex_home_with_a_symlink_never_redirects_the_login_cleanup_onto_it(self):
        # _remove does not follow a symlink at the very last path component, but the directories along a
        # path it is given are followed like any other filesystem lookup - so an agent whose shell tool
        # calls replace CODEX_HOME itself with a symlink before exiting ("rm -rf $CODEX_HOME && ln -s
        # /some/host/dir $CODEX_HOME") used to make the finally block's own auth.json cleanup land on
        # whatever that symlink pointed at, anywhere on the host the agent could name.
        victim = self.tmp / "victim"
        victim.mkdir(parents=True, exist_ok=True)
        (victim / "auth.json").write_text("VICTIM-AUTH\n")
        fake = self.tmp / "bin" / "codex"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    f"rm -rf \"$CODEX_HOME\" && ln -s {victim} \"$CODEX_HOME\"\n"
                    "echo '{\"type\": \"turn.completed\", \"usage\": {}}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        # the finally block's own auth.json cleanup (see run_codex) runs unconditionally, whether or not
        # "copy_auth" is set, so an ordinary key-based arm exercises it just as well.
        codex = {"c": {"executor": "codex", "model": "m", "binary": str(fake),
                      "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        write(self.tmp / "plan.json", json.dumps({"name": "p", "repeats": 1, "sandbox": "none",
                                                   "scenarios": ["scenarios/make-file"], "arms": codex}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((victim / "auth.json").read_text(), "VICTIM-AUTH\n")

    def test_replacing_claude_home_with_a_symlink_never_redirects_the_credential_cleanup_onto_it(self):
        # The same pattern as run_codex's matching test above, for run_claude's ~/.claude/.credentials.json.
        victim = self.tmp / "victim"
        victim.mkdir(parents=True, exist_ok=True)
        (victim / ".credentials.json").write_text("VICTIM-CREDS\n")
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    f"rm -rf \"$HOME/.claude\" && ln -s {victim} \"$HOME/.claude\"\n"
                    "echo '{\"type\": \"result\", \"result\": \"done\"}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        # See run_codex's matching test above: the finally block's own credential cleanup runs
        # unconditionally, whether or not "copy_auth" is set.
        claude = {"c": {"executor": "claude", "model": "m", "binary": str(fake),
                        "base_url": "http://proxy.invalid", "api_key_var": "TRIAL_TEST_KEY",
                        "env_file": str(env_file)}}
        write(self.tmp / "plan.json", json.dumps({"name": "p", "repeats": 1, "sandbox": "none",
                                                   "scenarios": ["scenarios/make-file"], "arms": claude}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((victim / ".credentials.json").read_text(), "VICTIM-CREDS\n")

    def test_prune_removes_codex_caches_from_their_new_home_relative_location(self):
        # PRUNE (see _prune) has to name where a codex run's caches actually land - ~/.codex inside the
        # run's own private home, not a bare top-level "home" - or they are never removed at all.
        fake = self.tmp / "bin" / "codex"
        write(fake, "#!/bin/sh\ncat >/dev/null\n"
                    "mkdir -p \"$CODEX_HOME/skills\"\n"
                    "echo native-skill > \"$CODEX_HOME/skills/.system\"\n"
                    "echo '{\"cached\": true}' > \"$CODEX_HOME/models_cache.json\"\n"
                    "echo '{\"type\": \"turn.completed\", \"usage\": {}}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        codex = {"c": {"executor": "codex", "model": "m", "binary": str(fake),
                      "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        r = self.run_cli("run", self._plan(codex), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        codex_home = next(self.out.glob("runs/*/harness/home/.codex"))
        self.assertFalse((codex_home / "skills").exists())
        self.assertFalse((codex_home / "models_cache.json").exists())
        self.assertTrue((codex_home / "config.toml").exists())  # only the caches are pruned, not the state itself

    def test_missing_bubblewrap_is_refused_before_any_setup_script_runs(self):
        # Before this fix, a missing bwrap was only discovered per job, inside the first job's own executor
        # call - after plan.json had already been written and every earlier job's own setup.sh had already
        # run (leaving a ".pending" marker for each). Multiple repeats/arms made this worse: several jobs'
        # worth of setup work happened before the very first confined job's own failure was even reached.
        write(self.tmp / "plan.json", json.dumps({"name": "sb2", "repeats": 3,
            "arms": {"a": {"executor": "command", "command": "true"}, "b": {"executor": "command", "command": "true"}},
            "scenarios": ["scenarios/make-file"]}))
        real_which = shutil.which

        def fake_which(name, *a, **k):
            return None if name == "bwrap" else real_which(name, *a, **k)

        out = self.tmp / "sb2out"
        with mock.patch("trial.shutil.which", side_effect=fake_which):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                code = trial.main(["run", str(self.tmp / "plan.json"), "--out", str(out)])
        self.assertEqual(code, 2)
        self.assertIn("bubblewrap", buf.getvalue())
        self.assertFalse(out.exists())  # nothing was created at all: no plan.json, no setup.sh runs, no .pending

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap: proves the actual escape is closed")
    def test_confined_run_cannot_reach_host_sockets_under_run(self):
        # A read-only bind of "/" leaves Unix-domain sockets under /run fully reachable even with the host
        # otherwise read-only and home hidden - a user systemd/D-Bus bus, or a container runtime's control
        # socket - none of which the network namespace (still shared, so model APIs stay reachable) has any
        # boundary over.
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
        plan = self._plan({"a": {"executor": "command",
                                 "command": 'ls /run > seen.txt 2>&1 || true; ls -d /run/user 2>>seen.txt || true'}})
        write(self.tmp / "plan.json", json.dumps(dict(json.loads(Path(plan).read_text()), sandbox="confined")))
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        seen = self.results()["make-file__a__r1"]["checks"]["seen"]
        self.assertNotIn("user", seen.split())  # /run is an empty tmpfs, not the host's own /run
        self.assertIn("No such file or directory", seen)

    def test_a_symlinked_launcher_stays_a_link_inside_the_sandbox(self):
        """npm's bin/ entries are links into the package; binding one would copy its target to the link's path,
        and a launcher that resolves its dependencies from its own location then looks in the wrong place."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "lib" / "pkg" / "bin"
            pkg.mkdir(parents=True)
            target = pkg / "tool.js"
            target.write_text("#!/bin/sh\n")
            link = Path(tmp) / "bin" / "tool"
            link.parent.mkdir()
            link.symlink_to(os.path.relpath(target, link.parent))
            with mock.patch("shutil.which", return_value="/usr/bin/bwrap"):
                cmd = trial.confine_prefix(Path(tmp) / "job", [link, pkg])
            i = cmd.index("--symlink")
            self.assertEqual(cmd[i + 1:i + 3], [os.readlink(link), str(link)])
            self.assertNotIn(["--ro-bind", str(link), str(link)], [cmd[j:j + 3] for j in range(len(cmd) - 2)])

    def test_prune_removes_codex_databases_but_keeps_the_session_rollout(self):
        job = Path(self.tmp) / "job"
        codex = job / "harness" / "home" / ".codex"
        (codex / "sessions" / "2026").mkdir(parents=True)
        rollout = codex / "sessions" / "2026" / "rollout-1.jsonl"
        rollout.write_text("{}\n")
        for name in ("state_5.sqlite", "state_5.sqlite-wal", "logs_2.sqlite-shm", "memories_1.sqlite-journal"):
            (codex / name).write_text("x")
        (codex / "config.toml").write_text("model = 'm'\n")
        trial._prune(job)
        self.assertEqual(sorted(p.name for p in codex.iterdir()), ["config.toml", "sessions"])
        self.assertTrue(rollout.exists())

    def test_prune_build_output_removes_regenerable_caches_but_keeps_evidence_and_links(self):
        job = Path(self.tmp) / "buildjob"
        work = job / "work"
        # A Cargo target directory (matched by its own CACHEDIR.TAG, the marker Cargo itself writes).
        target = work / "target"
        (target / "debug" / "deps").mkdir(parents=True)
        target_tag = "Signature: 8a477f597d28d172789f06886806bc55\n# This file is a cache directory tag created by cargo.\n"
        (target / "CACHEDIR.TAG").write_text(target_tag)
        (target / "debug" / "deps" / "lib.rlib").write_text("x" * 10)
        # A Go build cache (matched by its own README, wherever GOCACHE actually points - not only under a
        # dot-cache directory, and not by name).
        go_cache = work / "sub" / "go-build"
        go_cache.mkdir(parents=True)
        (go_cache / "README").write_text("This directory holds cached build artifacts from the Go build system.\n")
        (go_cache / "ab").mkdir()
        (go_cache / "ab" / "entry").write_text("cached")
        # Python's own bytecode cache, matched by name alone.
        pycache = work / "pkg" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "mod.cpython-312.pyc").write_text("bytecode")
        # The agent's own source, never a build artifact.
        src = work / "src" / "main.rs"
        src.parent.mkdir(parents=True)
        src.write_text("fn main() {}\n")
        # A link out of the run directory: never followed, and never removed just for being named "target".
        outside = Path(self.tmp) / "outside-secret"
        outside.mkdir()
        (outside / "secret.txt").write_text("do not touch\n")
        evil_target = work / "evil" / "target"
        evil_target.parent.mkdir(parents=True)
        evil_target.symlink_to(outside)
        # A read-only directory (the way a resource copy - see _copy_readonly - or an agent's own chmod
        # leaves one) holding a target directory of its own: removing it needs write access reclaimed on
        # its parent, inside the run directory only.
        locked_parent = work / "locked"
        locked_target = locked_parent / "target"
        locked_target.mkdir(parents=True)
        (locked_target / "CACHEDIR.TAG").write_text(target_tag)
        locked_parent.chmod(0o500)
        try:
            found = trial._build_output_under(job)
            self.assertEqual({p.relative_to(job) for p in found},
                             {Path("work/target"), Path("work/sub/go-build"), Path("work/pkg/__pycache__"),
                              Path("work/locked/target")})
            trial._prune_build_output(job, found)
            self.assertFalse(target.exists())
            self.assertFalse(go_cache.exists())
            self.assertFalse(pycache.exists())
            self.assertFalse(locked_target.exists())
            self.assertTrue(src.exists())
            self.assertEqual(src.read_text(), "fn main() {}\n")
            self.assertTrue(evil_target.is_symlink())
            self.assertEqual(os.readlink(evil_target), str(outside))
            self.assertTrue(outside.is_dir())
            self.assertEqual((outside / "secret.txt").read_text(), "do not touch\n")
        finally:
            with contextlib.suppress(OSError):
                locked_parent.chmod(0o700)

    def test_prune_build_output_keeps_what_an_opt_out_asks_for(self):
        build_command = ('echo hi > out.txt; faketool x; printf "%s" "$TRIAL_PROMPT" > prompt.txt; '
                         'mkdir -p target/debug; '
                         'printf "# This file is a cache directory tag created by cargo.\\n" > target/CACHEDIR.TAG; '
                         'echo built > target/debug/binary')
        plan = {"name": "buildprune", "repeats": 1, "sandbox": self.default_sandbox,
                "arms": {"good": {"executor": "command", "command": build_command}},
                "scenarios": ["scenarios/make-file"]}
        write(self.tmp / "plan.json", json.dumps(plan))
        out = self.tmp / "out-default"
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = {p.parent.name: json.loads(p.read_text()) for p in (out / "runs").glob("*/result.json")}
        job = next(iter(res))
        self.assertTrue(res[job]["checks"]["made_file"])
        # Pruned by default, and result.json says so - so a missing artifact a later recheck cannot explain
        # from the run's own files alone is still explained by what this run recorded.
        self.assertEqual(res[job].get("pruned_build_output"), ["work/target"])
        self.assertFalse((out / "runs" / job / "work" / "target").exists())

        write(self.tmp / "plan.json", json.dumps(dict(plan, prune_build_output=False)))
        out2 = self.tmp / "out-plan-off"
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(out2))
        self.assertEqual(r.returncode, 0, r.stderr)
        res2 = {p.parent.name: json.loads(p.read_text()) for p in (out2 / "runs").glob("*/result.json")}
        job2 = next(iter(res2))
        self.assertNotIn("pruned_build_output", res2[job2])
        self.assertTrue((out2 / "runs" / job2 / "work" / "target" / "CACHEDIR.TAG").exists())

        write(self.tmp / "plan.json", json.dumps(plan))
        out3 = self.tmp / "out-env-off"
        r = subprocess.run([sys.executable, str(SCRIPT), "run", str(self.tmp / "plan.json"), "--out", str(out3)],
                           capture_output=True, text=True, timeout=300, env={**os.environ, "TRIAL_PRUNE_BUILD_OUTPUT": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        res3 = {p.parent.name: json.loads(p.read_text()) for p in (out3 / "runs").glob("*/result.json")}
        job3 = next(iter(res3))
        self.assertNotIn("pruned_build_output", res3[job3])
        self.assertTrue((out3 / "runs" / job3 / "work" / "target" / "CACHEDIR.TAG").exists())

    def test_recheck_after_build_output_pruning_still_scores_the_run(self):
        build_command = ('echo hi > out.txt; faketool x; printf "%s" "$TRIAL_PROMPT" > prompt.txt; '
                         'mkdir -p target/debug; '
                         'printf "# This file is a cache directory tag created by cargo.\\n" > target/CACHEDIR.TAG; '
                         'echo built > target/debug/binary')
        write(self.tmp / "plan.json", json.dumps({
            "name": "buildprune-recheck", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"good": {"executor": "command", "command": build_command}},
            "scenarios": ["scenarios/make-file"]}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        job = next(iter(self.results()))
        self.assertFalse((self.out / "runs" / job / "work" / "target").exists())
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        rechecked = self.results()[job]
        self.assertTrue(rechecked["rechecked"])
        self.assertTrue(rechecked["checks"]["made_file"])
        self.assertTrue(rechecked["checks"]["tool_called"])

    def test_model_listings_in_different_formats_are_cached_apart(self):
        """A proxy can answer Anthropic and OpenAI listing requests at the same URL with the same key; a Codex
        judge in a plan whose arms are all Claude must not receive the Claude listing."""
        seen = []

        def fake_run(cmd, **kw):
            fmt = cmd[cmd.index(trial._LIST_MODELS) + 2]
            seen.append(fmt)
            ids = ["claude-sonnet-5-5"] if fmt == "anthropic" else ["gpt-6-luna"]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(ids), "")

        trial._MODELS.clear()
        with mock.patch.dict(os.environ, {"TRIAL_ENV_FILE": "", "SHARED_KEY": "k"}), \
             mock.patch.object(trial, "_provider_block", return_value={"base_url": "https://proxy.example/v1"}), \
             mock.patch("subprocess.run", side_effect=fake_run):
            claude = trial.available_models({"executor": "claude", "base_url": "https://proxy.example",
                                             "api_key_var": "SHARED_KEY"})
            codex = trial.available_models({"executor": "codex", "api_key_var": "SHARED_KEY"})
        trial._MODELS.clear()
        self.assertEqual((claude, codex, seen), (["claude-sonnet-5-5"], ["gpt-6-luna"], ["anthropic", "openai"]))

    def test_a_run_whose_executor_never_reported_usage_adds_no_seconds_or_commands(self):
        runs = [{"usage": {"output_tokens": 100}, "seconds": 30.0, "commands": 4},
                {"usage": {}, "seconds": 0.2, "commands": 0}]
        m = trial._cost_measures(runs)
        self.assertEqual((m["seconds_mean"], m["commands_mean"], m["no_usage"]), (30.0, 4, 1))

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap")
    def test_confine_prefix_hides_run_but_dns_still_resolves_when_available(self):
        cmd = trial.confine_prefix(self.tmp, [])
        # asserted structurally (not by actually resolving a name, which would need real network access in
        # a test environment that may not have it): "/run" is tmpfs'd, and any resolver directory this host
        # actually has gets read back in read-only so /etc/resolv.conf's symlink target still exists.
        self.assertIn("/run", cmd)
        idx = cmd.index("/run")
        self.assertEqual(cmd[idx - 1], "--tmpfs")
        for resolver in trial._RUN_RESOLVERS:
            if resolver.is_dir():
                self.assertIn(str(resolver), cmd)

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap: proves the actual escape is closed")
    def test_confined_run_with_out_outside_home_cannot_see_sibling_runs(self):
        # With --out outside both the home and /tmp tmpfs mounts confinement already hides, a confined
        # process used to be able to list its sibling run directories and read plan.json two directories up
        # from its own job directory - the read-only "/" bind still exposed out's parent whole.
        outside = Path("/var/tmp") / f"trial-out-{os.urandom(4).hex()}"
        try:
            write(self.tmp / "scenarios" / "make-file" / "check.py",
                  "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
            plan = self._plan({"a": {"executor": "command",
                                     "command": 'ls "$TRIAL_JOB_DIR/.." > seen.txt 2>&1; '
                                                'cat "$TRIAL_JOB_DIR/../../plan.json" >> seen.txt 2>&1 || true'}})
            # This test is about confinement, not space: /var/tmp can sit near the disk-space floor on a busy host.
            with mock.patch.dict(os.environ, {"TRIAL_MIN_FREE_GB": "0"}):
                r = self.run_cli("run", plan, "--out", str(outside))
            self.assertEqual(r.returncode, 0, r.stderr)
            results = {p.parent.name: json.loads(p.read_text()) for p in outside.glob("runs/*/result.json")}
            seen = results["make-file__a__r1"]["checks"]["seen"]
            self.assertNotIn("make-file__a__r1.pending", seen)
            self.assertNotIn('"arms"', seen)  # plan.json's own content never reached the check
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_rerunning_a_claude_arm_with_no_explicit_permission_mode_is_never_refused(self):
        # Regression: run_claude records its own effective default ("bypassPermissions" confined,
        # "acceptEdits" unconfined) onto the run's identity so a rerun that would silently compare a
        # confined and an unconfined Claude arm is still caught - but the SAME default was never applied to
        # the freshly loaded plan's own arm when comparing, so identical reruns, --retry-invalid, and adding
        # --repeats were all refused with "permission_mode unset (was ...)" for any claude arm that never
        # set permission_mode explicitly itself.
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\ncat >/dev/null\necho '{\"type\": \"result\", \"result\": \"ok\"}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        claude = {"c": {"executor": "claude", "model": "m", "binary": str(fake),
                        "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}
        plan = self._plan(claude)
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        # an identical rerun into the same directory, --retry-invalid, and added --repeats all succeed
        for args in ([], ["--retry-invalid"], ["--repeats", "2"]):
            r = self.run_cli("run", plan, "--out", str(self.out), *args)
            self.assertEqual(r.returncode, 0, (args, r.stderr))
        self.assertEqual(len(self.results()), 2)
        # a real confinement change (--sandbox none, when bubblewrap is present so the two differ) IS still
        # caught - never silently allowed through under the same "no explicit permission_mode" cover.
        if shutil.which("bwrap"):
            r = self.run_cli("run", plan, "--out", str(self.out), "--sandbox", "none")
            self.assertEqual(r.returncode, 2)
            self.assertIn("permission_mode", r.stderr)
            self.assertIn("use a new --out", r.stderr)

    def test_baseline_naming_no_loaded_arm_is_an_explicit_error(self):
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        r = self.run_cli("summarize", str(self.out), "--baseline", "nope")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--baseline 'nope' does not name a loaded arm", r.stderr)
        self.assertIn("valid arms: bad, good", r.stderr)
        r = self.run_cli("report", str(self.out), "--baseline", "nope")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--baseline 'nope' does not name a loaded arm", r.stderr)
        # the plan's own stored baseline (never explicitly asked for on this call) naming no loaded arm
        # stays a silent no-op, e.g. after --arms filtered it out - not a new error
        self.assertEqual(self.run_cli("summarize", str(self.out)).returncode, 0)

    def test_report_scenario_entries_list_invalid_reasons_like_summarize_does(self):
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    raise ValueError('boom')\n")
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        payload = json.loads(self.run_cli("report", str(self.out)).stdout)
        entry = payload["scenarios"]["make-file|good"]
        self.assertEqual(entry["invalid"], ["check-error"])

    def test_judge_resources_are_validated_and_resolved_like_an_arms(self):
        write(self.tmp / "resources" / "demo-skill" / "SKILL.md", "a demo skill\n")
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        judge = {"executor": "claude", "model": "m", "resources": {"../escape": "resources/demo-skill"}}
        write(self.tmp / "plan.json", json.dumps({"name": "p", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"good": {"executor": "command", "command": "true"}},
            "judge": judge, "scenarios": ["scenarios/make-file"]}))
        with self.assertRaisesRegex(trial.TrialError, 'judge resources.*without ".."'):
            trial.load_plan(self.tmp / "plan.json", None, None, None)
        s.write_text(json.dumps(dict(json.loads(s.read_text()))))
        good_judge = {"executor": "claude", "model": "m", "resources": {"skills/demo": "resources/demo-skill"}}
        write(self.tmp / "plan.json", json.dumps({"name": "p", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"good": {"executor": "command", "command": "true"}},
            "judge": good_judge, "scenarios": ["scenarios/make-file"]}))
        plan = trial.load_plan(self.tmp / "plan.json", None, None, None)
        self.assertIn("resources_sha256", plan["judge"])
        self.assertTrue(Path(plan["judge"]["resources"]["skills/demo"]).is_absolute())

    # ------------------------------------------------------------ skill selection

    def test_stub_skills_are_deterministic_and_length_matched(self):
        spec = {"dir": ".agents/skills", "count": 35, "chars": 13900}
        stubs = trial.stub_skills(spec)
        self.assertEqual(stubs, trial.stub_skills(dict(spec)))
        self.assertEqual(len(stubs), 35)
        names = [n for n, _ in stubs]
        self.assertEqual(len(set(names)), 35)
        total = 0
        for i, (name, text) in enumerate(stubs):
            self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)+$")
            head, body = text.split("\n---\n", 1)
            fields = dict(line.split(": ", 1) for line in head.splitlines()[1:])
            self.assertEqual(fields["name"], name)
            share = 13900 // 35 + (1 if i < 13900 % 35 else 0)
            self.assertLessEqual(len(fields["description"]), share)
            self.assertGreaterEqual(len(fields["description"]), share - 20)
            self.assertNotIn(":", fields["description"])  # a plain YAML scalar every host parses alike
            total += len(fields["description"])
        self.assertGreaterEqual(total, 13900 - 35 * 20)
        self.assertNotEqual(names, [n for n, _ in trial.stub_skills(dict(spec, seed=7))])
        many = [n for n, _ in trial.stub_skills({"dir": "s", "count": 400, "chars": 400 * 40})]
        self.assertEqual(len(set(many)), 400)
        for bad, message in (({"dir": "s", "count": 10, "chars": 100}, "fewer than 40"),
                             ({"dir": "/abs", "count": 1, "chars": 100}, "relative path"),
                             ({"dir": "../up", "count": 1, "chars": 100}, "relative path"),
                             ({"dir": "s", "count": "3", "chars": 300}, "must be integers"),
                             ({"dir": "s", "count": 1, "chars": 100, "size": 2}, "must be an object")):
            with self.assertRaisesRegex(trial.TrialError, message):
                trial.stub_skills(bad)

    def test_stub_skills_and_resources_land_read_only_in_the_private_home(self):
        write(self.tmp / "resources" / "ledger" / "SKILL.md", "---\nname: ledger\ndescription: d\n---\n")
        stub = trial.stub_skills({"dir": ".agents/skills", "count": 3, "chars": 300})[0][0]
        arm = {"executor": "command", "resources": {".agents/skills/ledger": "resources/ledger"},
               "stub_skills": {"dir": ".agents/skills", "count": 3, "chars": 300},
               "command": (f'ls "$HOME/.agents/skills" > listing.txt; cat "$HOME/.agents/skills/{stub}/SKILL.md" > stub.txt; '
                           f'echo x >> "$HOME/.agents/skills/{stub}/SKILL.md" 2>/dev/null && echo writable > w.txt; true')}
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'listing': run.file('listing.txt'), 'stub': run.file('stub.txt'),\n"
              "            'writable': run.file('w.txt').strip() == 'writable'}\n")
        plan = self._plan({"k": arm})
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        checks = self.results()["make-file__k__r1"]["checks"]
        listed = checks["listing"].split()
        self.assertEqual(sorted(listed), sorted(["ledger", *[n for n, _ in trial.stub_skills(arm["stub_skills"])]]))
        self.assertTrue(checks["stub"].startswith(f"---\nname: {stub}\n"), checks)
        self.assertFalse(checks["writable"])
        digest = json.loads((self.out / "plan.json").read_text())["arms"]["k"]["resources_sha256"]
        self.assertEqual(digest, trial.load_plan(Path(plan), None, None, None)["arms"]["k"]["resources_sha256"])
        # different padding under the same arm name is a different arm: refused, like changed resources
        self._plan({"k": dict(arm, stub_skills={"dir": ".agents/skills", "count": 4, "chars": 400})})
        r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("different resources", r.stderr)
        # stubs never land inside a resource (read-only), nor a resource on a stub
        inside = {"dir": ".agents/skills/ledger", "count": 1, "chars": 100}
        on_top = {".agents/skills/" + stub: "resources/ledger"}
        for resources, stubs in (({".agents/skills/ledger": "resources/ledger"}, inside), (on_top, arm["stub_skills"])):
            self._plan({"k": dict(arm, resources=resources, stub_skills=stubs)})
            with self.assertRaisesRegex(trial.TrialError, "overlaps resources"):
                trial.load_plan(Path(plan), None, None, None)
        # read-only for the agent only: a finished run directory deletes with a plain rm -rf
        r = subprocess.run(["rm", "-rf", str(self.out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.out.exists())

    def test_each_executor_finds_skills_where_its_host_discovers_them(self):
        # Codex reads $CODEX_HOME/skills and $HOME/.agents/skills, Gemini CLI ~/.gemini/skills and ~/.agents/skills,
        # and Claude Code (without --bare) ~/.claude/skills: each inside the run's private home.
        write(self.tmp / "resources" / "demo" / "SKILL.md", "---\nname: demo\ndescription: d\n---\n")
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        reply = {"codex": "echo '{\"type\": \"thread.started\", \"thread_id\": \"T\"}'; echo '{\"type\": \"turn.completed\", \"usage\": {}}'",
                 "gemini": "echo '{\"type\": \"result\", \"stats\": {}}'",
                 "claude": "echo '{\"type\": \"result\", \"result\": \"ok\"}'"}
        where = {"codex": ('"$HOME/.agents/skills/demo/SKILL.md"', '"$CODEX_HOME/skills/demo2/SKILL.md"'),
                 "gemini": ('"$GEMINI_CLI_HOME/.gemini/skills/demo/SKILL.md"', '"$HOME/.agents/skills/demo2/SKILL.md"'),
                 "claude": ('"$HOME/.claude/skills/demo/SKILL.md"', '"$HOME/.claude/skills/demo2/SKILL.md"')}
        keys = {"codex": (".agents/skills/demo", ".codex/skills/demo2"), "gemini": (".gemini/skills/demo", ".agents/skills/demo2"),
                "claude": (".claude/skills/demo", ".claude/skills/demo2")}
        arms = {}
        for executor in ("codex", "gemini", "claude"):
            if executor == "claude" and not shutil.which("bwrap"):
                continue  # "bare": false needs confinement
            fake = self.tmp / "bin" / executor / executor
            a, b = where[executor]
            write(fake, f"#!/bin/sh\ncat >/dev/null\nif test -f {a} && test -f {b}; then echo found > seen.txt; "
                        f"else echo missing > seen.txt; fi\n{reply[executor]}\n", 0o755)
            arms[executor] = {"executor": executor, "model": "m", "binary": str(fake), "api_key_var": "TRIAL_TEST_KEY",
                              "env_file": str(env_file), "resources": {k: "resources/demo" for k in keys[executor]}}
        arms.get("claude", {})["bare"] = False
        if not shutil.which("bwrap"):
            arms["gemini"]["approval_mode"] = "yolo"  # unconfined, auto_edit is refused for placed skills; the fake binary runs nothing
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
        r = self.run_cli("run", self._plan({k: v for k, v in arms.items() if v}), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        for executor in arms:
            result = self.results()[f"make-file__{executor}__r1"]
            self.assertEqual(result["status"], "ok", result)
            self.assertEqual(result["checks"]["seen"], "found", executor)

    @unittest.skipUnless(shutil.which("bwrap"), "\"bare\": false runs only confined")
    def test_claude_bare_false_runs_without_bare_and_keeps_key_auth(self):
        fake = self.tmp / "bin" / "claude"
        write(fake, "#!/bin/sh\nprintf '%s\\n' \"$@\" > argv.txt\n"
                    "[ -n \"$ANTHROPIC_API_KEY\" ] && echo set > key.txt\n"
                    "printf '%s' \"${CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL:-unset}\" > market.txt\n"
                    "cat >/dev/null\necho '{\"type\": \"result\", \"result\": \"ok\"}'\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        base = {"executor": "claude", "model": "m", "binary": str(fake), "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'argv': run.file('argv.txt'), 'key': run.file('key.txt').strip(),\n"
              "            'market': run.file('market.txt')}\n")
        plan = self._plan({"open": dict(base, bare=False), "default": dict(base)})
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()
        open_run, default_run = res["make-file__open__r1"], res["make-file__default__r1"]
        self.assertNotIn("--bare", open_run["checks"]["argv"].split())
        self.assertIn("--bare", default_run["checks"]["argv"].split())
        for run in (open_run, default_run):
            self.assertEqual(run["checks"]["key"], "set")
            self.assertEqual(run["checks"]["argv"].split()[:1], ["-p"])
            self.assertIn("stream-json", run["checks"]["argv"].split())
        self.assertEqual(open_run["checks"]["market"], "1")
        self.assertEqual(default_run["checks"]["market"], "unset")
        self.assertIs(open_run["identity"]["bare"], False)
        self.assertNotIn("bare", default_run["identity"])  # the default records nothing new
        # the same arm name switching between bare and not is a different arm
        self._plan({"open": dict(base), "default": dict(base, bare=True)})
        r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("bare True (was False)", r.stderr)
        self._plan({"open": dict(base, bare=False), "default": dict(base, bare=True)})
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)

    def test_bare_is_validated_and_refused_unconfined(self):
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        claude = {"executor": "claude", "model": "m", "binary": "/bin/true", "api_key_var": "TRIAL_TEST_KEY",
                  "env_file": str(env_file)}
        for arm, message in ((dict(claude, bare="no"), "must be true or false"),
                             ({"executor": "codex", "model": "m", "bare": False}, "only a claude arm reads"),
                             (dict(claude, bare=False, copy_auth=True), "copied claude.ai login")):
            with self.assertRaisesRegex(trial.TrialError, message):
                trial.load_plan(Path(self._plan({"a": arm})), None, None, None)
        with self.assertRaisesRegex(trial.TrialError, "always runs with --bare"):
            trial.load_plan(Path(self._plan({"a": dict(claude)}, judge=dict(claude, bare=False))), None, None, None)
        r = self.run_cli("run", self._plan({"a": dict(claude, bare=False)}), "--out", str(self.out), "--sandbox", "none")
        self.assertEqual(r.returncode, 2)
        self.assertIn("arm 'a' on scenario 'make-file' sets \"bare\": false but would run unconfined", r.stderr)
        self.assertFalse(self.out.exists())  # refused before anything was scheduled
        # an --out outside the home and /tmp leaves the directories above the run visible: refused, dry run included
        outside = Path("/var/tmp") / f"trial-out-{os.urandom(4).hex()}"
        for extra in ([], ["--dry-run"]):
            r = self.run_cli("run", self._plan({"a": dict(claude, bare=False)}), "--out", str(outside), *extra)
            self.assertEqual(r.returncode, 2, extra)
            if shutil.which("bwrap"):
                self.assertIn(f"the run directory {outside} is outside your home and /tmp", r.stderr)
            else:  # without bubblewrap the run would be unconfined, which is refused first
                self.assertIn("sets \"bare\": false but would run unconfined", r.stderr)
            self.assertFalse(outside.exists())
        self.assertEqual(self.run_cli("run", self._plan({"a": dict(claude)}), "--out", str(outside), "--dry-run").returncode, 0)

    def test_discovery_hides_the_directories_above_the_home(self):
        home = (self.tmp / "parent" / "user").resolve()
        topmost = home.parents[len(home.parents) - 2]  # the child of "/" on the home's path
        with mock.patch.object(Path, "home", classmethod(lambda cls: home)):
            self.assertEqual(trial._discovery_hide(home / ".cache" / "agent-trials" / "p"), [topmost])
            self.assertEqual(trial._discovery_hide(Path("/tmp") / "x" / "p"), [])
            with self.assertRaisesRegex(trial.TrialError, "outside your home and /tmp"):
                trial._discovery_hide(Path("/var/tmp") / "p")
        with mock.patch.object(Path, "home", classmethod(lambda cls: Path("/root"))):  # a home right under "/"
            self.assertEqual(trial._discovery_hide(Path("/root/.cache/p")), [])

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap to prove the directories above the run are hidden")
    def test_claude_without_bare_never_sees_instructions_above_the_run(self):
        # Claude Code without --bare reads CLAUDE.md, CLAUDE.local.md, and .claude/ in every directory from its
        # working directory up to "/"; a home under /var/tmp stands in for one under /home, whose parent the
        # read-only "/" bind would otherwise expose.
        try:
            parent = Path(tempfile.mkdtemp(prefix="trial-test-above-", dir="/var/tmp"))
        except OSError:
            self.skipTest("needs a writable /var/tmp")
        try:
            home = parent / "home" / "user"
            home.mkdir(parents=True)
            write(parent / "CLAUDE.md", "planted\n")
            write(parent / "home" / ".claude" / "rules" / "r.md", "planted\n")
            fake = self.tmp / "bin" / "claude"
            write(fake, "#!/bin/sh\ncat >/dev/null\nd=$PWD; : > seen.txt\nwhile [ \"$d\" != / ]; do\n"
                        "  for f in CLAUDE.md CLAUDE.local.md .claude; do [ -e \"$d/$f\" ] && echo \"$d/$f\" >> seen.txt; done\n"
                        "  d=$(dirname \"$d\"); done\necho '{\"type\": \"result\", \"result\": \"ok\"}'\n", 0o755)
            env_file = self.tmp / "keys.env"
            env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
            base = {"executor": "claude", "model": "m", "binary": str(fake), "api_key_var": "TRIAL_TEST_KEY",
                    "env_file": str(env_file)}
            write(self.tmp / "scenarios" / "make-file" / "check.py",
                  "def check(run):\n    return {'seen': run.file('seen.txt').split()}\n")
            out = home / ".cache" / "agent-trials" / "p"
            with mock.patch.object(Path, "home", classmethod(lambda cls: home)), mock.patch.object(trial, "MIN_FREE_BYTES", 0):
                code = trial.main(["run", self._plan({"open": dict(base, bare=False), "default": base}), "--out", str(out)])
            self.assertEqual(code, 0)
            results = {p.parent.name: json.loads(p.read_text()) for p in out.glob("runs/*/result.json")}
            self.assertEqual(results["make-file__open__r1"]["checks"]["seen"], [])
            # --bare reads none of them, so its confinement is unchanged and still shows them
            self.assertIn(str(parent / "CLAUDE.md"), results["make-file__default__r1"]["checks"]["seen"])
        finally:
            subprocess.run(["chmod", "-R", "u+rwx", str(parent)], capture_output=True)
            shutil.rmtree(parent, ignore_errors=True)

    def test_gemini_arm_placing_skills_is_refused_outside_yolo(self):
        write(self.tmp / "resources" / "demo" / "SKILL.md", "---\nname: demo\ndescription: d\n---\n")
        gem = {"executor": "gemini", "model": "m", "resources": {".agents/skills/demo": "resources/demo"}}
        r = self.run_cli("run", self._plan({"g": gem}), "--sandbox", "none", "--dry-run")
        self.assertEqual(r.returncode, 2)
        self.assertIn("arm 'g' on scenario 'make-file' places skills where Gemini CLI discovers them, but resolves to "
                      "approval_mode \"auto_edit\"", r.stderr)
        for arm in (dict(gem, approval_mode="default"), {"executor": "gemini", "model": "m", "approval_mode": "plan",
                                                         "stub_skills": {"dir": ".gemini/skills", "count": 1, "chars": 100}}):
            r = self.run_cli("run", self._plan({"g": arm}), "--sandbox", "confined", "--dry-run")
            self.assertEqual(r.returncode, 2, arm)
            self.assertIn("headless policy denies activate_skill", r.stderr)
        for arm, extra in ((dict(gem, approval_mode="yolo"), ["--sandbox", "none"]),  # an explicit choice
                           (gem, ["--sandbox", "confined"]),  # confined: "yolo" by default
                           (dict(gem, resources={"notes/demo": "resources/demo"}), ["--sandbox", "none"])):  # no skill placed
            r = self.run_cli("run", self._plan({"g": arm}), *extra, "--dry-run")
            self.assertEqual(r.returncode, 0, (arm, r.stderr))

    def test_resources_are_frozen_when_the_trial_starts(self):
        write(self.tmp / "resources" / "demo" / "SKILL.md", "first\n")
        write(self.tmp / "resources" / "note.txt", "note\n")
        arm = {"executor": "command", "command": "true",
               "resources": {".agents/skills/demo": "resources/demo", "notes/note.txt": "resources/note.txt"}}
        plan = trial.load_plan(Path(self._plan({"k": arm})), None, None, None)
        self.out.mkdir()
        trial._snapshot_resources(plan, self.out)
        frozen = plan["arms"]["k"]["resources"]
        self.assertTrue(all(Path(p).is_relative_to(self.out / "resources") for p in frozen.values()), frozen)
        self.assertEqual(plan["arms"]["k"]["resources_source"][".agents/skills/demo"], str(self.tmp / "resources" / "demo"))
        write(self.tmp / "resources" / "demo" / "SKILL.md", "edited during the trial\n")
        job = self.out / "runs" / "j"
        (job / "work").mkdir(parents=True)
        (job / "harness").mkdir()
        env = trial.isolated_env(job, self.out, {"dir": str(self.tmp / "scenarios" / "make-file")}, plan["arms"]["k"])
        self.assertEqual((Path(env["HOME"]) / ".agents" / "skills" / "demo" / "SKILL.md").read_text(), "first\n")
        self.assertEqual((Path(env["HOME"]) / "notes" / "note.txt").read_text(), "note\n")
        # a source that changed between loading the plan and freezing it is refused, never frozen under the old digest
        plan = trial.load_plan(Path(self._plan({"k": arm})), None, None, None)
        write(self.tmp / "resources" / "demo" / "SKILL.md", "edited again\n")
        with self.assertRaisesRegex(trial.TrialError, "arm 'k' resources changed after the plan was loaded"):
            trial._snapshot_resources(plan, self.out)

    def test_confine_prefix_hides_named_host_directories(self):
        present = self.tmp / "managed"
        present.mkdir()
        with mock.patch("trial.shutil.which", return_value="/usr/bin/bwrap"):
            cmd = trial.confine_prefix(self.tmp, [], hide=[present, self.tmp / "absent"])
        self.assertIn(["--tmpfs", str(present)], [cmd[i:i + 2] for i in range(len(cmd) - 1)])
        self.assertNotIn(str(self.tmp / "absent"), cmd)

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap to prove the managed directory is hidden")
    def test_claude_without_bare_never_sees_host_managed_settings(self):
        try:  # outside the home and /tmp, which confinement hides anyway
            host = Path(tempfile.mkdtemp(prefix="trial-test-managed-", dir="/var/tmp"))
        except OSError:
            self.skipTest("needs a writable /var/tmp")
        try:
            write(host / "claude-code" / "managed-settings.json", "{}\n")
            fake = self.tmp / "bin" / "claude"
            write(fake, f"#!/bin/sh\ncat >/dev/null\ntest -f {host}/claude-code/managed-settings.json && echo seen > seen.txt "
                        "|| echo hidden > seen.txt\necho '{\"type\": \"result\", \"result\": \"ok\"}'\n", 0o755)
            env_file = self.tmp / "keys.env"
            env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
            base = {"executor": "claude", "model": "m", "binary": str(fake), "api_key_var": "TRIAL_TEST_KEY",
                    "env_file": str(env_file)}
            write(self.tmp / "scenarios" / "make-file" / "check.py",
                  "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
            with mock.patch.object(trial, "CLAUDE_MANAGED_DIRS", (host / "claude-code",)):
                code = trial.main(["run", self._plan({"open": dict(base, bare=False), "default": base}), "--out", str(self.out)])
            self.assertEqual(code, 0)
            self.assertEqual(self.results()["make-file__open__r1"]["checks"]["seen"], "hidden")
            self.assertEqual(self.results()["make-file__default__r1"]["checks"]["seen"], "seen")  # --bare: unchanged
        finally:
            shutil.rmtree(host, ignore_errors=True)

    def _synthetic_run(self, events, rollout=None):
        job = Path(tempfile.mkdtemp(prefix="job-", dir=self.tmp))
        (job / "work").mkdir()
        write(job / "events.jsonl", "".join(json.dumps(e) + "\n" for e in events))
        if rollout is not None:
            write(job / "harness" / "home" / ".codex" / "sessions" / "2026" / "10" / "01" / "rollout-x.jsonl",
                  "".join(json.dumps(e) + "\n" for e in rollout))
        return trial.Run(job, "ok")

    def test_skills_loaded_from_a_codex_record(self):
        def cmd(command, code=0, output=""):
            return {"type": "item.completed", "item": {"type": "command_execution", "command": command,
                                                       "aggregated_output": output, "exit_code": code}}

        def fm(name):
            return f"---\nname: {name}\ndescription: d\n---\n\n# Body\n"
        events = [
            cmd("/usr/bin/zsh -lc \"sed -n '1,200p' ~/.agents/skills/ledger/SKILL.md\"", output=fm("ledger")),
            cmd("cat ~/.agents/skills/*/SKILL.md", output=fm("glob-a") + fm("glob-b")),
            cmd("find ~/.agents/skills/found -name SKILL.md -exec cat {} +", output=fm("found")),
            cmd("echo ~/.agents/skills/xargs-one/SKILL.md | xargs cat", output=fm("xargs-one")),
            cmd("printf '%s\\n' \"$(cat ~/.agents/skills/subst-one/SKILL.md)\"", output=fm("subst-one")),
            cmd("pushd ~/.agents/skills/pushed && cat SKILL.md", output=fm("pushed")),
            cmd("cat -n skills/numbered/SKILL.md", output="     1\t---\n     2\tname: numbered\n     3\tdescription: d\n"),
            cmd("cat skills/partial/SKILL.md && rg -n x .", code=1, output=fm("partial")),
            # named without being read: listings, a write, a commit, a patch, a comment, a failed alias, an echo
            cmd("rg --files -g 'AGENTS.md' -g 'SKILL.md' ~/.agents/skills",
                output="/h/.agents/skills/listed-a/SKILL.md\n/h/.agents/skills/listed-b/SKILL.md\n"),
            cmd("rg --files ~/.agents/skills | grep SKILL.md", output="/h/.agents/skills/listed-c/SKILL.md\n"),
            cmd("fd SKILL.md ~/.agents/skills", output="/h/.agents/skills/listed-d/SKILL.md\n"),
            cmd("cat > skills/written/SKILL.md <<'EOF'\n---\nname: written\ndescription: d\n---\nEOF"),
            cmd("git add skills/committed/SKILL.md && git commit -m x", output="[main 1a2b3c4] x\n 1 file changed\n"),
            cmd("apply_patch <<'P'\n*** Begin Patch\n*** Add File: skills/patched/SKILL.md\n+---\n+name: patched\n*** End Patch\nP",
                output="Success. Updated the following files:\nA skills/patched/SKILL.md\n"),
            cmd("cat notes.txt  # format per commented/SKILL.md", output="notes\n"),
            cmd("cat r1/aliased/SKILL.md || true", output="cat: r1/aliased/SKILL.md: No such file or directory\n"),
            cmd("echo see r0/printed/SKILL.md", output="see r0/printed/SKILL.md\n"),
            cmd("cat /nowhere/missing/SKILL.md", code=1, output="cat: No such file or directory"),
            {"type": "item.completed", "item": {"type": "agent_message", "text": "read ~/.agents/skills/said/SKILL.md"}}]
        rollout = [
            {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": (
                "<skills_instructions>\n## Skills\n### Skill roots\n- `r0` = `/h/.agents/skills`\n### Available skills\n"
                "- ledger: Convert notes. (file: r0/ledger/SKILL.md)\n- quiet-one: Unused. (file: r0/quiet-one/SKILL.md)\n"
                "- bare-one (file: r0/bare-one/SKILL.md)\n- Discovery: the list above\n</skills_instructions>")}]}},
            # a cd in the same command: Codex parses a bare SKILL.md read; its output shows which skill it was
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {
                "type": "CommandExecution", "command": ["/usr/bin/zsh", "-lc", "cd ~/.agents/skills/cwd-one && cat SKILL.md"],
                "cwd": "file:///h/runs/j/work", "parsed_cmd": [{"type": "read", "path": "SKILL.md"}],
                "exit_code": 0, "aggregated_output": fm("cwd-one")}}},
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {
                "type": "CommandExecution", "command": ["/usr/bin/zsh", "-lc", "rg --files -g SKILL.md"],
                "cwd": "file:///h/runs/j/work", "parsed_cmd": [{"type": "read", "path": "SKILL.md"}],
                "exit_code": 0, "aggregated_output": "skills/x/SKILL.md\n"}}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text",
                "text": "<skill>\n<name>mentioned-one</name>\n<path>/h/.agents/skills/mentioned-one/SKILL.md</path>\nbody\n</skill>"}]}},
        ]
        run = self._synthetic_run(events, rollout)
        loaded = run.skills_loaded()
        self.assertEqual(sorted(loaded), ["cwd-one", "found", "glob-a", "glob-b", "ledger", "mentioned-one", "numbered",
                                          "partial", "pushed", "subst-one", "xargs-one"])
        self.assertNotIn("work", loaded)  # never the working directory's own name
        self.assertTrue(run.skill_loaded("ledger"))
        self.assertFalse(run.skill_loaded("quiet-one"))
        self.assertIn("ledger/SKILL.md", loaded["ledger"][0])
        self.assertEqual(run.skills_listed(), {"ledger": "Convert notes.", "quiet-one": "Unused.", "bare-one": ""})

    def test_skills_loaded_from_a_claude_record(self):
        def use(i, name, inp):
            return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": i, "name": name, "input": inp}]}}

        def result(i, error=False, text="ok"):
            return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "is_error": error,
                                                              "content": [{"type": "text", "text": text}]}]}}
        events = [{"type": "system", "subtype": "init", "skills": ["ledger", "registered-only"]},
                  use("1", "Skill", {"skill": "ledger"}), result("1", text="Launching skill: ledger"),
                  use("2", "Skill", {"skill": "tools:helper"}), result("2"),
                  use("3", "Read", {"file_path": "/h/.claude/skills/read-one/SKILL.md", "offset": 20}), result("3", text="20\tstep"),
                  use("4", "Bash", {"command": "cd ~/.claude/skills/bash-one"}), result("4", text=""),
                  use("5", "Bash", {"command": "cat SKILL.md"}), result("5", text="---\nname: bash-one\ndescription: d\n---\n"),
                  use("6", "Read", {"file_path": "/h/.claude/skills/gone/SKILL.md"}), result("6", error=True, text="File does not exist."),
                  use("7", "Write", {"file_path": "/h/.claude/skills/written/SKILL.md", "content": "---\nname: written\n---\n"}),
                  result("7", text="File created successfully"),
                  use("8", "Edit", {"file_path": "/h/skills/edited/SKILL.md", "old_string": "a", "new_string": "b"}),
                  result("8", text="The file has been updated. Here's a snippet:\n     1\t---\n     2\tname: edited\n"),
                  use("9", "Grep", {"pattern": "Ledger", "path": "/h/.claude/skills", "output_mode": "content"}),
                  result("9", text="/h/.claude/skills/grepped/SKILL.md:5:Ledger lines"),
                  {"type": "assistant", "message": {"content": [{"type": "text", "text": "see ~/.claude/skills/said/SKILL.md"}]}}]
        run = self._synthetic_run(events)
        self.assertEqual(sorted(run.skills_loaded()), ["bash-one", "helper", "ledger", "read-one"])
        self.assertEqual(run.skills_loaded()["helper"], ["Skill: tools:helper"])
        self.assertEqual(run.skills_loaded()["bash-one"], ["Bash: cat SKILL.md"])
        self.assertIsNone(run.skills_listed())  # the init event names registered skills, not the listing
        # the listing Claude Code sent the model is in its session transcript, in the run's private home
        transcript = run.harness / "home" / ".claude" / "projects" / "-h-work" / "s.jsonl"
        write(transcript, "".join(json.dumps(r) + "\n" for r in [
            {"type": "user", "message": {"role": "user", "content": "go"}},
            {"type": "attachment", "attachment": {"type": "skill_listing", "isInitial": True, "names": ["ledger", "quiet-one", "plug:helper"],
                                                  "content": "- ledger: Convert notes.\n- quiet-one\n- plug:helper: Helps: a lot."}}]))
        self.assertEqual(run.skills_listed(), {"ledger": "Convert notes.", "quiet-one": "", "plug:helper": "Helps: a lot."})

    def test_skills_loaded_from_a_gemini_record(self):
        def use(i, name, params):
            return {"type": "tool_use", "tool_name": name, "tool_id": i, "parameters": params}

        def res(i, status="success", output=""):
            return {"type": "tool_result", "tool_id": i, "status": status, "output": output}
        events = [{"type": "init", "session_id": "s", "model": "m"},
                  use("1", "activate_skill", {"name": "ledger"}), res("1"),
                  use("2", "read_file", {"file_path": "/h/.gemini/skills/read-one/SKILL.md"}), res("2"),
                  use("3", "read_many_files", {"include": ["notes.txt", "/h/.agents/skills/many-one/SKILL.md"]}),
                  use("4", "run_shell_command", {"command": "cat SKILL.md", "dir_path": "/h/.gemini/skills/shell-one"}),
                  res("4", output="---\nname: shell-one\ndescription: d\n---\n"),
                  use("5", "activate_skill", {"name": "denied-one"}),
                  {"type": "tool_result", "tool_id": "5", "status": "error", "error": {"type": "x", "message": "denied"}},
                  use("6", "write_file", {"file_path": "/h/skills/new-one/SKILL.md", "content": "---\nname: new-one\n---\n"}),
                  res("6", output="---\nname: new-one\n---\n"),
                  use("7", "run_shell_command", {"command": "ls ~/.gemini/skills/*/SKILL.md"}),
                  res("7", output="/h/.gemini/skills/listed/SKILL.md\n"),
                  {"type": "message", "role": "assistant", "content": "I could read ~/.gemini/skills/said/SKILL.md", "delta": True}]
        run = self._synthetic_run(events)
        self.assertEqual(sorted(run.skills_loaded()), ["ledger", "many-one", "read-one", "shell-one"])
        self.assertIsNone(run.skills_listed())  # Gemini's stream-json does not show the listing

    def test_frontmatter_names_reads_only_a_frontmatter_block(self):
        self.assertEqual(trial._frontmatter_names("---\ndescription: d\nname: 'quoted-one'\n---\nname: body-line\n"), {"quoted-one"})
        self.assertEqual(trial._frontmatter_names("name: no-fence\n"), set())
        self.assertEqual(trial._frontmatter_names("---\n  name: indented\n---\n"), set())
        self.assertEqual(trial._frontmatter_names("     1→---\n     2→name: arrowed\n"), {"arrowed"})
        self.assertEqual(trial._frontmatter_names("---\n" + "k: v\n" * 70 + "name: too-far\n"), set())


if __name__ == "__main__":
    unittest.main()
