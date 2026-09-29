"""Behavior of the trial runner, exercised with the deterministic command executor."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
            "name": "unit", "repeats": 2, "seed": 3,
            "arms": {"good": {"executor": "command", "command": 'echo hi > out.txt; faketool x; printf "%s" "$TRIAL_PROMPT" > prompt.txt'},
                     "bad": {"executor": "command", "command": "true"}},
            "scenarios": ["scenarios/make-file"]}))
        self.out = self.tmp / "out"

    def tearDown(self):
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def results(self):
        return {p.parent.name: json.loads(p.read_text()) for p in (self.out / "runs").glob("*/result.json")}

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

    def test_isolated_environment_hides_user_paths_and_scenario_location(self):
        write(self.tmp / "scenarios" / "make-file" / "check.py", (
            "def check(run):\n"
            "    env = dict(l.split('=', 1) for l in run.file('env.txt').splitlines() if '=' in l)\n"
            "    return {'fake_home': env.get('HOME', '').endswith('/harness/home'),\n"
            "            'no_user_bin': '/usr/local/bin' not in env.get('PATH', '') and '.local/bin' not in env.get('PATH', ''),\n"
            "            'tools_copied': env.get('PATH', '').split(':')[0].endswith('/tools'),\n"
            "            'no_ssh_agent': 'SSH_AUTH_SOCK' not in env,\n"
            "            'private_git': env.get('GIT_CONFIG_GLOBAL', '').endswith('/harness/.gitconfig')}\n"))
        write(self.tmp / "plan.json", json.dumps({"name": "env", "repeats": 1, "arms": {"a": {"executor": "command", "command": "env > env.txt"}},
                                                  "scenarios": ["scenarios/make-file"]}))
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        checks = self.results()["make-file__a__r1"]["checks"]
        self.assertTrue(all(checks.values()), checks)

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
        out2 = self.tmp / "out2"
        self.run_cli("run", str(plan), "--out", str(out2))
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
        write(self.tmp / "plan.json", json.dumps({"name": "claude", "repeats": 1, "scenarios": ["scenarios/make-file"],
            "arms": {"c": {"executor": "claude", "model": "m", "binary": str(fake), "base_url": "http://proxy.invalid",
                           "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()["make-file__c__r1"]
        self.assertEqual(res["checks"]["seen"], "http://proxy.invalid set")
        self.assertEqual(res["checks"]["final"], "all done")
        self.assertEqual(res["usage"].get("output_tokens"), 3)

    def test_wilson_interval_bounds(self):
        lo, hi = trial.wilson(5, 5)
        self.assertAlmostEqual(lo, 0.566, places=2)
        self.assertEqual(hi, 1.0)
        self.assertEqual(trial.wilson(0, 0), (0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
