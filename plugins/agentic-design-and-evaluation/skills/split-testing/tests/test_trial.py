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


# A launcher for a pretend agent (see its docstring), used where a test needs an arm that passes the probe.
FAKE_LAUNCHER = Path(__file__).with_name("fake_launcher.py")
# A launcher for a pretend judge: it hands the prompt to the judge's executable, which answers on standard output.
JUDGE_LAUNCHER = '#!/bin/sh\n[ "$TRIAL_TURN" = 0 ] && exit 0\nexec "$TRIAL_BINARY" < "$TRIAL_PROMPT_FILE"\n'
# What a pretend judge answers the probe's arithmetic with, so that it qualifies (see trial._probe_judge).
PROBE_ANSWERS = ("case \"$prompt\" in *'sum of 2 and 3'*) case \"$prompt\" in *' is 5.'*) echo '{\"verdict\": \"pass\", \"reason\": \"5\"}' ;;"
                 " *) echo '{\"verdict\": \"fail\", \"reason\": \"not 5\"}' ;; esac; exit 0 ;; esac\n")


def launcher_judge(where: Path, name: str, answer: str, **settings) -> dict:
    """A launcher judge, model `name`, on a pretend executable installed in `where` (apart from the plan's directory,
    which confinement hides, as a real executable would be). It answers the probe's arithmetic correctly and
    everything else with `answer`: shell that can read the prompt in $prompt and prints the verdict."""
    write(where / "judge-launcher.sh", JUDGE_LAUNCHER, 0o755)
    write(where / name, "#!/bin/sh\nprompt=$(cat)\n" + PROBE_ANSWERS + answer, 0o755)
    return dict({"executor": "launcher", "script": str(where / "judge-launcher.sh"), "binary": str(where / name), "model": name,
                 "script_sha256": hashlib.sha256(JUDGE_LAUNCHER.encode()).hexdigest()}, **settings)


class LatestModelTest(unittest.TestCase):
    def test_the_newest_version_in_a_list_compares_each_version_number_numerically(self):
        with self.assertRaises(trial.TrialError):
            trial.resolve_arm({"executor": "launcher", "model": "latest:gpt-*-sol"}, "arm")
        self.assertEqual(trial.resolve_arm({"executor": "host", "model": "latest:anything"}, "arm")["model"], "latest:anything")
        ids = ["gpt-6-sol", "gpt-6.1-sol", "gpt-6.9-sol", "gpt-6.10-sol", "gpt-6.10-sol-mini", "gpt-6-luna"]
        self.assertEqual(trial.latest_model("gpt-*-sol", ids), "gpt-6.10-sol")
        self.assertEqual(trial.latest_model("gpt-*-sol", ["gpt-6-sol", "gpt-6.1-sol"]), "gpt-6.1-sol")
        self.assertEqual(trial.latest_model("gpt-*-sol", ["gpt-7-sol", "gpt-6.12-sol"]), "gpt-7-sol")
        self.assertEqual(trial.latest_model("claude-sonnet-*", ["claude-sonnet-5", "claude-sonnet-5-5", "claude-sonnet-4-6"]), "claude-sonnet-5-5")


class TrialRunnerTest(unittest.TestCase):
    def setUp(self):
        # Confinement needs bubblewrap; a host without it (macOS, or Linux missing the package) runs every
        # plain command-arm test unconfined instead of refusing outright. Tests specific to confinement
        # itself are separately @unittest.skipUnless(shutil.which("bwrap"), ...).
        self.default_sandbox = "confined" if shutil.which("bwrap") else "none"
        self.tmp = Path(tempfile.mkdtemp(prefix="trial-test-", dir=Path.home() / ".cache"))
        self.judges = Path(tempfile.mkdtemp(prefix="trial-judges-", dir=Path.home() / ".cache"))  # apart from the plan
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
        subprocess.run(["rm", "-rf", str(self.tmp), str(self.judges)])

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

    def test_a_timeout_fails_only_a_scenario_that_tests_ending(self):
        for name, fails in (("must-end", True), ("may-end", False)):
            spec = {"prompt": "work", "required": ["made_file"], "timeout_s": 2}
            if fails:
                spec["timeout_fails"] = True
            write(self.tmp / "scenarios" / name / "scenario.json", json.dumps(spec))
            write(self.tmp / "scenarios" / name / "check.py",
                  "def check(run):\n    return {'made_file': run.file('out.txt').strip() == 'hi'}\n")
        write(self.tmp / "plan.json", json.dumps({
            "name": "endings", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"slow": {"executor": "command", "command": "sleep 30; echo hi > out.txt"}},
            "scenarios": ["scenarios/must-end", "scenarios/may-end"]}))
        for cmd in (("run", str(self.tmp / "plan.json"), "--out", str(self.out)), ("recheck", str(self.out))):
            r = self.run_cli(*cmd)
            self.assertEqual(r.returncode, 0, r.stderr)
            res = self.results()
            self.assertEqual(res["must-end__slow__r1"]["status"], "timeout", cmd[0])
            self.assertIs(res["must-end__slow__r1"]["passed"], False, cmd[0])
            self.assertIsNone(res["may-end__slow__r1"]["passed"], cmd[0])

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
        self.assertTrue(self.stored_cell("make-file", "bad").startswith("0/1 "))
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    return {'made_file': True, 'tool_called': True}\n")
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.results()["make-file__bad__r1"]["passed"])
        self.assertIn("rechecked 2 runs", r.stdout)
        # The stored summary follows the rescored results, not the run that first wrote it.
        self.assertTrue(self.stored_cell("make-file", "bad").startswith("1/1 "))

    def stored_cell(self, scenario, arm):
        """The passed / valid cell of summary.md's scenario table for a scenario and an arm."""
        lines = (self.out / "summary.md").read_text().splitlines()
        header = next(line for line in lines if line.startswith("| Scenario |"))
        row = next(line for line in lines if line.startswith(f"| {scenario} |"))
        cells = dict(zip([c.strip() for c in header.split("|")[1:-1]], [c.strip() for c in row.split("|")[1:-1]]))
        return cells[arm]

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


    # --- Between-turn reseed must never follow a link an agent's own turn planted (HIGH, confirmed) -----

    def test_recheck_with_another_judge_replaces_verdicts(self):
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        # The plan names no judge yet: a judge question under a judge-less plan is invalid, never a silent pass.
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1")
        first = self.results()["make-file__good__r1"]
        self.assertIsNone(first["passed"])
        self.assertTrue(first["judge_missing"])
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        judge = launcher_judge(self.judges, "m2", (  # it answers only when given its key and its endpoint
            'eval "key=\\${$TRIAL_API_KEY_VAR}"\n[ -n "$key" ] && [ "$TRIAL_BASE_URL" = http://proxy.invalid ] || exit 3\n'
            "echo '{\"verdict\": \"fail\", \"reason\": \"no\"}'\n"),
            base_url="http://proxy.invalid", api_key_var="TRIAL_TEST_KEY", env_file=str(env_file))
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
        git = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")  # no signing or hooks of this host's
        subprocess.run(["git", "init", "-q", str(repo)], check=True, env=git)
        subprocess.run(["git", "-C", str(repo), "config", "diff.external", "sh -c 'exit 1'"], check=True, env=git)
        (repo / "f").write_text("one\n")
        subprocess.run(["git", "-C", str(repo), "add", "f"], check=True, env=git)
        run = trial.Run(job, "ok", unconfined=not shutil.which("bwrap"))
        self.assertEqual(run.git_rc("diff", "--cached"), 0)
        self.assertIn("+one", run.git("diff", "--cached"))
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=a", "-c", "user.email=a@a.com",
                       "commit", "-q", "-m", "one"], check=True, env=git)
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
        (victims / "record.json").write_text('{"finished": true, "actions": [{"kind": "message", "text": "HOST-SECRET"}]}')
        (victims / "secret.txt").write_text("HOST-SECRET")
        (victims / "artifact.md").write_text("HOST-SECRET")
        state = lambda: sorted((str(p.relative_to(victims)), p.read_bytes() if p.is_file() else None) for p in victims.rglob("*"))
        before = state()
        s = self.tmp / "scenarios" / "make-file"
        # once its record is written, the pretend agent leaves a FIFO where the check reads and links from its run's own
        # files into the victims (see fake_launcher.py); this test also recheck --rejudge's, which needs the judge to run
        # unconfined on a host without bubblewrap: only the literal "none" does that.
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": [],
                                               "sandbox": "confined" if shutil.which("bwrap") else "none",
                                               "judge": {"question": "q?", "pass_when": "it passes"}}))
        write(s / "check.py", "def check(run):\n    return {'final': run.final_message, 'out': run.file('out.txt')}\n")
        arm = {"executor": "launcher", "script": str(FAKE_LAUNCHER), "model": "pretend-1",
               "pass_env": ["FAKE_LAUNCHER_MODE", "FAKE_LAUNCHER_DECOY"]}
        judge = launcher_judge(self.judges, "j", "echo '{\"verdict\": \"pass\", \"reason\": \"ok\"}'\n")
        with mock.patch.dict(os.environ, FAKE_LAUNCHER_MODE="plant-links", FAKE_LAUNCHER_DECOY=str(victims)):
            r = self.run_cli("run", self._plan({"c": arm}, judge), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        first = self.results()["make-file__c__r1"]
        self.assertEqual((first["status"], first["judge"]["verdict"]), ("ok", "pass"))  # judged, so a re-judge asks again
        self.assertTrue(stat.S_ISFIFO(os.lstat(self.out / "runs" / "make-file__c__r1" / "work" / "out.txt").st_mode))
        self.assertNotIn("HOST-SECRET", json.dumps(first))
        self.assertEqual(state(), before)
        self.assertEqual(self.run_cli("recheck", str(self.out), "--rejudge").returncode, 0)
        self.assertNotEqual(self.results()["make-file__c__r1"]["judge_cell"], first["judge_cell"])  # a new judge cell
        self.assertEqual(state(), before)
        # a record put behind a link is never read: the run has no record, never the victim's
        out = self.tmp / "out-link-record"
        with mock.patch.dict(os.environ, FAKE_LAUNCHER_MODE="link-record", FAKE_LAUNCHER_DECOY=str(victims)):
            r = self.run_cli("run", self._plan({"c": arm}, judge), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        linked = json.loads((out / "runs" / "make-file__c__r1" / "result.json").read_text())
        self.assertNotEqual(linked["status"], "ok")
        self.assertNotIn("HOST-SECRET", json.dumps(linked))
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

    def test_only_a_launchers_exit_75_is_retried(self):
        attempts = self.judges / "attempts.txt"  # apart from the run, which a fresh attempt would replace
        self._plan({"k": {"executor": "command", "command": f"echo once >> '{attempts}'; exit 75", "confine": False}})
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(attempts.read_text(), "once\n")  # a command's 75 is its own exit status, not a transient failure
        self.assertEqual(self.results()["make-file__k__r1"]["status"], "exit-75")

    def test_report_shows_every_setting_a_run_directory_recorded_but_this_machines_plumbing(self):
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1").returncode, 0)
        stored = json.loads((self.out / "plan.json").read_text())
        # a directory written by an older runtime holds settings of executors this one no longer has
        stored["arms"]["good"].update(permission_mode="acceptEdits", allowed_tools=["Bash"], bare=False,
                                      env_file="/somewhere/keys.env", binary="/usr/local/bin/agent")
        (self.out / "plan.json").write_text(json.dumps(stored))
        arm = trial.report(self.out)["plan"]["arms"]["good"]
        self.assertEqual((arm["permission_mode"], arm["allowed_tools"], arm["bare"]), ("acceptEdits", ["Bash"], False))
        self.assertEqual((arm["executor"], arm["command"]), ("command", stored["arms"]["good"]["command"]))
        self.assertNotIn("env_file", arm)
        self.assertNotIn("binary", arm)

    def test_report_gives_identical_material_read_from_different_files_as_identical_arms(self):
        for name in ("a", "b"):
            write(self.tmp / "arms" / f"{name}.md", "Be brief.\n")
            write(self.tmp / "res" / f"{name}.md", "a note\n")
        arm = lambda name: {"executor": "command", "command": "true", "instructions": f"arms/{name}.md",
                            "resources": {"notes/note.md": f"res/{name}.md"}}
        self.assertEqual(self.run_cli("run", self._plan({"a": arm("a"), "b": arm("b")}), "--out", str(self.out)).returncode, 0)
        arms = trial.report(self.out)["plan"]["arms"]
        self.assertEqual(arms["a"], arms["b"])  # the same material, whichever file it was read from

    def test_what_an_agent_leaves_never_stops_the_runner(self):
        s = self.tmp / "scenarios" / "make-file"
        spec = json.loads((s / "scenario.json").read_text())
        write(s / "scenario.json", json.dumps(dict(spec, judge={"question": "q?", "pass_when": "it passes"})))
        flag = self.tmp / "break-judge-context"
        with open(s / "check.py", "a") as f:
            f.write(f"\ndef judge_context(run):\n    import os\n"
                    f"    if '__plain__' in run.dir.name and os.path.exists({str(flag)!r}):\n        raise KeyError('boom')\n"
                    f"    return 'evidence'\n")
        judges = {name: launcher_judge(self.judges, name, (  # locks what it can of its cell, and reaches above it
            "mkdir -p ../verdict.json/locked; chmod 000 ../verdict.json/locked\n"
            "touch ../../judge-was-here 2>/dev/null; chmod 500 ../.. 2>/dev/null; chmod 500 ..\n"
            "echo '{\"verdict\": \"pass\", \"reason\": \"ok\"}'\n")) for name in ("j1", "j2")}
        made = "echo hi > out.txt; faketool x"
        leave = (made + "; cd .. && mkdir result.json final-0.md && mkdir -p judge/locked judge.next/locked && "
                 "touch judge/locked/f judge.next/locked/f && chmod 000 judge/locked judge.next/locked && "
                 "mkdir home && touch home/models_cache.json && chmod 500 home && chmod 500 .")
        plan = self._plan({"leave": {"executor": "command", "command": leave}, "plain": {"executor": "command", "command": made}},
                          judges["j1"])
        r = self.run_cli("run", plan, "--out", str(self.out), "--jobs", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.out / "summary.md").exists())
        expected = {"make-file__leave__r1": True, "make-file__plain__r1": True}
        self.assertEqual({k: v["passed"] for k, v in self.results().items()}, expected)
        self.assertEqual(self.run_cli("recheck", str(self.out), "--judge", json.dumps(judges["j2"])).returncode, 0)
        before = {k: v["judge_identity"]["model"] for k, v in self.results().items()}
        self.assertEqual(set(before.values()), {"j2"})
        flag.write_text("")
        r = self.run_cli("recheck", str(self.out), "--rejudge")
        self.assertEqual(r.returncode, 2)
        self.assertIn("judge_context: KeyError: 'boom'", r.stderr)
        self.assertIn("nothing was changed", r.stderr)
        self.assertTrue((self.judge_cell("make-file__plain__r1").parent / "judge.verdict.out").is_file())
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
        self._plan({"c": {"executor": "launcher", "script": str(FAKE_LAUNCHER), "model": "m", "env_file": "missing.env"}})
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
        with self.assertRaisesRegex(trial.TrialError, "no model matches claude-haiku-\\*"):
            trial.latest_model("claude-haiku-*", ids)
        with self.assertRaisesRegex(trial.TrialError, "only \\*"):
            trial.latest_model("gpt-?-luna", ids)
        self.assertEqual(trial.latest_model("m-*-*", ["m-" + "1-" * 200 + "1", "m-5-5"]), "m-5-5")  # overlong IDs skipped
        with self.assertRaisesRegex(trial.TrialError, "at most three"):
            trial.latest_model("m-*-*-*-*", ids)

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
    def test_readable_reaches_a_confined_launcher_arm(self):
        toolchain = self.judges / "extra-toolchain"  # apart from the plan's directory, as a real toolchain would be
        write(toolchain / "marker.txt", "reachable\n")
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
        arm = {"c": {"executor": "launcher", "script": str(FAKE_LAUNCHER), "model": "pretend-1", "readable": [str(toolchain)],
                     "pass_env": ["FAKE_LAUNCHER_MODE", "FAKE_LAUNCHER_MARK"]}}
        with mock.patch.dict(os.environ, FAKE_LAUNCHER_MODE="read-marker", FAKE_LAUNCHER_MARK=str(toolchain / "marker.txt")):
            r = self.run_cli("run", self._plan(arm), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.results()["make-file__c__r1"]["checks"]["seen"], "reachable")

    def test_the_judge_of_a_run_directory_changes_only_through_recheck(self):
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        good = {"good": {"executor": "command", "command": 'echo hi > out.txt; faketool x'}}
        self.assertEqual(self.run_cli("run", self._plan(good), "--out", str(self.out)).returncode, 0)
        judge = launcher_judge(self.judges, "m2", "echo '{\"verdict\": \"pass\", \"reason\": \"ok\"}'\n")
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
        self.assertIn("valid judge executors: launcher, host", r.stderr)
        self.assertEqual(json.loads((self.out / "plan.json").read_text())["judge"]["model"], "m2")
        # A verdict from another judge does not score until it is re-judged.
        stale = self.out / "runs" / "make-file__good__r1" / "result.json"
        stale.write_text(json.dumps(dict(json.loads(stale.read_text()), judge_identity={"executor": "launcher", "model": "m1"})))
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
        judges = {name: launcher_judge(self.judges, name, f"echo '{reply}'\n")
                  for name, reply in [("works", '{"verdict": "pass", "reason": "ok"}'), ("broken", "[1]")]}
        self.assertEqual(self.run_cli("recheck", str(self.out), "--judge", json.dumps(judges["works"])).returncode, 0)
        stored = json.loads((self.out / "plan.json").read_text())
        self.assertIn("judge", stored["scenarios"][0])  # the spec it judged with
        r = self.run_cli("run", self._plan(good), "--out", str(self.out))
        self.assertIn("has no judge", r.stderr)
        verdict = self.judge_cell("make-file__good__r1").parent / "judge.verdict.out"  # the judge's own standard output
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
        for bad, error in [('"launcher"', "must be a JSON object"), ("null", "must be a JSON object"), ("{", "not valid JSON")]:
            r = self.run_cli("recheck", str(self.out), "--judge", bad)
            self.assertEqual(r.returncode, 2, bad)
            self.assertIn(error, r.stderr)

    def test_one_run_or_recheck_uses_a_run_directory_at_a_time(self):
        self.out.mkdir()
        with trial._lock(self.out):
            r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("in use by another trial.py run", r.stderr)

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
        write(self.tmp / "scenarios" / "make-file" / "check.py",
              "def check(run):\n    return {'seen': run.file('seen.txt').strip()}\n")
        arm = {"executor": "launcher", "script": str(FAKE_LAUNCHER), "model": "pretend-1", "api_key_var": "TRIAL_TEST_KEY",
               "pass_env": ["FAKE_LAUNCHER_MODE"]}

        def seen(out_dir):
            return json.loads((out_dir / "runs" / "make-file__c__r1" / "result.json").read_text())["checks"]["seen"]

        with mock.patch.dict(os.environ, FAKE_LAUNCHER_MODE="show-key"):  # the pretend agent writes the key it was given
            os.environ.pop("TRIAL_ENV_FILE", None)
            # (a) neither env_file nor TRIAL_ENV_FILE: the key comes straight from this process's environment.
            os.environ["TRIAL_TEST_KEY"] = "from-parent-env"
            out_a = self.tmp / "out-a"
            self.assertEqual(self.run_cli("run", self._plan({"c": arm}), "--out", str(out_a)).returncode, 0)
            self.assertEqual(seen(out_a), "from-parent-env")
            del os.environ["TRIAL_TEST_KEY"]
            # (b) TRIAL_ENV_FILE names a file when the arm names none.
            env_file = self.tmp / "trial-env-file.env"
            env_file.write_text("TRIAL_TEST_KEY=from-trial-env-file\n")
            os.environ["TRIAL_ENV_FILE"] = str(env_file)
            out_b = self.tmp / "out-b"
            self.assertEqual(self.run_cli("run", self._plan({"c": arm}), "--out", str(out_b)).returncode, 0)
            self.assertEqual(seen(out_b), "from-trial-env-file")
            # (c) the arm's own env_file wins over TRIAL_ENV_FILE.
            arm_env_file = self.tmp / "arm.env"
            arm_env_file.write_text("TRIAL_TEST_KEY=from-arm-env-file\n")
            out_c = self.tmp / "out-c"
            self.assertEqual(self.run_cli("run", self._plan({"c": dict(arm, env_file=str(arm_env_file))}),
                                          "--out", str(out_c)).returncode, 0)
            self.assertEqual(seen(out_c), "from-arm-env-file")
            # (d) none of the three: a clear error naming all three ways to supply it.
            del os.environ["TRIAL_ENV_FILE"]
            r = self.run_cli("run", self._plan({"c": arm}), "--out", str(self.tmp / "out-d"))
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("env_file", r.stderr)
            self.assertIn("TRIAL_ENV_FILE", r.stderr)
            self.assertIn("environment", r.stderr)

    def test_binary_discovery_handles_shallow_paths_and_symlinks(self):
        # A shallow path (no nested install layout) must resolve without the IndexError an old
        # parents[3]-based install guess raised.
        shallow = self.tmp / "usr" / "bin" / "agent-cli"
        write(shallow, "#!/bin/sh\necho hi\n", 0o755)
        self.assertEqual(trial._resolve_binary(str(shallow)), str(shallow))
        readable = trial._executor_readable(str(shallow))
        self.assertIn(shallow.parent, readable)

        # A symlinked launcher (npm/pnpm/volta-style shim) resolves to its real target's own directory too,
        # and a shebang naming an interpreter (the node runtime a JS launcher needs) adds that directory.
        real_bin = self.tmp / "lib" / "node_modules" / "agent-cli" / "bin" / "agent-cli"
        write(real_bin, "#!/usr/bin/env node\n", 0o755)
        shim_dir = self.tmp / "shim" / "bin"
        shim_dir.mkdir(parents=True)
        shim = shim_dir / "agent-cli"
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

        # a bare name is looked up on PATH; one found nowhere is an error
        os.environ["PATH"] = f"{shallow.parent}{os.pathsep}{old_path}"
        try:
            self.assertEqual(trial._resolve_binary("agent-cli"), str(shallow))
        finally:
            os.environ["PATH"] = old_path
        with self.assertRaisesRegex(trial.TrialError, "cannot find the binary 'nonexistent-binary-xyz'"):
            trial._resolve_binary("nonexistent-binary-xyz")

    def test_resolve_binary_expands_bare_names_and_tilde_like_a_shell(self):
        # A bare name in "binary" used to be returned verbatim, treated as a path relative to the current
        # directory, and fail inside bwrap with an opaque "Can't mkdir parents".
        real = self.tmp / "usr" / "bin" / "agent-cli"
        write(real, "#!/bin/sh\necho hi\n", 0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{real.parent}{os.pathsep}{old_path}"
        try:
            self.assertEqual(trial._resolve_binary("agent-cli"), str(real))
            # a "~" binary is expanded the same way a shell would, not treated as a literal path segment
            home_bin = Path.home() / (".trial-test-tilde-" + os.urandom(4).hex())
            write(home_bin, "#!/bin/sh\necho hi\n", 0o755)
            try:
                self.assertEqual(trial._resolve_binary("~/" + home_bin.name), str(home_bin))
            finally:
                home_bin.unlink()
        finally:
            os.environ["PATH"] = old_path
        with self.assertRaisesRegex(trial.TrialError, "not a path that exists and no such name is on PATH"):
            trial._resolve_binary("nonexistent-binary-xyz")

    def test_executor_readable_never_exposes_root_or_an_ancestor_of_home(self):
        # A binary directly under "/" must never end up in the readable set: binding "/" back read-only
        # would undo the tmpfs bwrap puts over the user's home, re-exposing it whole.
        with mock.patch("trial.Path.home", return_value=Path("/nonexistent-fake-home-for-test")):
            readable = trial._executor_readable("/nonexistent-binary-for-test")
        self.assertNotIn(Path("/"), readable)
        # An ancestor of home (not just an immediate child, which too_broad already covered) must be
        # excluded too, for the same reason: it would remount over the tmpfs bwrap puts at home itself.
        fake_home = self.tmp / "fake" / "nested" / "home"
        write(fake_home.parent / "bin" / "agent-cli", "#!/bin/sh\necho hi\n", 0o755)
        with mock.patch("trial.Path.home", return_value=fake_home):
            readable = trial._executor_readable(str(fake_home.parent / "bin" / "agent-cli"))
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

    def test_typo_or_unrelated_sandbox_value_never_runs_a_launcher_or_command_unconfined(self):
        """A typo ("confinde") or another tool's own sandbox mode name must fail safe to confined - never silently drop
        this runtime's own bubblewrap (see _unconfined; only the literal "none" is the documented opt-out)."""
        write(self.tmp / "scenarios" / "make-file" / "scenario.json",
              json.dumps({"prompt": "create out.txt", "required": [], "sandbox": "confinde"}))
        launcher = {"c": {"executor": "launcher", "script": str(FAKE_LAUNCHER), "model": "pretend-1"}}
        command = {"k": {"executor": "command", "command": "echo SHOULD-NOT-RUN > escaped.txt"}}
        real_which = shutil.which

        def fake_which(name, *a, **k):
            return None if name == "bwrap" else real_which(name, *a, **k)

        with mock.patch("trial.shutil.which", side_effect=fake_which):
            for arms, out_name in [(launcher, "typo-launcher"), (command, "typo-command")]:
                out = self.tmp / out_name
                code = trial.main(["run", self._plan(arms), "--out", str(out)])
                self.assertEqual(code, 2, out_name)
                self.assertFalse(list(out.glob("runs/*")), out_name)  # nothing ran, confined or not

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
        judge = launcher_judge(self.judges, "m", "echo '{\"verdict\": \"pass\", \"reason\": \"ok\"}'\n")
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
        self.assertEqual(payload["arms"]["bad"]["commands_mean"], 0.0)  # a command arm is no agent: it ran none
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
            "judge": launcher_judge(self.judges, "investor", "echo '{\"verdict\": \"pass\", \"reason\": \"looks fine\"}'\n"),
            "scenarios": ["scenarios/eval-plan"]}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.results()
        self.assertTrue(res["eval-plan__a__r1"]["passed"])
        self.assertTrue(res["eval-plan__b__r1"]["passed"])
        # a single-file artifact's own content becomes the judged output
        self.assertEqual((self.out / "runs" / "eval-plan__a__r1" / "final-0.md").read_text(),
                         "A bakery selling artisan bread to local restaurants.\n")
        # a directory artifact with more than one file gives every file's content, each under its path
        self.assertEqual((self.out / "runs" / "eval-plan__b__r1" / "final-0.md").read_text(),
                         "--- appendix.md ---\nappendix\n--- index.md ---\nindex\n")
        stored = json.loads((self.out / "plan.json").read_text())["arms"]
        self.assertRegex(stored["a"]["artifact_sha256"], "^[0-9a-f]{64}$")
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
        judge = launcher_judge(self.judges, "j", (  # response 1 wins when it is alpha's output
            "case \"$prompt\" in *'<response_1>'*ALPHA_OUTPUT*'</response_1>'*) echo '{\"winner\": \"1\", \"reason\": \"seen\"}' ;;"
            " *'<response_1>'*) echo '{\"winner\": \"2\", \"reason\": \"seen\"}' ;;"
            " *) echo '{\"verdict\": \"pass\", \"reason\": \"seen\"}' ;; esac\n"))
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
        # when the results were written, read from the result files, and when this document was
        stamp = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$"
        self.assertRegex(payload["generated_at"], stamp)
        self.assertRegex(payload["ran"]["first"], stamp)
        self.assertLessEqual(payload["ran"]["first"], payload["ran"]["last"])
        self.assertLessEqual(payload["ran"]["last"], payload["generated_at"])
        # the document stays bounded even with a long final message somewhere in it
        self.assertLess(len(json.dumps(payload)), 20000)
        out_file = self.tmp / "report.json"
        r = self.run_cli("report", str(self.out), "--out", str(out_file))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(out_file.read_text())["name"], "rep")

    def test_report_shows_the_instructions_each_arm_received_bounded_and_only_from_the_run_directory(self):
        write(self.tmp / "arms" / "k.md", "be terse\r\n")
        write(self.tmp / "arms" / "long.md", "y" * (trial.REPORT_TEXT_CHARS + 100))
        write(self.tmp / "resources" / "demo-skill" / "SKILL.md", "a demo skill\n")
        stubs = {"dir": ".agents/skills", "count": 1, "chars": 60, "seed": 0}
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), description="Writes out.txt; the fake tool must be called.",
                                     judge_required=False)))
        write(self.tmp / "plan.json", json.dumps({
            "name": "rep", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"good": {"executor": "command", "model": "${TRIAL_TEST_UNSET:-m1}", "instructions": "arms/k.md",
                              "resources": {"skills/demo": "resources/demo-skill"}, "stub_skills": stubs,
                              "command": "echo hi > out.txt; faketool x"},
                     "long": {"executor": "command", "instructions": "arms/long.md", "command": "true"},
                     "bad": {"executor": "command", "command": "true"}},
            "scenarios": ["scenarios/make-file"]}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        # the source changing after the run never changes what the report shows: it reads the run's own snapshot
        write(self.tmp / "arms" / "k.md", "edited after the run\n")
        arms = trial.report(self.out)["plan"]["arms"]
        self.assertEqual((arms["good"]["instructions_text"], arms["good"]["instructions_truncated"]), ("be terse\n", False))
        self.assertEqual(len(arms["long"]["instructions_text"]), trial.REPORT_TEXT_CHARS)
        self.assertTrue(arms["long"]["instructions_truncated"])
        self.assertNotIn("instructions_text", arms["bad"])
        self.assertNotIn("instructions_truncated", arms["bad"])
        self.assertEqual(arms["good"]["resources"], ["skills/demo"])
        self.assertEqual(arms["good"]["stub_skills"], stubs)
        self.assertEqual(arms["good"]["model_spec"], "${TRIAL_TEST_UNSET:-m1}")
        scenario = trial.report(self.out)["plan"]["scenarios"][0]
        self.assertEqual(scenario["description"], "Writes out.txt; the fake tool must be called.")
        self.assertFalse(scenario["description_truncated"])
        self.assertIs(scenario["judge_required"], False)

        snapshot = self.out / "instructions" / (arms["good"]["instructions_sha256"] + ".md")
        original = snapshot.read_bytes()
        # a snapshot whose content no longer has the recorded digest is not what the runs received: omitted
        snapshot.write_text("tampered\n")
        report = trial.report(self.out)
        self.assertNotIn("instructions_text", report["plan"]["arms"]["good"])
        self.assertIn("instructions_text", report["plan"]["arms"]["long"])
        # a link in place of the snapshot is never followed, even to a file holding the right bytes
        outside = self.tmp / "outside"
        write(outside / snapshot.name, original.decode())
        snapshot.unlink()
        snapshot.symlink_to(outside / snapshot.name)
        self.assertNotIn("instructions_text", trial.report(self.out)["plan"]["arms"]["good"])
        # nor is an instructions directory that is itself a link out of the run directory
        folder = self.out / "instructions"
        shutil.copy2(folder / (arms["long"]["instructions_sha256"] + ".md"), outside)
        shutil.rmtree(folder)
        folder.symlink_to(outside)
        report = trial.report(self.out)
        self.assertNotIn("instructions_text", report["plan"]["arms"]["good"])
        self.assertNotIn("instructions_text", report["plan"]["arms"]["long"])
        # a missing snapshot leaves the digest alone and the report still succeeds
        folder.unlink()
        r = self.run_cli("report", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        good = json.loads(r.stdout)["plan"]["arms"]["good"]
        self.assertIn("instructions_sha256", good)
        self.assertNotIn("instructions_text", good)

    def test_report_scenario_description_is_bounded_and_optional(self):
        long = trial._report_scenario({"name": "s", "prompt": "p", "description": "d" * (trial.REPORT_TEXT_CHARS + 1)})
        self.assertEqual(len(long["description"]), trial.REPORT_TEXT_CHARS)
        self.assertTrue(long["description_truncated"])
        self.assertNotIn("judge_required", long)
        for absent in ({"name": "s"}, {"name": "s", "description": ""}, {"name": "s", "description": ["not text"]}):
            entry = trial._report_scenario(absent)
            self.assertNotIn("description", entry)
            self.assertNotIn("description_truncated", entry)

    def test_report_shows_each_artifact_arms_artifact_text(self):
        write(self.tmp / "artifacts" / "plan-a.md", "A bakery selling artisan bread to local restaurants.\n")
        directory = self.tmp / "artifacts" / "plan-b"
        write(directory / "index.md", "index\n")
        write(directory / "appendix.md", "appendix")
        (directory / "logo.bin").write_bytes(b"\x89PNG\0\0data")
        write(self.tmp / "scenarios" / "eval-plan" / "scenario.json", json.dumps({
            "prompt": "You are an investor judging this business plan for viability.", "required": []}))
        write(self.tmp / "plan.json", json.dumps({
            "name": "artifact", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"a": {"executor": "artifact", "artifact": "artifacts/plan-a.md"},
                     "b": {"executor": "artifact", "artifact": "artifacts/plan-b"},
                     "c": {"executor": "command", "command": "true"}},
            "scenarios": ["scenarios/eval-plan"]}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        arms = trial.report(self.out)["plan"]["arms"]
        self.assertEqual(arms["a"]["artifact_text"], "A bakery selling artisan bread to local restaurants.\n")
        self.assertFalse(arms["a"]["artifact_truncated"])
        # a directory gives each file under its relative path, in path order, naming a binary file without its bytes
        self.assertEqual(arms["b"]["artifact_text"],
                         "--- appendix.md ---\nappendix\n--- index.md ---\nindex\n--- logo.bin ---\n[not text: 10 bytes]\n")
        self.assertNotIn("artifact_text", arms["c"])
        # a changed snapshot is no longer what the runs judged: omitted, and the report still succeeds
        (self.out / "artifacts" / arms["b"]["artifact_sha256"] / "index.md").write_text("changed\n")
        arms = trial.report(self.out)["plan"]["arms"]
        self.assertNotIn("artifact_text", arms["b"])
        self.assertIn("artifact_text", arms["a"])
        # a long artifact is cut to the bound and says so
        write(self.tmp / "artifacts" / "plan-a.md", "z" * (trial.REPORT_TEXT_CHARS * 2))
        out2 = self.tmp / "out2"
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(out2), "--arms", "a")
        self.assertEqual(r.returncode, 0, r.stderr)
        a = trial.report(out2)["plan"]["arms"]["a"]
        self.assertEqual(len(a["artifact_text"]), trial.REPORT_TEXT_CHARS)
        self.assertTrue(a["artifact_truncated"])

    def test_executor_readable_never_exposes_home_or_its_immediate_children(self):
        fake_home = self.tmp / "fakehome"
        # ~/bin/agent-cli: the "parent of a bin/ directory" rule used to expose the whole home directory.
        shallow = fake_home / "bin" / "agent-cli"
        write(shallow, "#!/bin/sh\necho hi\n", 0o755)
        with mock.patch("trial.Path.home", return_value=fake_home):
            readable = trial._executor_readable(str(shallow))
        self.assertNotIn(fake_home, readable)
        self.assertIn(fake_home / "bin", readable)  # the binary's own, narrow directory is still needed

        # ~/.local/bin/agent-cli and ~/.cargo/bin/agent-cli: a shim placed directly in one of these broad,
        # multi-purpose directories one level below home (which can hold unrelated credentials - a real
        # host's ~/.cargo/credentials.toml, for example, or unrelated user scripts) gets only the single
        # binary FILE exposed, never the whole shared directory around it.
        for sub in (".local", ".cargo"):
            b = fake_home / sub / "bin" / "agent-cli"
            write(b, "#!/bin/sh\necho hi\n", 0o755)
            with mock.patch("trial.Path.home", return_value=fake_home):
                readable = trial._executor_readable(str(b))
            self.assertNotIn(fake_home / sub, readable, sub)
            self.assertNotIn(fake_home / sub / "bin", readable, sub)
            self.assertIn(b, readable, sub)  # the binary itself still runs

        # a package root that sits well below home (a real npm-style global install under $HOME) is still
        # exposed: only the broad, shallow directories immediately under home are guarded against.
        real_bin = fake_home / ".npm-global" / "lib" / "node_modules" / "agent-cli" / "bin" / "agent-cli"
        write(real_bin, "#!/usr/bin/env node\n", 0o755)
        with mock.patch("trial.Path.home", return_value=fake_home):
            readable = trial._executor_readable(str(real_bin))
        self.assertIn(fake_home / ".npm-global" / "lib" / "node_modules" / "agent-cli", readable)

        # a native-installer layout (~/.local/bin/other-cli -> ~/.local/share/other-cli/versions/2.1.0/other-cli):
        # the symlink's own directory is the same broad, shared ~/.local/bin as above (never exposed whole,
        # only the symlink file itself), while the resolved target sits well below home and keeps its whole
        # versioned directory exposed.
        target = fake_home / ".local" / "share" / "other-cli" / "versions" / "2.1.0" / "other-cli"
        write(target, "#!/bin/sh\necho hi\n", 0o755)
        shim = fake_home / ".local" / "bin" / "other-cli"
        shim.parent.mkdir(parents=True, exist_ok=True)
        shim.symlink_to(target)
        with mock.patch("trial.Path.home", return_value=fake_home):
            readable = trial._executor_readable(str(shim))
        self.assertNotIn(fake_home / ".local" / "bin", readable)
        self.assertIn(shim, readable)
        self.assertIn(target.parent, readable)

    def test_only_literal_none_turns_off_confinement(self):
        self.assertFalse(trial._unconfined({}))
        self.assertFalse(trial._unconfined({"sandbox": "confined"}))
        # any other value, a typo or another tool's own sandbox name, never silently drops the confinement
        # checks, git, and judges rely on the way "none" does
        self.assertFalse(trial._unconfined({"sandbox": "workspace-write"}))
        self.assertTrue(trial._unconfined({"sandbox": "none"}))

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
            "judge": launcher_judge(self.judges, "investor", "echo '{\"verdict\": \"pass\", \"reason\": \"looks fine\"}'\n"),
            "scenarios": ["scenarios/eval-plan"]}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
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
        judge = launcher_judge(self.judges, "j", "case \"$prompt\" in *'<response_1>'*) echo '{\"winner\": \"tie\", \"reason\": \"n/a\"}' ;;"
                               " *) echo '{\"verdict\": \"pass\", \"reason\": \"n/a\"}' ;; esac\n")
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
        judge = launcher_judge(self.judges, "j", "case \"$prompt\" in *'<response_1>'*) echo '{\"winner\": \"tie\", \"reason\": \"n/a\"}' ;;"
                               " *) echo '{\"verdict\": \"pass\", \"reason\": \"n/a\"}' ;; esac\n")
        write(self.tmp / "plan.json", json.dumps({"name": "pw-evidence-fail", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"alpha": {"executor": "command", "command": "echo ALPHA_OUTPUT"},
                     "beta": {"executor": "command", "command": "echo BETA_OUTPUT"}},
            "judge": judge, "scenarios": ["scenarios/make-file"]}))
        check = self.tmp / "scenarios" / "make-file" / "check.py"
        failing = check.read_text()
        check.write_text("def check(run):\n    return {}\n\n\ndef judge_context(run):\n    return 'EVIDENCE_FOR_' + run.final_message.strip()\n")
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        check.write_text(failing)  # the evidence the runs were judged on can no longer be given for beta
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 0, r.stderr)
        detail = json.loads((self.out / "pairwise" / "alpha__beta" / "make-file__r1.json").read_text())
        self.assertIn("b", detail["evidence_errors"])
        self.assertIn("no evidence for beta", detail["evidence_errors"]["b"])
        # a pair the judge cannot be given the evidence for is invalid, and no judge is asked about it
        self.assertEqual(detail["outcome"], "invalid")
        self.assertFalse((self.out / "pairwise" / ".cells" / detail["cell"] / "order-1" / "prompt.md").exists())
        self.assertIn("invalid 1", r.stdout)

    def test_native_windows_is_refused_with_a_clear_error(self):
        with mock.patch("trial.os.name", "nt"):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                code = trial.main(["run", str(self.tmp / "plan.json"), "--out", str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("WSL", buf.getvalue())
        self.assertFalse(self.out.exists())  # refused before anything was scheduled

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
        # A toolchain an agent installed into the run's private home, and Cargo's download cache there;
        # a ".rustup" without toolchains and a "registry" outside ".cargo" are left alone.
        (job / "harness" / "home" / ".rustup" / "toolchains" / "stable").mkdir(parents=True)
        (job / "harness" / "home" / ".cargo" / "registry" / "cache").mkdir(parents=True)
        (work / "notes" / ".rustup").mkdir(parents=True)
        (work / "registry").mkdir()
        try:
            found = trial._build_output_under(job)
            self.assertEqual({p.relative_to(job) for p in found},
                             {Path("work/target"), Path("work/sub/go-build"), Path("work/pkg/__pycache__"),
                              Path("work/locked/target"), Path("harness/home/.rustup"),
                              Path("harness/home/.cargo/registry")})
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
        judge = launcher_judge(self.judges, "m", "", resources={"../escape": "resources/demo-skill"})
        write(self.tmp / "plan.json", json.dumps({"name": "p", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"good": {"executor": "command", "command": "true"}},
            "judge": judge, "scenarios": ["scenarios/make-file"]}))
        with self.assertRaisesRegex(trial.TrialError, 'judge resources.*without ".."'):
            trial.load_plan(self.tmp / "plan.json", None, None, None)
        s.write_text(json.dumps(dict(json.loads(s.read_text()))))
        good_judge = launcher_judge(self.judges, "m", "", resources={"skills/demo": "resources/demo-skill"})
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

    # The host executor: the host that runs trial.py starts each executor by its own means, and the runtime
    # prepares, scores, and records the run around it. A test plays the host's controller.

    def _dispatch(self, name="dispatch.json"):
        return json.loads((self.out / name).read_text())

    def _play_host(self, entry, reply, record, task=None):
        """One dispatch.json entry as a host's controller carries it out: the executor's task in the working directory
        with the environment it was given, then the executor's reply, and the record last."""
        if task:
            subprocess.run(["sh", "-c", task], cwd=entry["workdir"], env=entry["env"], check=True, capture_output=True)
        Path(entry["reply"]).write_text(reply)
        Path(entry["record"]).write_text(json.dumps(record))

    def test_a_host_arm_is_prepared_and_dispatched_and_a_later_run_scores_it(self):
        write(self.tmp / "arms" / "h.md", "work carefully\n")
        write(self.tmp / "resources" / "ref.md", "reference\n")
        write(self.tmp / "scenarios" / "make-file" / "check.py", (
            "def check(run):\n"
            "    return {'made_file': run.file('out.txt').strip() == 'hi',\n"
            "            'setup_ran': run.file('prepared.txt').strip() == 'prepared',\n"
            "            'tool_called': any(c.get('tool') == 'faketool' for c in run.calls),\n"
            "            'final': run.final_message}\n"))
        plan = self.tmp / "plan.json"
        write(plan, json.dumps({"name": "hosted", "repeats": 2, "seed": 3, "sandbox": self.default_sandbox,
            "arms": {"guided": {"executor": "host", "host_env": True, "instructions": "arms/h.md",
                                "resources": {"notes/ref.md": "resources/ref.md"}},
                     "plain": {"executor": "host", "host_env": True}},
            "scenarios": ["scenarios/make-file"]}))
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 4, r.stderr)  # waiting for the host: neither success nor failure
        self.assertIn(f"host jobs awaiting their executor: 4 ({self.out / 'dispatch.json'})", r.stdout)
        self.assertEqual(self.results(), {})
        entries = self._dispatch()
        schedule = [line.split("\t") for line in self.run_cli("run", str(plan), "--dry-run").stdout.splitlines()
                    if line.startswith("make-file\t")]
        self.assertEqual([e["job"] for e in entries], [f"{s}__{arm}__{rep}" for s, arm, rep in schedule])
        self.assertEqual([e["job"][-2:] for e in entries], ["r1", "r1", "r2", "r2"])  # arms interleaved per repeat
        for e in entries:
            with self.subTest(e["job"]):
                run_dir = self.out / "runs" / e["job"]
                self.assertEqual(e["workdir"], str(run_dir / "work"))
                self.assertEqual(Path(e["workdir"], "prepared.txt").read_text(), "prepared\n")  # setup.sh ran
                self.assertEqual(Path(e["workdir"], "seed.txt").read_text(), "seed\n")  # the fixture is there
                self.assertEqual((e["prompt"], e["followups"]), ("create out.txt", []))
                home = Path(e["env"]["HOME"])
                self.assertTrue(home.is_relative_to(run_dir) and Path(e["env"]["TMPDIR"]).is_relative_to(run_dir))
                self.assertTrue((Path(e["env"]["PATH"].split(os.pathsep)[0]) / "faketool").is_file())  # tools first
                for path in (e["reply"], e["record"]):  # in the run directory, outside the executor's workspace
                    self.assertTrue(Path(path).is_relative_to(run_dir) and not Path(path).is_relative_to(run_dir / "work"))
                if "__guided__" in e["job"]:
                    self.assertTrue(Path(e["instructions"]).is_relative_to(run_dir))
                    self.assertEqual(Path(e["instructions"]).read_text(), "work carefully\n")
                    self.assertEqual((home / "notes" / "ref.md").read_text(), "reference\n")
                else:
                    self.assertIsNone(e["instructions"])
        record = {"finished": True, "workspace": "direct", "model": "reported-model", "instructions": "system",
                  "env_applied": True, "fresh": True}
        for i, e in enumerate(entries):
            self._play_host(e, f"out.txt made ({i})\n", record, task="echo hi > out.txt; faketool x")
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("host jobs awaiting their executor: 0", r.stdout)
        self.assertFalse((self.out / "dispatch.json").exists())
        res = self.results()
        self.assertEqual(sorted(res), sorted(e["job"] for e in entries))
        for i, e in enumerate(entries):
            v = res[e["job"]]
            self.assertEqual((v["status"], v["passed"], v["confined"]), ("ok", True, False))
            self.assertTrue(v["checks"]["setup_ran"] and v["checks"]["tool_called"], v["checks"])
            self.assertEqual(v["checks"]["final"], f"out.txt made ({i})\n")  # the reply is the final message
            self.assertEqual(v["host"], record)
            self.assertEqual(v["identity"]["executor"], "host")
        payload = json.loads(self.run_cli("summarize", str(self.out), "--json").stdout)
        self.assertEqual({k: (v["passed"], v["valid"]) for k, v in payload["scenarios"].items()},
                         {"make-file|guided": (2, 2), "make-file|plain": (2, 2)})
        self.assertIn("**Host executor**", (self.out / "summary.md").read_text())

    def test_a_host_arm_needs_host_env_on_a_scenario_with_fake_tools(self):
        write(self.tmp / "scenarios" / "toolless" / "scenario.json", json.dumps({"prompt": "say hi"}))
        for name, arm, scenario, code in (("refused", {"executor": "host"}, "make-file", 2),
                                          ("committed", {"executor": "host", "host_env": True}, "make-file", 4),
                                          ("toolless", {"executor": "host"}, "toolless", 4)):
            with self.subTest(name):
                plan = self.tmp / f"{name}.json"
                write(plan, json.dumps({"name": name, "repeats": 1, "sandbox": self.default_sandbox, "arms": {"h": arm},
                                        "scenarios": [f"scenarios/{scenario}"]}))
                out = self.tmp / f"out-{name}"
                r = self.run_cli("run", str(plan), "--out", str(out))
                self.assertEqual(r.returncode, code, r.stderr)
                if code == 2:
                    self.assertIn('"host_env": true', r.stderr)
                    self.assertFalse(out.exists())  # refused when the plan loads, before anything is prepared

    def test_a_host_judge_is_asked_through_blind_cells_and_its_replies_score_the_runs(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "judge": {"question": "is the output thorough?", "pass_when": "it is"}}))
        plan = self.tmp / "plan.json"
        write(plan, json.dumps({"name": "judged", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"alpha": {"executor": "command", "command": "echo ALPHA_OUTPUT"},
                     "beta": {"executor": "command", "command": "echo BETA_OUTPUT"}},
            "judge": {"executor": "host"}, "scenarios": ["scenarios/make-file"]}))
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn(f"runs awaiting the host judge: 2 ({self.out / 'judge-dispatch.json'})", r.stdout)
        self.assertEqual(self.results(), {})
        cells = self._dispatch("judge-dispatch.json")
        self.assertEqual(len(cells), 2)
        for c in cells:
            self.assertEqual(set(c), {"cell", "prompt", "schema", "reply"})
            prompt = Path(c["prompt"]).read_text()
            for name in ("alpha", "beta", "make-file"):  # neither the entry nor the prompt tells the judge whose run
                self.assertNotIn(name, json.dumps(c).replace(str(self.out), ""))
                self.assertNotIn(name, prompt)
            self.assertIn("is the output thorough?", prompt)
            schema = json.loads(Path(c["schema"]).read_text())
            self.assertEqual((schema["required"], schema["properties"]["verdict"]["enum"]),
                             (["verdict", "reason"], ["pass", "fail", "unclear"]))
        # a run directory keeps one judge, including the one its waiting runs were put to
        changed = json.loads(plan.read_text())
        changed["judge"]["model"] = "another"
        write(self.tmp / "changed.json", json.dumps(changed))
        r = self.run_cli("run", str(self.tmp / "changed.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("judge-dispatch.json", r.stderr)
        for c in cells:
            alpha = "ALPHA_OUTPUT" in Path(c["prompt"]).read_text()
            Path(c["reply"]).write_text('```json\n{"verdict": "pass", "reason": "thorough"}\n```\n' if alpha
                                        else '{"verdict": "maybe", "reason": "hard to say"}')
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.out / "judge-dispatch.json").exists())
        res = self.results()
        alpha, beta = res["make-file__alpha__r1"], res["make-file__beta__r1"]
        self.assertEqual((alpha["passed"], alpha["judge"]["verdict"]), (True, "pass"))
        self.assertEqual(alpha["judge_identity"], {"executor": "host", "model": "unknown"})
        self.assertEqual((beta["passed"], beta["judge"]["verdict"]), (None, "error"))  # invalid, never a guess
        self.assertIn("invalid 1: judge-error", r.stdout)
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)  # a plain recheck keeps the verdicts
        self.assertTrue(self.results()["make-file__alpha__r1"]["passed"])

    def test_a_judge_never_sees_the_arm_and_a_verdict_outside_the_schema_is_invalid(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "judge": {"question": "is it done?", "pass_when": "it is"}}))
        plan = self.tmp / "plan.json"
        write(plan, json.dumps({"name": "blind", "repeats": 1, "sandbox": self.default_sandbox,
            "arms": {"secretarm": {"executor": "command",  # a reply that quotes the paths it worked in
                                   "command": 'echo "worked in $PWD as $(basename "$TRIAL_JOB_DIR")"'}},
            "judge": {"executor": "host"}, "scenarios": ["scenarios/make-file"]}))
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        prompt = Path(self._dispatch("judge-dispatch.json")[0]["prompt"]).read_text()
        self.assertNotIn("secretarm", prompt)
        self.assertNotIn(str(self.out), prompt)
        self.assertIn("worked in <run>/work as <run>", prompt)
        # a launcher judge whose answer is not one of the schema's verdicts gives no verdict: the run is invalid
        cli = json.loads(plan.read_text())
        cli["judge"] = launcher_judge(self.judges, "maybe", "echo '{\"verdict\": \"maybe\", \"reason\": \"hard to say\"}'\n")
        write(self.tmp / "cli.json", json.dumps(cli))
        out = self.tmp / "out-cli"
        self.assertEqual(self.run_cli("run", str(self.tmp / "cli.json"), "--out", str(out)).returncode, 0)
        result = json.loads((out / "runs" / "make-file__secretarm__r1" / "result.json").read_text())
        self.assertEqual((result["passed"], result["judge"]["verdict"]), (None, "error"))

    def test_a_plan_or_scenario_that_cannot_be_read_is_refused_without_a_traceback(self):
        missing = self._plan({"a": {"executor": "command", "command": "true"}})
        plan = json.loads(Path(missing).read_text())
        write(self.tmp / "missing.json", json.dumps(dict(plan, scenarios=["scenarios/no-such-scenario"])))
        write(self.tmp / "broken.json", "{not json")
        write(self.tmp / "scenarios" / "listed" / "scenario.json", "[1, 2]")
        write(self.tmp / "listed.json", json.dumps(dict(plan, scenarios=["scenarios/listed"])))
        for name, error in [("missing.json", "scenario scenarios/no-such-scenario: "), ("broken.json", "is not valid JSON"),
                            ("listed.json", "must hold a JSON object"), ("absent.json", "plan: ")]:
            r = self.run_cli("run", str(self.tmp / name), "--out", str(self.out))
            self.assertEqual(r.returncode, 2, name)
            self.assertIn(error, r.stderr, name)
            self.assertNotIn("Traceback", r.stderr, name)

    def test_a_misspelled_executor_is_refused_and_replies_are_read_in_turn_order(self):
        r = self.run_cli("run", self._plan({"a": {"executor": "codx"}}), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("'codx'", r.stderr)
        self.assertIn("valid executors: launcher, command, artifact, host", r.stderr)
        self.assertFalse(self.out.exists())
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    return {'final': run.final_message}\n")
        plan = self._plan({"turns": {"executor": "command",
                                     "command": 'for i in 0 1 2 9 10 11; do echo "turn $i" > "$TRIAL_JOB_DIR/final-$i.md"; done'}})
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        self.assertEqual(self.results()["make-file__turns__r1"]["checks"]["final"], "turn 11\n")

    def test_a_host_job_stays_awaiting_until_its_reply_and_record_arrive(self):
        plan = self._plan({"h": {"executor": "host", "host_env": True}})
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 4)
        entry = self._dispatch()[0]
        Path(entry["workdir"], "progress.txt").write_text("half done\n")  # the host's executor is still at work
        for name, reply, record, reason in (("nothing yet", None, None, None),
                                            ("a reply alone", "made it\n", None, "record"),
                                            ("a record that is not JSON", None, "{not json", "not valid JSON"),
                                            ("a record with NaN", None, '{"finished": true, "x": NaN}', "not valid JSON"),
                                            ("a record without finished", None, json.dumps({"model": "m"}), '"finished"')):
            with self.subTest(name):
                if reply is not None:
                    Path(entry["reply"]).write_text(reply)
                if record is not None:
                    Path(entry["record"]).write_text(record)
                r = self.run_cli("run", plan, "--out", str(self.out))
                self.assertEqual(r.returncode, 4, r.stderr)
                line = next(l for l in r.stdout.splitlines() if l.startswith("make-file__h__r1\t"))
                self.assertTrue(line.startswith("make-file__h__r1\tawaiting-host\tpassed=None"), line)
                if reason:
                    self.assertIn(reason, line)
                self.assertEqual(self.results(), {})  # never a silent pass
                self.assertEqual(self._dispatch(), [entry])  # listed again as it was
                self.assertEqual(Path(entry["workdir"], "progress.txt").read_text(), "half done\n")  # never redone
        self.assertEqual(self.run_cli("summarize", str(self.out)).returncode, 2)  # nothing to count yet

    def test_a_host_record_saying_the_executor_did_not_finish_makes_the_run_invalid(self):
        for name, extra in (("may-stop", {}), ("must-end", {"timeout_fails": True})):
            write(self.tmp / "scenarios" / name / "scenario.json",
                  json.dumps({"prompt": "work", "followups": ["continue", "finish up"], **extra}))
            write(self.tmp / "scenarios" / name / "check.py", "def check(run):\n    return {'final': run.final_message}\n")
        plan = self.tmp / "plan.json"
        write(plan, json.dumps({"name": "stops", "repeats": 1, "sandbox": self.default_sandbox,
                                "arms": {"h": {"executor": "host"}},
                                "scenarios": ["scenarios/may-stop", "scenarios/must-end"]}))
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        for e in self._dispatch():
            self.assertEqual(e["followups"], ["continue", "finish up"])  # sent in order; the reply follows the last
            self._play_host(e, "stopped partway\n", {"finished": False, "workspace": "direct"})
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("invalid 1: unfinished", r.stdout)
        for cmd in ("run", "recheck"):
            if cmd == "recheck":
                self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
            res = self.results()
            self.assertEqual((res["may-stop__h__r1"]["status"], res["may-stop__h__r1"]["passed"]), ("unfinished", None), cmd)
            self.assertIs(res["must-end__h__r1"]["passed"], False, cmd)  # where ending is under test, as a timeout
            self.assertEqual(res["may-stop__h__r1"]["checks"]["final"], "stopped partway\n", cmd)

    def test_host_runs_need_no_bubblewrap_network_or_model_endpoint(self):
        # A hosted Python sandbox: no bubblewrap, no network, and subagents that cannot reach its files.
        s = self.tmp / "scenarios" / "repo"
        write(s / "scenario.json", json.dumps({"prompt": "add out.txt saying hi", "required": ["made_file", "base_kept"],
                                               "judge": {"question": "does out.txt say hi?", "pass_when": "it does"}}))
        write(s / "setup.sh", "git init -q . && echo base > base.txt && git add base.txt && git commit -q -m base\n")
        write(s / "check.py", "def check(run):\n    return {'made_file': run.file('out.txt').strip() == 'hi',\n"
                              "            'base_kept': run.git('show', 'HEAD:base.txt') == 'base'}\n")
        plan = self.tmp / "sandboxed.json"
        write(plan, json.dumps({"name": "sandboxed", "repeats": 1,
            "arms": {"unnamed": {"executor": "host"}, "named": {"executor": "host", "model": "latest:claude-sonnet-*"}},
            "judge": {"executor": "host"}, "scenarios": ["scenarios/repo"]}))
        real_which = shutil.which

        def run():
            buf = io.StringIO()
            with mock.patch("trial.shutil.which", side_effect=lambda n, *a, **k: None if n == "bwrap" else real_which(n, *a, **k)), \
                    mock.patch("socket.socket", side_effect=OSError("the network is off")), \
                    contextlib.redirect_stdout(buf):
                code = trial.main(["run", str(plan), "--out", str(self.out), "--sandbox", "none"])
            return code, buf.getvalue()

        self.assertEqual(run()[0], 4)
        stored = json.loads((self.out / "plan.json").read_text())
        self.assertEqual(stored["arms"]["unnamed"]["model"], "unknown")
        self.assertEqual(stored["arms"]["named"]["model"], "latest:claude-sonnet-*")  # free text, as given
        self.assertEqual(stored["judge"]["model"], "unknown")
        for e in self._dispatch():  # the controller relays the workspace to a subagent and back
            seen = Path(e["workdir"], "base.txt").read_text()
            Path(e["workdir"], "out.txt").write_text("hi\n" if seen == "base\n" else "?\n")
            self._play_host(e, "out.txt now says hi\n", {"finished": True, "workspace": "relayed", "fresh": True})
        self.assertEqual(run()[0], 4)  # now each run awaits the host judge
        for c in self._dispatch("judge-dispatch.json"):
            Path(c["reply"]).write_text('{"verdict": "pass", "reason": "it says hi"}')
        code, out = run()
        self.assertEqual(code, 0, out)
        res = self.results()
        for job, model in (("repo__unnamed__r1", "unknown"), ("repo__named__r1", "latest:claude-sonnet-*")):
            self.assertEqual((res[job]["passed"], res[job]["identity"]["model"], res[job]["sandbox"]), (True, model, "none"))
            self.assertTrue(res[job]["checks"]["base_kept"])  # setup's git commit, read back by the check
            self.assertEqual(res[job]["host"]["workspace"], "relayed")
        runs = {r["job"]: r for r in trial.report(self.out)["runs"]}
        self.assertEqual(runs["repo__named__r1"]["host"], {"finished": True, "workspace": "relayed", "fresh": True})

    def _judged_plan(self, question="is the output thorough?", repeats=1, judge=None):
        """Two command arms whose outputs name them, under a host judge (or `judge`), on a scenario with a question."""
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "judge": {"question": question, "pass_when": "it is"}}))
        plan = self.tmp / "plan.json"
        write(plan, json.dumps({"name": "judged", "repeats": repeats, "sandbox": self.default_sandbox,
            "arms": {"alpha": {"executor": "command", "command": "echo ALPHA_OUTPUT"},
                     "beta": {"executor": "command", "command": "echo BETA_OUTPUT"}},
            "judge": judge or {"executor": "host"}, "scenarios": ["scenarios/make-file"]}))
        return plan

    def _answer(self, name, reply):
        """A host's controller answering every prompt a dispatch file lists with reply(prompt text)."""
        entries = self._dispatch(name)
        for e in entries:
            Path(e["reply"]).write_text(reply(Path(e["prompt"]).read_text()))
        return entries

    def test_runs_that_take_up_only_some_jobs_keep_every_waiting_one_listed(self):
        for name in ("s1", "s2"):
            write(self.tmp / "scenarios" / name / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file"]}))
            write(self.tmp / "scenarios" / name / "check.py",
                  "def check(run):\n    return {'made_file': run.file('out.txt').strip() == 'hi'}\n")
        plan = self.tmp / "plan.json"
        write(plan, json.dumps({"name": "filtered", "repeats": 2, "sandbox": self.default_sandbox,
                                "arms": {"A": {"executor": "host"}, "B": {"executor": "host"}},
                                "scenarios": ["scenarios/s1", "scenarios/s2"]}))
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        record = {"finished": True, "workspace": "direct"}
        for answered, flags, waiting in (("__A__", ["--arms", "A"], {"s1__B__r1", "s2__B__r1", "s1__B__r2", "s2__B__r2"}),
                                         ("s1__B__", ["--only", "s1"], {"s2__B__r1", "s2__B__r2"}),
                                         ("s2__B__r1", ["--repeats", "1"], {"s2__B__r2"})):
            for e in self._dispatch():
                if answered in e["job"]:
                    self._play_host(e, "done\n", record, task="echo hi > out.txt")
            r = self.run_cli("run", str(plan), "--out", str(self.out), *flags)
            self.assertEqual(r.returncode, 4, flags)  # the jobs it did not take up still wait on the host
            self.assertEqual({e["job"] for e in self._dispatch()}, waiting, flags)
            self.assertIn(f"host jobs awaiting their executor: {len(waiting)}", r.stdout)
        for e in self._dispatch():
            self._play_host(e, "done\n", record, task="echo hi > out.txt")
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.out / "dispatch.json").exists())
        self.assertEqual([v["passed"] for v in self.results().values()], [True] * 8)

    def test_a_run_awaiting_the_host_judge_is_scored_with_the_checks_and_question_of_now(self):
        plan = self._judged_plan(question="is the output thorough?")
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    return {'version': 1}\n")
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "pass", "reason": "thorough"}')
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    return {'version': 2}\n")
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual({(json.dumps(v["checks"]), v["judge"]["verdict"], v["passed"]) for v in self.results().values()},
                         {('{"version": 2}', "pass", True)})  # the checks of now, not of when the prompt went out
        # a question that changed between dispatch and answer: the answer to the old one is discarded, and the run waits
        self.out = self.tmp / "out-question"
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        cells = self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "pass", "reason": "thorough"}')
        self._judged_plan(question="is the output short?")
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(self.results(), {})
        now = self._dispatch("judge-dispatch.json")  # the same cells, asking the question of now
        self.assertEqual([(c["cell"], c["prompt"]) for c in now], [(c["cell"], c["prompt"]) for c in cells])
        for old, c in zip(cells, now):
            self.assertNotEqual(old["reply"], c["reply"])  # asked anew: an answer to the old question is never read
            self.assertFalse(Path(old["reply"]).exists() or Path(c["reply"]).exists())
            self.assertIn("is the output short?", Path(c["prompt"]).read_text())
            self.assertNotIn("thorough", Path(c["prompt"]).read_text())
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "fail", "reason": "long"}')
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 0)
        self.assertEqual({(v["judge"]["verdict"], v["passed"]) for v in self.results().values()}, {("fail", False)})

    def test_a_host_judge_is_given_only_its_prompt_so_resources_on_it_are_refused(self):
        write(self.tmp / "resources" / "rubric.md", "a rubric\n")
        plan = self._judged_plan(judge={"executor": "host", "resources": {"rubric.md": "resources/rubric.md"}})
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn('"resources"', r.stderr)
        self.assertFalse(self.out.exists())

    def test_pairwise_asks_a_host_judge_between_calls(self):
        plan = self._judged_plan(question="which output is more thorough?", repeats=2)
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "pass", "reason": "ok"}')
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 0)
        listed = "pairwise/alpha__beta/dispatch.json"
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn(f"pairwise orders awaiting the host judge: 4 ({self.out / listed})", r.stdout)
        orders = self._dispatch(listed)  # both orders of each of the two pairs
        for o in orders:
            self.assertEqual(set(o), {"cell", "prompt", "schema", "reply"})
            for name in ("alpha", "beta", "make-file"):
                self.assertNotIn(name, json.dumps(o).replace(str(self.out), ""))
                self.assertNotIn(name, Path(o["prompt"]).read_text())
        self.assertFalse((self.out / "pairwise" / "alpha__beta.json").exists())  # no result until every order is in
        alpha = lambda o: "1" if "ALPHA_OUTPUT" in Path(o["prompt"]).read_text().split("</response_1>")[0] else "2"
        for o in orders[::2]:
            Path(o["reply"]).write_text(json.dumps({"winner": alpha(o), "reason": "more thorough"}))
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(self._dispatch(listed), orders[1::2])  # a cell keeps its reply; only the others are asked
        self.assertTrue(all(Path(o["reply"]).exists() for o in orders[::2]))
        for o, winner in zip(orders[1::2], (alpha(orders[1]), "maybe")):  # a reply outside the schema: an error
            Path(o["reply"]).write_text(json.dumps({"winner": winner, "reason": "more thorough"}))
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("overall: alpha 1 - beta 0 - tie 0 - inconsistent 0 - invalid 1", r.stdout)
        self.assertFalse((self.out / listed).exists())
        self.assertEqual(json.loads(self.run_cli("summarize", str(self.out), "--json").stdout)
                         ["pairwise"]["alpha__beta"]["overall"]["a_wins"], 1)

    def test_recheck_rejudges_through_a_host_judge_between_calls(self):
        plan = self._judged_plan(question="is the output thorough?")
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "pass", "reason": "thorough"}')
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 0)
        before = self.results()
        self._judged_plan(question="is the output short?")
        r = self.run_cli("recheck", str(self.out), "--rejudge")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn(f"re-judged runs awaiting the host judge: 2 ({self.out / 'judge-dispatch.json'})", r.stdout)
        cells = self._dispatch("judge-dispatch.json")
        self.assertTrue(all("is the output short?" in Path(c["prompt"]).read_text() for c in cells))
        self.assertEqual(self.results(), before)  # the stored verdicts stay in force until every new one is in
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("being re-judged by the host judge", r.stderr)
        Path(cells[0]["reply"]).write_text('{"verdict": "fail", "reason": "long"}')
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 4)
        self.assertEqual(self.results(), before)
        self.assertEqual(self._dispatch("judge-dispatch.json"), cells[1:])
        Path(cells[1]["reply"]).write_text('{"verdict": "fail", "reason": "long"}')
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual({(v["judge"]["verdict"], v["passed"]) for v in self.results().values()}, {("fail", False)})
        self.assertFalse((self.out / "judge-dispatch.json").exists())
        # --judge naming another host judge re-judges by it, which becomes the directory's judge with its verdicts
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps({"executor": "host", "model": "second-judge"}))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "pass", "reason": "short enough"}')
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        self.assertEqual(json.loads((self.out / "plan.json").read_text())["judge"]["model"], "second-judge")
        self.assertEqual({(v["judge_identity"]["model"], v["passed"]) for v in self.results().values()},
                         {("second-judge", True)})
        # a reply outside the schema changes nothing and drops the re-judging, as a CLI judge giving no verdict does
        self.assertEqual(self.run_cli("recheck", str(self.out), "--rejudge").returncode, 4)
        before = self.results()
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "maybe", "reason": "hard to say"}')
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("nothing was changed", r.stderr)
        self.assertEqual(self.results(), before)
        self.assertEqual(list((self.out / "runs").glob("*.awaiting")), [])

    def test_a_marker_left_beside_a_finished_run_waits_on_nothing(self):
        plan = self._judged_plan()
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        markers = {path: path.read_bytes() for path in (self.out / "runs").glob("*.awaiting")}
        self.assertEqual(len(markers), 2)
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "pass", "reason": "ok"}')
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 0)
        for path, data in markers.items():  # as a finishing run leaves them that stops after writing result.json
            path.write_bytes(data)
        r = self.run_cli("run", str(plan), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("runs awaiting the host judge: 0", r.stdout)
        self.assertFalse((self.out / "judge-dispatch.json").exists())
        self.assertEqual(list((self.out / "runs").glob("*.awaiting")), [])
        for path, data in markers.items():  # nor does such a marker keep another judge from taking over
            path.write_bytes(data)
        judge = launcher_judge(self.judges, "m2", "echo '{\"verdict\": \"fail\", \"reason\": \"no\"}'\n")
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judge))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual({v["judge"]["verdict"] for v in self.results().values()}, {"fail"})

    def test_a_number_beyond_a_float_makes_a_host_record_or_judge_reply_unusable(self):
        plan = self._plan({"h": {"executor": "host", "host_env": True}})
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 4)
        entry = self._dispatch()[0]
        self._play_host(entry, "done\n", {}, task="echo hi > out.txt; faketool x")
        Path(entry["record"]).write_text('{"finished": true, "workspace": "direct", "seconds": 1e400}')
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("not valid JSON", next(l for l in r.stdout.splitlines() if l.startswith("make-file__h__r1\t")))
        self.assertEqual(self.results(), {})
        Path(entry["record"]).write_text('{"finished": true, "workspace": "direct", "seconds": 12.5}')
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        self.assertEqual(self.run_cli("report", str(self.out)).returncode, 0)
        self.out = self.tmp / "out-judge"
        plan = self._judged_plan()
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "pass", "reason": "ok", "score": 1e400}')
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 0)
        self.assertEqual({(v["judge"]["verdict"], v["passed"]) for v in self.results().values()}, {("error", None)})
        self.assertEqual(self.run_cli("report", str(self.out)).returncode, 0)

    def _judged_and_answered(self, plan, verdict="pass"):
        """Run a plan under a host judge to the end, every prompt answered with `verdict`."""
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 4)
        self._answer("judge-dispatch.json", lambda prompt: json.dumps({"verdict": verdict, "reason": "r"}))
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 0)

    def test_the_judge_cannot_change_while_a_host_rejudging_is_outstanding(self):
        plan = self._judged_plan()
        self._judged_and_answered(plan)
        self.assertEqual(self.run_cli("recheck", str(self.out), "--rejudge").returncode, 4)
        cells = self._dispatch("judge-dispatch.json")
        Path(cells[0]["reply"]).write_text('{"verdict": "fail", "reason": "by the first judge"}')  # one answered
        before = self.results()
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps({"executor": "host", "model": "judge-b"}))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("finish it", r.stderr)
        self.assertIn("new --out", r.stderr)
        self.assertEqual(self.results(), before)
        self.assertTrue(Path(cells[0]["reply"]).exists())  # the re-judging under way keeps its answer
        self.assertEqual(self.run_cli("run", str(plan), "--out", str(self.out)).returncode, 2)
        Path(cells[1]["reply"]).write_text('{"verdict": "fail", "reason": "by the first judge"}')
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        self.assertEqual({(v["judge_identity"]["model"], v["judge"]["verdict"]) for v in self.results().values()},
                         {("unknown", "fail")})

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap, for a confined default to differ from --sandbox none")
    def test_a_host_rejudging_keeps_the_sandbox_it_began_with(self):
        plan = self._judged_plan()
        self._judged_and_answered(plan)
        self.assertEqual({v["sandbox"] for v in self.results().values()}, {"confined"})
        self.assertEqual(self.run_cli("recheck", str(self.out), "--rejudge", "--sandbox", "none").returncode, 4)
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "fail", "reason": "r"}')
        r = self.run_cli("recheck", str(self.out))  # goes on as it began, with no flags of its own
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual({(v["sandbox"], v["judge"]["verdict"]) for v in self.results().values()}, {("none", "fail")})
        self.assertEqual(json.loads((self.out / "plan.json").read_text())["sandbox"], "none")

    def test_the_same_filtered_host_rejudge_command_resumes_it(self):
        for name in ("first", "second"):
            write(self.tmp / "scenarios" / name / "scenario.json", json.dumps({
                "prompt": "create out.txt", "judge": {"question": f"is the {name} output thorough?", "pass_when": "it is"}}))
        plan = self.tmp / "plan.json"
        write(plan, json.dumps({"name": "two", "repeats": 1, "sandbox": self.default_sandbox,
                                "arms": {"alpha": {"executor": "command", "command": "echo ALPHA_OUTPUT"}},
                                "judge": {"executor": "host"}, "scenarios": ["scenarios/first", "scenarios/second"]}))
        self._judged_and_answered(plan)
        command = ("recheck", str(self.out), "--rejudge", "--only", "first")
        self.assertEqual(self.run_cli(*command).returncode, 4)
        self.assertEqual(len(self._dispatch("judge-dispatch.json")), 1)  # only the selection is asked
        r = self.run_cli("recheck", str(self.out), "--rejudge", "--only", "second")
        self.assertEqual(r.returncode, 2)  # another selection while this one is under way
        self._answer("judge-dispatch.json", lambda prompt: '{"verdict": "fail", "reason": "r"}')
        r = self.run_cli(*command)  # the same command goes on with it
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.results()
        self.assertEqual((res["first__alpha__r1"]["judge"]["verdict"], res["second__alpha__r1"]["judge"]["verdict"]),
                         ("fail", "pass"))

    def test_a_host_pairwise_answer_counts_only_for_the_judge_it_was_asked_of(self):
        plan = self._judged_plan(question="which output is more thorough?")
        self._judged_and_answered(plan)
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        listed = "pairwise/alpha__beta/dispatch.json"
        orders = self._answer(listed, lambda prompt: json.dumps(
            {"winner": "1" if "ALPHA_OUTPUT" in prompt.split("</response_1>")[0] else "2", "reason": "first judge"}))
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta", "--judge-model", "second-judge")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)  # asked again: those answers were the first judge's
        now = self._dispatch(listed)  # the same orders, asked anew of the second judge
        self.assertEqual([(o["cell"], o["prompt"]) for o in now], [(o["cell"], o["prompt"]) for o in orders])
        self.assertFalse({o["reply"] for o in now} & {o["reply"] for o in orders})
        self.assertFalse(any(Path(o["reply"]).exists() for o in orders + now))
        self._answer(listed, lambda prompt: '{"winner": "tie", "reason": "second judge"}')
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta", "--judge-model", "second-judge")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        summary = json.loads((self.out / "pairwise" / "alpha__beta.json").read_text())
        self.assertEqual((summary["judge"]["model"], summary["overall"]["tie"]), ("second-judge", 1))

    def test_a_late_answer_from_a_replaced_host_judge_never_counts(self):
        plan = self._judged_plan(question="which output is more thorough?")
        self._judged_and_answered(plan)
        listed = "pairwise/alpha__beta/dispatch.json"
        self.assertEqual(self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta").returncode, 4)
        first = self._dispatch(listed)  # the first judge's questions, still unanswered
        self.assertEqual(self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta",
                                      "--judge-model", "second-judge").returncode, 4)
        for o in first:  # the first judge answers late, where it was told to
            Path(o["reply"]).write_text('{"winner": "1", "reason": "first judge, late"}')
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta", "--judge-model", "second-judge")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)  # still waiting on the second judge's own answers
        self.assertFalse((self.out / "pairwise" / "alpha__beta.json").exists())
        self.assertFalse({o["reply"] for o in first} & {o["reply"] for o in self._dispatch(listed)})

    def test_a_host_rejudging_by_another_judge_stops_when_a_check_breaks(self):
        plan = self._judged_plan()
        self._judged_and_answered(plan)
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps({"executor": "host", "model": "judge-b"}))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        cells = self._dispatch("judge-dispatch.json")
        Path(cells[0]["reply"]).write_text('{"verdict": "fail", "reason": "by judge b"}')  # one answered
        check = self.tmp / "scenarios" / "make-file" / "check.py"
        working = check.read_text()
        check.write_text("def check(run):\n    raise RuntimeError('broken')\n")
        before = self.results()
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)  # never one judge's verdicts beside another's
        self.assertEqual(self.results(), before)
        self.assertTrue((self.out / "rejudge.json").exists())
        check.write_text(working)  # fixed: the re-judging goes on as it began
        Path(cells[1]["reply"]).write_text('{"verdict": "fail", "reason": "by judge b"}')
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        self.assertEqual({v["judge_identity"]["model"] for v in self.results().values()}, {"judge-b"})

    def test_a_pairwise_judged_anew_withdraws_its_earlier_aggregate(self):
        plan = self._judged_plan(question="which output is more thorough?")
        self._judged_and_answered(plan)
        self.assertEqual(self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta").returncode, 4)
        self._answer("pairwise/alpha__beta/dispatch.json", lambda prompt: '{"winner": "tie", "reason": "even"}')
        self.assertEqual(self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta").returncode, 0)
        self.assertIn("pairwise", json.loads(self.run_cli("summarize", str(self.out), "--json").stdout))
        self._judged_plan(question="which output is shorter?")  # a new question: every pair is asked anew
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertNotIn("pairwise", json.loads(self.run_cli("summarize", str(self.out), "--json").stdout))
        self.assertNotIn("Pairwise comparisons", self.run_cli("summarize", str(self.out)).stdout)
        self.assertEqual(trial.report(self.out)["pairwise"], {})

    def test_a_launcher_judge_verdict_is_checked_against_the_whole_schema(self):
        # a verdict with a key the schema does not have; a winner with a numeric reason
        cli = launcher_judge(self.judges, "m", "case \"$prompt\" in *'<response_1>'*) echo '{\"winner\": \"1\", \"reason\": 5}' ;;"
                             " *) echo '{\"verdict\": \"pass\", \"reason\": \"ok\", \"score\": 9}' ;; esac\n")
        r = self.run_cli("run", str(self._judged_plan(judge=cli)), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for v in self.results().values():
            self.assertEqual((v["passed"], v["judge"]["verdict"]), (None, "error"))
            self.assertIn("score", v["judge"]["reason"])
        self.out = self.tmp / "out-pairwise"  # runs a pairwise judge can compare: judged by a judge that answers well
        self._judged_and_answered(self._judged_plan())
        stored = json.loads((self.out / "plan.json").read_text())
        write(self.out / "plan.json", json.dumps(dict(stored, judge=cli)))
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("invalid 1", r.stdout)

    def test_a_check_edited_within_the_same_second_runs_as_edited(self):
        check = self.tmp / "scenarios" / "make-file" / "check.py"
        write(check, "def check(run):\n    return {'version': 1}\n")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}  # a Python that caches bytecode
        cli = lambda *args: subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                                           timeout=300, env=env)
        plan = self._plan({"good": {"executor": "command", "command": "true"}})
        self.assertEqual(cli("run", plan, "--out", str(self.out)).returncode, 0)
        self.assertEqual(self.results()["make-file__good__r1"]["checks"], {"version": 1})
        self.assertFalse((check.parent / "__pycache__").exists())  # nothing cached for scenario code
        before = check.stat()  # the same size and the same modified second, as a quick edit can leave them
        check.write_text("def check(run):\n    return {'version': 2}\n")
        os.utime(check, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(cli("recheck", str(self.out)).returncode, 0)
        self.assertEqual(self.results()["make-file__good__r1"]["checks"], {"version": 2})

    def test_a_record_with_a_number_too_large_for_a_float_is_refused_without_stopping_the_runner(self):
        plan = self._plan({"good": {"executor": "host", "host_env": True}})
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 4)
        entry = self._dispatch()[0]
        self._play_host(entry, "done", {"finished": True, "usage": {"input_tokens": 10 ** 400, "output_tokens": 7}},
                        task="echo hi > out.txt; faketool x")
        r = self.run_cli("run", plan, "--out", str(self.out))  # the record is not one the runtime can read: it waits on
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)  # the host for one it can, and goes on with the rest
        self.assertIn("is not a finite number", r.stdout)
        self._play_host(entry, "done", {"finished": True, "usage": {"output_tokens": 7}})
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.results()["make-file__good__r1"]["usage"], {"output_tokens": 7})

    def test_names_that_would_share_or_leave_a_run_directory_are_refused_before_anything_is_written(self):
        # A run directory is runs/<scenario>__<arm>__r<repeat>: two scenarios of one name would share theirs, a "__"
        # inside a name lets two (scenario, arm) pairs spell the same one, and a slash or ".." would put it elsewhere.
        write(self.tmp / "scenarios" / "twin" / "scenario.json", json.dumps({"name": "make-file", "prompt": "x"}))
        write(self.tmp / "scenarios" / "escape" / "scenario.json", json.dumps({"name": "../../escaped", "prompt": "x"}))
        good = {"executor": "command", "command": "true"}
        for scenarios, arms, expected in (
                (["scenarios/make-file", "scenarios/twin"], {"good": good}, "both named 'make-file'"),
                (["scenarios/escape"], {"good": good}, "'../../escaped'"),
                (["scenarios/make-file"], {"b__c": good}, "'b__c'"),
                (["scenarios/make-file"], {"x/y": good}, "'x/y'"),
                (["scenarios/make-file"], {"trailing_": good}, "'trailing_'"),
                (["scenarios/make-file"], {".hidden": good}, "'.hidden'")):
            with self.subTest(expected=expected):
                write(self.tmp / "plan.json", json.dumps({"name": "names", "repeats": 1, "sandbox": self.default_sandbox,
                                                          "arms": arms, "scenarios": scenarios}))
                r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(expected, r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertFalse(self.out.exists())
                self.assertFalse(list(self.tmp.glob("escaped*")))
        # names in ordinary use keep working, a derived arm's "~" included
        write(self.tmp / "plan.json", json.dumps({"name": "names", "repeats": 1, "sandbox": self.default_sandbox,
                                                  "arms": {"gpt-5.5_low": good, "a~r1": good}, "scenarios": ["scenarios/make-file"]}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(self.results()), ["make-file__a~r1__r1", "make-file__gpt-5.5_low__r1"])

    def test_a_materials_digest_changes_with_anything_a_run_could_observe_of_it(self):
        # Each pair below is two different materials an arm can be given; each must get its own digest, so a run
        # directory never holds runs of both under one arm name.
        def tree(name, files=(), links=(), dirs=(), executable=()):
            root = self.tmp / "material" / name
            root.mkdir(parents=True)
            for rel, data in files:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(data)
                (root / rel).chmod(0o755 if rel in executable else 0o644)
            for rel, target in links:
                os.symlink(target, root / rel)
            for rel in dirs:
                (root / rel).mkdir(parents=True)
            return f"material/{name}"

        pairs = {
            "one file holding a NUL, or two files": (tree("joined", [("a", b"Xb\0Y")]), tree("split", [("a", b"X"), ("b", b"Y")])),
            "an executable bit": (tree("plain", [("run.sh", b"echo hi\n")]),
                                  tree("exec", [("run.sh", b"echo hi\n")], executable={"run.sh"})),
            "where a link leads": (tree("link-a", [("a", b"A"), ("b", b"B")], links=[("current", "a")]),
                                   tree("link-b", [("a", b"A"), ("b", b"B")], links=[("current", "b")])),
            "an empty directory": (tree("bare", [("a", b"A")]), tree("with-dir", [("a", b"A")], dirs=["drafts"])),
        }
        write(self.tmp / "material" / "plan.md", "the same words\n")
        write(self.tmp / "material" / "draft.md", "the same words\n")
        pairs["a single file's name"] = ("material/plan.md", "material/draft.md")
        for what, (first, second) in pairs.items():
            with self.subTest(what):
                plan = trial.load_plan(Path(self._plan({"first": {"executor": "artifact", "artifact": first},
                                                        "second": {"executor": "artifact", "artifact": second}})), None, None, None)
                self.assertNotEqual(plan["arms"]["first"]["artifact_sha256"], plan["arms"]["second"]["artifact_sha256"])
        # a link out of the material would reach whatever it leads to on the run's host, so it is refused
        escaping = tree("escaping", [("a", b"A")], links=[("outside", str(self.tmp / "plan.json"))])
        with self.assertRaisesRegex(trial.TrialError, "leads out of"):
            trial.load_plan(Path(self._plan({"x": {"executor": "artifact", "artifact": escaping}})), None, None, None)
        # material that changes after the plan loaded is refused when it is frozen, never frozen under the old digest
        plan = trial.load_plan(Path(self._plan({"x": {"executor": "artifact", "artifact": "material/plan.md"}})), None, None, None)
        write(self.tmp / "material" / "plan.md", "edited while the trial started\n")
        self.out.mkdir()
        with self.assertRaisesRegex(trial.TrialError, "arm 'x' artifact changed after the plan was loaded"):
            trial._snapshot_artifacts(plan, self.out)

    def test_artifacts_of_the_same_content_keep_their_own_file_names(self):
        write(self.tmp / "material" / "plan.md", "the same words\n")
        write(self.tmp / "material" / "draft.md", "the same words\n")
        write(self.tmp / "scenarios" / "named" / "scenario.json", json.dumps({"prompt": "read it", "artifact": "draft.md"}))
        write(self.tmp / "plan.json", json.dumps({
            "name": "names", "repeats": 1, "sandbox": self.default_sandbox, "scenarios": ["scenarios/named"],
            "arms": {"plan": {"executor": "artifact", "artifact": "material/plan.md"},
                     "draft": {"executor": "artifact", "artifact": "material/draft.md"}}}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(p.name for p in (self.out / "runs" / "named__draft__r1" / "work").iterdir()), ["draft.md"])
        self.assertEqual(sorted(p.name for p in (self.out / "runs" / "named__plan__r1" / "work").iterdir()), ["plan.md"])
        self.assertFalse(self.results()["named__draft__r1"].get("artifact_missing", False))

    def test_a_rerun_under_other_conditions_is_refused_rather_than_pooled_with_the_stored_runs(self):
        # Each change below alters what a run of the same arm on the same scenario would be given; a rerun into the
        # directory would otherwise return the stored runs and add new ones made under the new conditions.
        s = self.tmp / "scenarios" / "make-file"
        plan = str(self.tmp / "plan.json")

        def passes(names):
            data = json.loads(Path(plan).read_text())
            data["arms"]["good"]["pass_env"] = names
            Path(plan).write_text(json.dumps(data))
        changes = {
            "the prompt": (lambda: write(s / "scenario.json", json.dumps({"prompt": "create out.txt now", "required": ["made_file", "tool_called"]})), "scenario"),
            "the follow-ups": (lambda: write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "followups": ["more"], "required": ["made_file", "tool_called"]})), "scenario"),
            "the fixture": (lambda: write(s / "fixture" / "seed.txt", "another seed\n"), "scenario"),
            "the setup": (lambda: write(s / "setup.sh", "echo prepared differently > prepared.txt\n"), "scenario"),
            "a fake tool": (lambda: write(s / "bin" / "faketool", "#!/bin/sh\nexit 0\n", 0o755), "scenario"),
            "the environment variables the arm passes": (lambda: passes(["TRIAL_TEST_OTHER"]), "environment variables"),
            "the checks": (lambda: write(s / "check.py", "def check(run):\n    return {'made_file': True, 'tool_called': True}\n"), "recheck"),
            "the judge question": (lambda: write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file", "tool_called"], "judge": {"question": "q", "pass_when": "p"}, "judge_required": False})), "recheck"),
        }
        passes(["TRIAL_TEST_PASSED"])
        original = {p: p.read_bytes() for p in (s / "scenario.json", s / "fixture" / "seed.txt", s / "setup.sh", s / "bin" / "faketool",
                                                s / "check.py", Path(plan))}
        for what, (change, expected) in changes.items():
            with self.subTest(what):
                shutil.rmtree(self.out, ignore_errors=True)
                for path, data in original.items():
                    path.write_bytes(data)
                (s / "bin" / "faketool").chmod(0o755)
                r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "1")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                change()
                r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "2")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(expected, r.stderr)
                self.assertEqual(sorted(self.results()), ["make-file__bad__r1", "make-file__good__r1"])  # nothing new ran
        # a change of checks or judge question is settled by re-scoring the stored runs, after which the rerun goes on
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.results()), 4)

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap: compares a confined run with an unconfined one")
    def test_a_rerun_in_another_confinement_mode_is_refused(self):
        plan = str(self.tmp / "plan.json")
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out), "--repeats", "1", "--sandbox", "confined").returncode, 0)
        r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "2", "--sandbox", "none")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("sandbox", r.stderr)

    def test_a_host_job_awaiting_its_executor_is_held_to_the_conditions_it_was_prepared_under(self):
        plan = self._plan({"good": {"executor": "host", "host_env": True}})
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 4)
        write(self.tmp / "scenarios" / "make-file" / "fixture" / "seed.txt", "another seed\n")
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("scenario", r.stderr)

    def test_runs_that_record_no_conditions_are_never_resumed_into(self):
        plan = str(self.tmp / "plan.json")
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out), "--repeats", "1").returncode, 0)
        for path in (self.out / "runs").glob("*/result.json"):  # as a runtime that recorded no conditions wrote them
            r = json.loads(path.read_text())
            r.pop("conditions")
            path.write_text(json.dumps(r))
        r = self.run_cli("run", plan, "--out", str(self.out), "--repeats", "2")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("earlier trial.py", r.stderr)
        self.assertEqual(self.run_cli("summarize", str(self.out)).returncode, 0)  # its results still read as before

    def test_runs_of_one_arm_and_scenario_made_under_different_conditions_are_named_in_the_summary(self):
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        path = self.out / "runs" / "make-file__good__r2" / "result.json"
        r = json.loads(path.read_text())  # as a fixture edited while the trial ran leaves it
        r["conditions"]["scenario_sha256"] = "0" * 64
        path.write_text(json.dumps(r))
        summary = self.run_cli("summarize", str(self.out)).stdout
        self.assertIn("**Conditions**", summary)
        self.assertIn("make-file / good: scenario_sha256", summary)
        self.assertEqual(trial.report(self.out)["runs"][0]["conditions"].keys() >= {"scenario_sha256", "scoring_sha256"}, True)

    def test_a_run_whose_outcome_was_not_observed_is_invalid_and_one_observed_to_fail_fails(self):
        # Each arm leaves its run in one state; a run is passed or failed only when what decides it was observed.
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file", "tool_called"]}))
        write(s / "check.py", (
            "import os\n"
            "def check(run):\n"
            "    shape = run.file('shape.txt').strip()\n"
            "    if shape == 'missing':\n"
            "        return {'made_file': True}\n"
            "    if shape == 'unknown':\n"
            "        return {'made_file': True, 'tool_called': 'unknown'}\n"
            "    if shape == 'failed-and-missing':\n"
            "        return {'made_file': False}\n"
            "    return {'made_file': True, 'tool_called': True}\n"))
        record = lambda r: "printf '%s' '" + json.dumps(r) + "' > \"$TRIAL_RECORD\""
        arms = {
            "missing": "echo missing > shape.txt",
            "unknown": "echo unknown > shape.txt",
            "failed": "echo failed-and-missing > shape.txt",
            "uncommanded": record({"finished": True, "covers": ["command"], "actions": [{"kind": "command", "ok": True}]}),
            "unfinished": record({"finished": False, "limits": ["stopped before the end"]}),
        }
        plan = self._plan({name: {"executor": "command", "command": cmd} for name, cmd in arms.items()})
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = {v["arm"]: v for v in self.results().values()}
        report = {run["arm"]: run for run in trial.report(self.out)["runs"]}
        expected = {"missing": (None, "check-missing"), "unknown": (None, "check-missing"), "failed": (False, None),
                    "uncommanded": (None, "record-invalid"), "unfinished": (None, "unfinished")}
        for arm, (passed, reason) in expected.items():
            self.assertEqual((res[arm]["passed"], report[arm]["invalid_reason"]), (passed, reason), arm)
        self.assertEqual(res["missing"]["checks_missing"], ["tool_called"])
        summary = self.run_cli("summarize", str(self.out)).stdout
        self.assertIn("check-missing", summary)

    def test_an_unclear_verdict_is_unassessed_unless_the_scenario_counts_it_as_failing(self):
        s = self.tmp / "scenarios" / "make-file"
        judge = launcher_judge(self.judges, "unsure", "echo '{\"verdict\": \"unclear\", \"reason\": \"cannot tell\"}'\n")
        plan = self._plan({"good": {"executor": "command", "command": "echo hi > out.txt; faketool x"}}, judge)
        for unclear_fails, passed, reason in ((None, None, "judge-unclear"), (True, False, None)):
            with self.subTest(unclear_fails=unclear_fails):
                spec = {"prompt": "create out.txt", "required": ["made_file", "tool_called"],
                        "judge": {"question": "is it right?", "pass_when": "it is"}}
                if unclear_fails:
                    spec["unclear_fails"] = True
                write(s / "scenario.json", json.dumps(spec))
                shutil.rmtree(self.out, ignore_errors=True)
                self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
                result = self.results()["make-file__good__r1"]
                self.assertEqual((result["judge"]["verdict"], result["passed"]), ("unclear", passed))
                self.assertEqual(trial.report(self.out)["runs"][0]["invalid_reason"], reason)
                self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
                self.assertEqual(self.results()["make-file__good__r1"]["passed"], passed)

    def test_a_missing_deliverable_fails_and_a_judge_never_judges_what_it_cannot_read(self):
        s = self.tmp / "scenarios" / "make-file"
        asked = self.tmp / "asked.txt"
        judge = launcher_judge(self.judges, "reader", f"echo asked >> '{asked}'\necho '{{\"verdict\": \"pass\", \"reason\": \"fine\"}}'\n")
        write(s / "scenario.json", json.dumps({"prompt": "write report.md", "artifact": "report.md",
                                               "judge": {"question": "is the report sound?", "pass_when": "it is"}}))
        write(s / "check.py", "def check(run):\n    return {}\n")
        write(self.tmp / "material" / "notes.md", "Prices rise in spring.\n")
        write(self.tmp / "material" / "appendix.md", "Costs fall in autumn.\n")
        (self.tmp / "picture").mkdir()
        (self.tmp / "picture" / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR")
        write(self.tmp / "multi.json", json.dumps({"name": "multi", "repeats": 1, "sandbox": self.default_sandbox,
                                                   "scenarios": ["scenarios/plain"], "judge": judge,
                                                   "arms": {"text": {"executor": "artifact", "artifact": "material"},
                                                            "image": {"executor": "artifact", "artifact": "picture/chart.png"}}}))
        write(self.tmp / "scenarios" / "plain" / "scenario.json", json.dumps({
            "prompt": "You are judging a market note.", "judge": {"question": "is it sound?", "pass_when": "it is"}}))
        plan = self._plan({"none": {"executor": "command", "command": "true"},
                           "binary": {"executor": "command", "command": "printf 'PK\\003\\004\\000\\377' > report.md"}}, judge)
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        res = {v["arm"]: v for v in self.results().values()}
        self.assertEqual((res["none"]["passed"], res["none"]["artifact_missing"], res["none"]["judge"]), (False, True, None))
        self.assertEqual((res["binary"]["passed"], res["binary"]["judge"]), (None, None))
        self.assertIn("not text", res["binary"]["judge_unassessed"])
        self.assertFalse(asked.exists())  # neither run was put to the judge
        # an artifact arm's several files reach the judge whole, and one it cannot read is not judged
        out = self.tmp / "out-multi"
        r = self.run_cli("run", str(self.tmp / "multi.json"), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        multi = {p.parent.name: json.loads(p.read_text()) for p in (out / "runs").glob("*/result.json")}
        self.assertTrue(multi["plain__text__r1"]["passed"])
        prompt = (out / "judges" / ".cells" / multi["plain__text__r1"]["judge_cell"] / "judge" / "prompt.md").read_text()
        self.assertIn("Prices rise in spring.", prompt)
        self.assertIn("Costs fall in autumn.", prompt)
        self.assertIsNone(multi["plain__image__r1"]["passed"])
        self.assertEqual(trial.report(out)["runs"][0 if trial.report(out)["runs"][0]["arm"] == "image" else 1]["invalid_reason"],
                         "judge-unassessed")
        # with evidence of its own (a judge_context), the scenario gives the judge what it can read
        write(self.tmp / "scenarios" / "plain" / "check.py", "def check(run):\n    return {}\ndef judge_context(run):\n"
                                                             "    return 'A bar chart: sales double in spring.'\n")
        self.assertEqual(self.run_cli("recheck", str(out), "--rejudge").returncode, 0)
        multi = {p.parent.name: json.loads(p.read_text()) for p in (out / "runs").glob("*/result.json")}
        self.assertTrue(multi["plain__image__r1"]["passed"])

    def test_a_stored_verdict_counts_only_for_the_question_and_evidence_it_answered(self):
        s = self.tmp / "scenarios" / "make-file"
        spec = {"prompt": "create out.txt", "required": ["made_file", "tool_called"],
                "judge": {"question": "is it right?", "pass_when": "it is"}}
        write(s / "scenario.json", json.dumps(spec))
        checks = (s / "check.py").read_text()
        write(s / "check.py", checks + "def judge_context(run):\n    return 'the file says hi'\n")
        judge = launcher_judge(self.judges, "m", "echo '{\"verdict\": \"pass\", \"reason\": \"ok\"}'\n")
        plan = self._plan({"good": {"executor": "command", "command": "echo hi > out.txt; faketool x"}}, judge)
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        result = lambda: self.results()["make-file__good__r1"]
        self.assertIs(result()["passed"], True)
        stored_question = lambda: next(sp for sp in json.loads((self.out / "plan.json").read_text())["scenarios"])["judge"]
        for what, change in (("question", lambda: write(s / "scenario.json", json.dumps(dict(spec, judge={"question": "is it short?", "pass_when": "it is"})))),
                             ("evidence", lambda: write(s / "check.py", checks + "def judge_context(run):\n    return 'the file says bye'\n"))):
            with self.subTest(what):
                change()
                r = self.run_cli("recheck", str(self.out))  # keeps stored verdicts, but none for a question it was not asked
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual((result()["passed"], result().get("judge_stale")), (None, True))
                self.assertIn("judge-stale", r.stdout)
                r = self.run_cli("recheck", str(self.out), "--rejudge")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIs(result()["passed"], True)
                self.assertEqual(stored_question(), json.loads((s / "scenario.json").read_text())["judge"])  # as judged
        # a field taken out of scenario.json is gone from the scenario as rechecked and recorded, not kept from before
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file", "tool_called"]}))
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        self.assertIs(result()["passed"], True)
        self.assertNotIn("judge", next(iter(json.loads((self.out / "plan.json").read_text())["scenarios"])))
        # a scenario.json that cannot be read is an error, never a silent fall-back to the scenario as it was
        write(s / "scenario.json", "{not json")
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("is not valid JSON", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_pairwise_compares_valid_runs_and_withdraws_an_aggregate_whose_inputs_changed(self):
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["printed"],
                                               "judge": {"question": "which output is more thorough?", "pass_when": "it is"}}))
        # beta's second run fails its check; its third cannot be checked
        write(s / "check.py", "def check(run):\n"
                              "    if run.dir.name.endswith('__beta__r3'):\n        raise ValueError('cannot check')\n"
                              "    return {'printed': not run.dir.name.endswith('__beta__r2')}\n")
        judge = launcher_judge(self.judges, "j", "case \"$prompt\" in *'<response_1>'*) echo '{\"winner\": \"tie\", \"reason\": \"even\"}' ;;"
                               " *) echo '{\"verdict\": \"pass\", \"reason\": \"fine\"}' ;; esac\n")
        write(self.tmp / "plan.json", json.dumps({"name": "pw-valid", "repeats": 3, "sandbox": self.default_sandbox,
            "arms": {"alpha": {"executor": "command", "command": "echo ALPHA_OUTPUT"},
                     "beta": {"executor": "command", "command": "echo BETA_OUTPUT"}},
            "judge": judge, "scenarios": ["scenarios/make-file"]}))
        self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out)).returncode, 0)
        aggregate = lambda: json.loads((self.out / "pairwise" / "alpha__beta.json").read_text())
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((aggregate()["overall"]["pairs"], aggregate()["eligible"], aggregate()["left_out"]), (2, "valid", 1))
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta", "--passed-only")  # finalists alone
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((aggregate()["overall"]["pairs"], aggregate()["eligible"], aggregate()["left_out"]), (1, "passed", 2))
        self.assertIn("alpha__beta", json.loads(self.run_cli("summarize", str(self.out), "--json").stdout)["pairwise"])
        # re-scoring the runs it compared, or adding runs, withdraws it from the summary and the report until it is redone
        for change in (lambda: self.run_cli("recheck", str(self.out)),
                       lambda: self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "4")):
            change()
            self.assertNotIn("pairwise", json.loads(self.run_cli("summarize", str(self.out), "--json").stdout))
            self.assertIn("withheld", self.run_cli("summarize", str(self.out)).stdout)
            report = trial.report(self.out)
            self.assertEqual((report["pairwise"], report["pairwise_withheld"]), ({}, ["alpha__beta"]))
            self.assertEqual(self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta").returncode, 0)
            self.assertEqual(list(trial.report(self.out)["pairwise"]), ["alpha__beta"])
        # so does a changed judge question
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["printed"],
                                               "judge": {"question": "which output is shorter?", "pass_when": "it is"}}))
        self.assertEqual(trial.report(self.out)["pairwise_withheld"], ["alpha__beta"])

    def test_pruning_keeps_the_transcripts_a_record_names_and_the_deliverable_a_scenario_judges(self):
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "build the report", "required": ["report"],
                                               "artifact": "target/release/report.txt"}))
        write(s / "check.py", "def check(run):\n    return {'report': run.final_message.strip() == 'the report'}\n")
        record = {"finished": True, "transcripts": ["harness/home/.cache/agent/session.jsonl"], "limits": []}
        command = ("mkdir -p target/release \"$HOME/.cache/agent\" && printf 'Signature: 8a477f597d28d172789f06886806bc55\\n' > target/CACHEDIR.TAG"
                   " && echo 'the report' > target/release/report.txt && echo '{}' > \"$HOME/.cache/agent/session.jsonl\""
                   f" && printf '%s' '{json.dumps(record)}' > \"$TRIAL_RECORD\"")
        self.assertEqual(self.run_cli("run", self._plan({"a": {"executor": "command", "command": command}}), "--out", str(self.out)).returncode, 0)
        job = self.out / "runs" / "make-file__a__r1"
        self.assertTrue((job / "harness" / "home" / ".cache" / "agent" / "session.jsonl").is_file())  # the native record it names
        self.assertTrue((job / "work" / "target" / "release" / "report.txt").is_file())  # the deliverable it was judged on
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        result = self.results()["make-file__a__r1"]
        self.assertEqual((result["passed"], result.get("artifact_missing", False)), (True, False))

    def test_a_command_exit_the_arm_declares_an_outcome_is_scored_not_discarded(self):
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "build it", "required": ["built"]}))
        write(s / "check.py", "def check(run):\n    return {'built': run.exit_code == 0}\n")
        arms = {"declared": {"executor": "command", "command": "exit 1", "outcome_exits": [0, 1]},
                "undeclared": {"executor": "command", "command": "exit 1"},
                "crashed": {"executor": "command", "command": "exit 2", "outcome_exits": [0, 1]}}
        self.assertEqual(self.run_cli("run", self._plan(arms), "--out", str(self.out)).returncode, 0)
        res = {v["arm"]: v for v in self.results().values()}
        self.assertEqual((res["declared"]["status"], res["declared"]["exit_code"], res["declared"]["passed"]), ("ok", 1, False))
        self.assertEqual((res["undeclared"]["status"], res["undeclared"]["passed"]), ("exit-1", None))
        self.assertEqual((res["crashed"]["status"], res["crashed"]["passed"]), ("exit-2", None))
        r = self.run_cli("run", self._plan({"x": {"executor": "launcher", "script": "x.sh", "outcome_exits": [1]}}), "--dry-run")
        self.assertEqual(r.returncode, 2)
        self.assertIn("only a command arm reads", r.stderr)

    def test_scenario_setup_runs_confined_and_a_setup_that_never_ends_is_a_recorded_failure(self):
        s = self.tmp / "scenarios" / "make-file"
        leak = self.tmp / "leaked-by-setup"
        later = self.tmp / "written-after-setup"
        if shutil.which("bwrap"):  # confined, setup can write only its run, as the executor can
            write(s / "setup.sh", f"echo prepared > prepared.txt\ntouch '{leak}' 2>/dev/null\n(sleep 2; touch '{later}') &\n")
            self.assertEqual(self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1").returncode, 0)
            time.sleep(3)
            self.assertFalse(leak.exists())
            self.assertFalse(later.exists())  # what setup left running ended with it
            self.assertTrue(all(v["checks"]["setup_ran"] for v in self.results().values()))
        write(s / "setup.sh", "sleep 30\n")
        plan = trial.load_plan(self.tmp / "plan.json", 1, None, ["good"])
        out = self.tmp / "out-timeout"
        out.mkdir()
        with mock.patch.object(trial, "SETUP_TIMEOUT", 1):
            result = trial.run_job(plan, out, ("good", plan["scenarios"][0], 1))
        self.assertEqual((result["status"], result["passed"]), ("setup-failed", None))
        self.assertIn("timed out", result["setup_error"])
        self.assertEqual(json.loads((out / "runs" / "make-file__good__r1" / "result.json").read_text())["status"], "setup-failed")

    def test_what_every_attempt_and_judge_call_spent_is_counted(self):
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file", "tool_called"],
                                               "judge": {"question": "is it right?", "pass_when": "it is"}}))
        mark = self.tmp / "judge-mark"
        # the judge's first call on a run records what it spent and fails for a transient reason; its retry answers
        judge = launcher_judge(self.judges, "m", (
            f"if [ ! -e '{mark}' ]; then touch '{mark}'; printf '%s' '{{\"finished\": true, \"usage\": {{\"input_tokens\": 7, \"cost_usd\": 0.25}}}}' > \"$TRIAL_RECORD\"; exit 75; fi\n"
            "printf '%s' '{\"finished\": true, \"usage\": {\"input_tokens\": 5, \"cost_usd\": 0.5}}' > \"$TRIAL_RECORD\"\n"
            "echo '{\"verdict\": \"pass\", \"reason\": \"ok\"}'\n"))
        # the arm's first attempt fails, until the environment it passes says otherwise
        arm = {"executor": "command", "pass_env": ["TRIAL_TEST_UP"], "command":
               "printf '%s' '{\"finished\": true, \"usage\": {\"output_tokens\": 3}}' > \"$TRIAL_RECORD\"; "
               "[ -n \"$TRIAL_TEST_UP\" ] || exit 1; echo hi > out.txt; faketool x"}
        plan = self._plan({"a": arm}, judge)
        data = json.loads(Path(plan).read_text())
        data["sandbox"] = "none"  # the judge's mark outlives its first call's cell
        Path(plan).write_text(json.dumps(data))
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        self.assertIsNone(self.results()["make-file__a__r1"]["passed"])  # exit-1: invalid, and retried below
        r = subprocess.run([sys.executable, str(SCRIPT), "run", plan, "--out", str(self.out), "--retry-invalid"],
                           capture_output=True, text=True, timeout=300, env=dict(os.environ, TRIAL_TEST_UP="1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        result = self.results()["make-file__a__r1"]
        self.assertIs(result["passed"], True)
        self.assertEqual([(a["status"], a["usage"]) for a in result["attempts"]], [("exit-1", {"output_tokens": 3})])
        self.assertEqual(result["judge"]["usage"], {"input_tokens": 12, "cost_usd": 0.75})  # both of the judge's calls
        spent = trial.report(self.out)["arms"]["a"]["spent"]
        self.assertEqual((spent["attempts"], spent["usage_total"], spent["judge_usage_total"]),
                         (2, {"output_tokens": 6}, {"input_tokens": 12, "cost_usd": 0.75}))

    def test_executor_failures_at_one_effort_never_skip_the_runs_of_another(self):
        # The breaker stops an executor family that keeps failing; one model at two efforts is two families.
        plan = {"arms": {"low": {"executor": "launcher", "model": "m", "effort": "low", "script_sha256": "s"},
                         "high": {"executor": "launcher", "model": "m", "effort": "high", "script_sha256": "s"}}}
        spec = {"name": "make-file"}
        breaker = trial.FailureBreaker(3)
        for rep in (1, 2, 3):
            breaker.record(plan, ("low", spec, rep), {"status": "exit-1"})
        self.assertIn("failed 3 runs in a row", breaker.blocked(plan, ("low", spec, 4)))
        self.assertIsNone(breaker.blocked(plan, ("high", spec, 1)))


class ArmJudgeTest(unittest.TestCase):
    """An arm may name its own judge: each run is judged by its arm's judge, else by the plan's. Every test runs
    the command line against launcher judges whose pretend executables leave in their homes what they were asked
    and given."""

    def setUp(self):
        self.sandbox = "confined" if shutil.which("bwrap") else "none"
        self.tmp = Path(tempfile.mkdtemp(prefix="trial-test-", dir=Path.home() / ".cache"))
        # the judges' executables, installed apart from the plan's directory as a real executor's would be
        self.bin = Path(tempfile.mkdtemp(prefix="trial-judges-", dir=Path.home() / ".cache"))
        self.out = self.tmp / "out"
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps(
            {"prompt": "create out.txt", "judge": {"question": "is the output thorough?", "pass_when": "it is"}}))
        # every judge's launcher: it hands the prompt to the judge's executable, which answers on standard output
        write(self.tmp / "judge-launcher.sh", '#!/bin/sh\n[ "$TRIAL_TURN" = 0 ] && exit 0\nexec "$TRIAL_BINARY" < "$TRIAL_PROMPT_FILE"\n', 0o755)

    def tearDown(self):
        subprocess.run(["chmod", "-R", "u+rwx", str(self.tmp)], capture_output=True)
        subprocess.run(["rm", "-rf", str(self.tmp), str(self.bin)])

    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=300,
                              env=dict(os.environ, **(env or {})))

    def results(self, out=None):
        return {p.parent.name: json.loads(p.read_text()) for p in ((out or self.out) / "runs").glob("*/result.json")}

    def cell(self, result, out=None):
        """The directory a run's verdict was given in, looked up from its result.json as a person would."""
        return (out or self.out) / "judges" / ".cells" / result["judge_cell"] / "judge"

    def footprints(self):
        """What every judge call left in its cell: (cell, who.txt) for each cell a pretend judge was called in."""
        return sorted((c.parents[3].name, c.read_text().strip()) for c in (self.out / "judges" / ".cells").glob("*/judge/harness/home/who.txt"))

    def judge(self, name, verdict="pass", reason="fine", usage=(1, 1), reply=None, **settings):
        """A launcher judge on a pretend executable, model `name`, with an endpoint and a key of its own. It answers
        the probe's arithmetic correctly, a run with `verdict` and `reason` and `usage` input and output tokens (or with
        `reply` as it stands), and a pair of responses with a tie, and writes who.txt in its home: its name, the model
        it was asked for, and the endpoint and key it was given. Writing it again changes its answers, not its identity."""
        answer = reply if reply is not None else json.dumps({"verdict": verdict, "reason": reason})
        tie = json.dumps({"winner": "tie", "reason": "even"})
        record = json.dumps({"finished": True, "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
                             "limits": ["a pretend judge keeps no session record"]})
        write(self.bin / name, (
            "#!/bin/sh\n"
            "prompt=$(cat)\n"
            'eval "key=\\${$TRIAL_API_KEY_VAR}"\n'
            f"printf 'name={name} model=%s base=%s key=%s\\n' \"$TRIAL_MODEL\" \"$TRIAL_BASE_URL\" \"$key\" > \"$HOME/who.txt\"\n"
            'printf "%s" "$prompt" > "$HOME/prompt-seen.txt"\n'
            f"printf '%s' '{record}' > \"$TRIAL_RECORD\"\n"
            'case "$prompt" in\n'
            "  *'sum of 2 and 3'*) case \"$prompt\" in *' is 5.'*) echo '{\"verdict\": \"pass\", \"reason\": \"5\"}' ;;"
            " *) echo '{\"verdict\": \"fail\", \"reason\": \"not 5\"}' ;; esac ;;\n"
            f"  *'<response_1>'*) echo '{tie}' ;;\n"
            f"  *) echo '{answer}' ;;\n"
            "esac\n"), 0o755)
        var = "KEY_" + name.upper().replace("-", "_")
        write(self.tmp / f"{name}.env", f"{var}=key-of-{name}\n")
        return dict({"executor": "launcher", "script": str(self.tmp / "judge-launcher.sh"), "binary": str(self.bin / name),
                     "model": name, "base_url": f"http://{name}.invalid", "api_key_var": var,
                     "env_file": str(self.tmp / f"{name}.env")}, **settings)

    def arms(self, alpha=None, beta=None):
        """alpha and beta, command arms whose outputs name them, each with the judge given for it."""
        return {name: dict({"executor": "command", "command": f"echo {name.upper()}_OUTPUT"}, **({"judge": judge} if judge else {}))
                for name, judge in (("alpha", alpha), ("beta", beta))}

    def plan(self, arms, judge=None, repeats=2, name="armjudges"):
        plan = {"name": name, "repeats": repeats, "sandbox": self.sandbox, "scenarios": ["scenarios/make-file"], "arms": arms}
        if judge:
            plan["judge"] = judge
        write(self.tmp / f"{name}.json", json.dumps(plan))
        return str(self.tmp / f"{name}.json")

    def identity(self, name):
        sha = hashlib.sha256((self.tmp / "judge-launcher.sh").read_bytes()).hexdigest()
        return {"executor": "launcher", "model": name, "base_url": f"http://{name}.invalid", "script_sha256": sha}

    def test_each_run_is_judged_by_the_judge_of_its_arm(self):
        alpha = self.judge("judge-a", "pass", "a likes it", (11, 2))
        beta = self.judge("judge-b", "fail", "b dislikes it", (33, 4))
        r = self.run_cli("run", self.plan(self.arms(alpha, beta)), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.results()
        self.assertEqual(sorted(res), ["make-file__alpha__r1", "make-file__alpha__r2", "make-file__beta__r1", "make-file__beta__r2"])
        expected = {"alpha": ("pass", "a likes it", {"input_tokens": 11, "output_tokens": 2}, "judge-a", True),
                    "beta": ("fail", "b dislikes it", {"input_tokens": 33, "output_tokens": 4}, "judge-b", False)}
        for job, v in res.items():
            verdict, reason, usage, model, passed = expected[v["arm"]]
            self.assertEqual((v["judge"]["verdict"], v["judge"]["reason"], v["judge"]["usage"]), (verdict, reason, usage), job)
            self.assertEqual(v["judge_identity"], self.identity(model), job)
            self.assertIs(v["passed"], passed, job)
            # the judge was started as its arm's judge says: its binary, the model it names, its endpoint and its key
            self.assertEqual((self.cell(v) / "harness" / "home" / "who.txt").read_text().strip(),
                             f"name={model} model={model} base=http://{model}.invalid key=key-of-{model}", job)
        self.assertEqual(len({v["judge_cell"] for v in res.values()}), 4)
        stored = json.loads((self.out / "plan.json").read_text())
        self.assertEqual({n: a["judge"]["model"] for n, a in stored["arms"].items()}, {"alpha": "judge-a", "beta": "judge-b"})
        self.assertNotIn("judge", stored)

    def test_an_arm_without_a_judge_of_its_own_is_judged_by_the_plans(self):
        plan = self.plan(self.arms(alpha=self.judge("judge-a", "fail", "a says fail")), judge=self.judge("judge-p", "pass", "p says pass"))
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        for job, v in self.results().items():
            model, verdict, reason = ("judge-a", "fail", "a says fail") if v["arm"] == "alpha" else ("judge-p", "pass", "p says pass")
            self.assertEqual((v["judge"]["verdict"], v["judge"]["reason"], v["judge_identity"]), (verdict, reason, self.identity(model)), job)
            self.assertEqual(v["passed"], verdict == "pass", job)
            self.assertTrue((self.cell(v) / "harness" / "home" / "who.txt").read_text().startswith(f"name={model} "), job)

    def test_a_judged_scenario_with_no_judge_for_its_arm_is_judge_missing(self):
        plan = self.plan(self.arms(alpha=self.judge("judge-a")))  # beta names none, and the plan names none
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for job, v in self.results().items():
            if v["arm"] == "alpha":
                self.assertEqual((v["passed"], v["judge"]["verdict"]), (True, "pass"), job)
            else:  # invalid, never a silent pass
                self.assertEqual((v["passed"], v["judge"], v["judge_missing"]), (None, None, True), job)
                self.assertNotIn("judge_identity", v)
        self.assertIn("invalid 2: judge-missing", r.stdout)  # beta's two runs
        self.assertIn("| make-file | 2/2", r.stdout)  # alpha's
        self.assertIn("alpha: judge-a (launcher); beta: no judge.", r.stdout)
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)  # a recheck decides the same
        self.assertEqual(sorted(k for k, v in self.results().items() if v.get("judge_missing")), ["make-file__beta__r1", "make-file__beta__r2"])

    def test_a_rerun_with_an_arms_judge_changed_is_refused_naming_the_arm(self):
        alpha, beta = self.judge("judge-a"), self.judge("judge-b")
        self.assertEqual(self.run_cli("run", self.plan(self.arms(alpha, beta)), "--out", str(self.out)).returncode, 0)
        stamp = (self.out / "runs" / "make-file__alpha__r1" / "result.json").stat().st_mtime_ns
        self.assertEqual(self.run_cli("run", self.plan(self.arms(alpha, beta)), "--out", str(self.out)).returncode, 0)  # unchanged: reused
        self.assertEqual((self.out / "runs" / "make-file__alpha__r1" / "result.json").stat().st_mtime_ns, stamp)
        changed = self.plan(self.arms(alpha, dict(beta, model="judge-b2")))
        for dry in ([], ["--dry-run"]):
            r = self.run_cli("run", changed, "--out", str(self.out), *dry)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("arm 'beta' judge now has model judge-b2 (was judge-b)", r.stderr)
            self.assertIn("use a new --out", r.stderr)
            self.assertNotIn("arm 'alpha'", r.stderr)
        # beta is left out of this run, so it keeps its stored judge; alpha, which it does cover, is unchanged
        r = self.run_cli("run", changed, "--out", str(self.out), "--arms", "alpha")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads((self.out / "plan.json").read_text())["arms"]["beta"]["judge"]["model"], "judge-b")
        # a judge taken away, with no plan judge to fall back on, leaves its arm's verdicts without one
        r = self.run_cli("run", self.plan(self.arms(alpha)), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("the plan has no judge for arm 'beta', but", r.stderr)
        self.assertIn("holds judge verdicts", r.stderr)

    def test_the_plans_judge_is_held_to_the_runs_of_the_arms_without_a_judge_of_their_own(self):
        plan_judge = self.judge("judge-p")
        self.assertEqual(self.run_cli("run", self.plan(self.arms(), judge=plan_judge), "--out", str(self.out)).returncode, 0)
        # beta takes a judge of its own: its stored verdicts are the plan judge's, so that is a change of its judge
        r = self.run_cli("run", self.plan(self.arms(beta=self.judge("judge-b")), judge=plan_judge), "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("arm 'beta' judge now has model judge-b (was judge-p)", r.stderr)
        # a directory where alpha has its own judge: changing the plan's judge touches only beta's runs, and says so
        out = self.tmp / "out-mixed"
        mixed = self.arms(alpha=self.judge("judge-a"))
        self.assertEqual(self.run_cli("run", self.plan(mixed, judge=plan_judge), "--out", str(out)).returncode, 0)
        r = self.run_cli("run", self.plan(mixed, judge=dict(plan_judge, model="judge-p2")), "--out", str(out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("the judge now has model judge-p2 (was judge-p)", r.stderr)
        self.assertNotIn("arm 'alpha'", r.stderr)
        r = self.run_cli("run", self.plan(self.arms(alpha=self.judge("judge-a", model="judge-a2")), judge=plan_judge), "--out", str(out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("arm 'alpha' judge now has model judge-a2 (was judge-a)", r.stderr)
        # runs scored without a judge (judge-missing) keep an arm from taking one until they are judged
        out = self.tmp / "out-unjudged"
        self.assertEqual(self.run_cli("run", self.plan(self.arms(alpha=self.judge("judge-a"))), "--out", str(out)).returncode, 0)
        r = self.run_cli("run", self.plan(self.arms(alpha=self.judge("judge-a"), beta=self.judge("judge-b"))), "--out", str(out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("holds runs of arm 'beta' scored without a judge", r.stderr)

    def test_recheck_rejudge_asks_each_arms_own_judge(self):
        plan = self.plan(self.arms(self.judge("judge-a", "pass", "a likes it"), self.judge("judge-b", "fail", "b dislikes it")))
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        before = self.results()
        self.judge("judge-a", "pass", "a re-judged", (5, 1))  # the same judges, now answering differently
        self.judge("judge-b", "pass", "b re-judged", (7, 3))
        r = self.run_cli("recheck", str(self.out), "--rejudge")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("rechecked 4 runs", r.stdout)
        for job, v in self.results().items():
            reason, usage, model = (("a re-judged", {"input_tokens": 5, "output_tokens": 1}, "judge-a") if v["arm"] == "alpha"
                                    else ("b re-judged", {"input_tokens": 7, "output_tokens": 3}, "judge-b"))
            self.assertEqual((v["judge"]["reason"], v["judge"]["usage"], v["judge"]["judge_model"]), (reason, usage, model), job)
            self.assertEqual(v["judge_identity"], self.identity(model), job)
            self.assertNotEqual(v["judge_cell"], before[job]["judge_cell"], job)  # asked again, in a cell of its own
            self.assertTrue((self.cell(v) / "harness" / "home" / "who.txt").read_text().startswith(f"name={model} "), job)
            self.assertIs(v["passed"], True, job)  # beta's judge now passes what it failed
            # the earlier scoring stays on record, its verdict and the cell it was given in included
            earlier = v["history"][-1]
            self.assertEqual((earlier["judge"], earlier["judge_cell"], earlier["passed"]),
                             (before[job]["judge"], before[job]["judge_cell"], before[job]["passed"]), job)
            self.assertTrue(self.cell(earlier).is_dir(), job)
        self.assertEqual(len(self.footprints()), 8)  # every verdict's cell, the earlier ones kept
        plan_after = json.loads((self.out / "plan.json").read_text())
        self.assertEqual({n: a["judge"]["model"] for n, a in plan_after["arms"].items()}, {"alpha": "judge-a", "beta": "judge-b"})

    def test_a_verdict_is_stale_when_it_is_not_from_the_judge_of_its_arm(self):
        plan = self.plan(self.arms(alpha=self.judge("judge-a", "pass", "a likes it")), judge=self.judge("judge-p", "pass", "p likes it"))
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        self.assertEqual({v["passed"] for v in self.results().values()}, {True})
        # alpha's first verdict turns out to have come from some other judge; beta's, from the plan's judge, did not
        path = self.out / "runs" / "make-file__alpha__r1" / "result.json"
        path.write_text(json.dumps(dict(json.loads(path.read_text()), judge_identity=self.identity("judge-old"))))
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("invalid 1: judge-stale", r.stdout)
        self.assertEqual({k: (v["passed"], v.get("judge_stale", False)) for k, v in self.results().items()},
                         {"make-file__alpha__r1": (None, True), "make-file__alpha__r2": (True, False),
                          "make-file__beta__r1": (True, False), "make-file__beta__r2": (True, False)})
        # a re-judge asks alpha's own judge, not the plan's, and the run counts again
        self.judge("judge-a", "fail", "a changed its mind")
        self.assertEqual(self.run_cli("recheck", str(self.out), "--rejudge").returncode, 0)
        res = self.results()
        self.assertEqual((res["make-file__alpha__r1"]["passed"], res["make-file__alpha__r1"]["judge"]["reason"], res["make-file__alpha__r1"]["judge_identity"]),
                         (False, "a changed its mind", self.identity("judge-a")))
        self.assertEqual({v["judge"]["reason"] for k, v in res.items() if "__beta__" in k}, {"p likes it"})

    def test_recheck_judge_replaces_every_judge_and_drops_the_arms_own(self):
        alpha, beta = self.judge("judge-a", "pass", "a likes it"), self.judge("judge-b", "fail", "b dislikes it")
        plan = self.plan(self.arms(alpha, beta))
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        both = self.judge("judge-c", "pass", "c says pass")
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(both))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for job, v in self.results().items():
            self.assertEqual((v["judge"]["verdict"], v["judge"]["reason"], v["judge"]["judge_model"], v["judge_identity"], v["passed"]),
                             ("pass", "c says pass", "judge-c", self.identity("judge-c"), True), job)  # beta's runs turn from failed to passed
        stored = json.loads((self.out / "plan.json").read_text())
        self.assertEqual(stored["judge"]["model"], "judge-c")
        self.assertEqual({n: "judge" in a for n, a in stored["arms"].items()}, {"alpha": False, "beta": False})
        r = self.run_cli("run", plan, "--out", str(self.out))  # the plan as first written no longer fits the directory
        self.assertEqual(r.returncode, 2)
        self.assertIn("arm 'alpha' judge now has model judge-a (was judge-c)", r.stderr)
        self.judge("judge-c", "fail", "c now says fail")
        self.assertEqual(self.run_cli("recheck", str(self.out), "--rejudge").returncode, 0)  # every run goes to the one judge
        self.assertEqual({(v["judge"]["reason"], v["judge_identity"]["model"]) for v in self.results().values()}, {("c now says fail", "judge-c")})
        current = {v["judge_cell"] for v in self.results().values()}
        self.assertEqual({text.split()[0] for cell, text in self.footprints() if cell in current}, {"name=judge-c"})
        for v in self.results().values():  # each earlier verdict kept, in order: its arm's own judge's, then the first of c's
            self.assertEqual([h["judge_identity"]["model"] for h in v["history"]],
                             ["judge-a" if v["arm"] == "alpha" else "judge-b", "judge-c"], v["job"])

    def test_a_host_judge_on_an_arm_is_asked_of_that_arms_runs_only(self):
        beta = self.judge("judge-b", "fail", "b dislikes it")
        plan = self.plan(self.arms(alpha={"executor": "host"}, beta=beta))
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn(f"runs awaiting the host judge: 2 ({self.out / 'judge-dispatch.json'})", r.stdout)
        asked = json.loads((self.out / "judge-dispatch.json").read_text())
        self.assertEqual(len(asked), 2)  # alpha's two runs
        for entry in asked:
            prompt = Path(entry["prompt"]).read_text()
            self.assertIn("ALPHA_OUTPUT", prompt)
            self.assertNotIn("BETA_OUTPUT", prompt)
        # beta's runs were judged on the spot by beta's own launcher judge; alpha's wait, with no result yet
        self.assertEqual(sorted(self.results()), ["make-file__beta__r1", "make-file__beta__r2"])
        self.assertEqual({v["judge"]["reason"] for v in self.results().values()}, {"b dislikes it"})
        self.assertEqual([text.split()[0] for _, text in self.footprints()], ["name=judge-b"] * 2)
        # a judge changed while its arm's runs wait on it is refused, naming the arm
        waiting = self.plan(self.arms(alpha={"executor": "host", "model": "another"}, beta=beta), name="changed")
        r = self.run_cli("run", waiting, "--out", str(self.out))
        self.assertEqual(r.returncode, 2)
        self.assertIn("arm 'alpha' judge now has model another (was unknown)", r.stderr)
        self.assertIn("judge-dispatch.json", r.stderr)
        for entry in asked:
            Path(entry["reply"]).write_text('{"verdict": "pass", "reason": "a is thorough"}')
        beta_before = {k: (v["judge_cell"], (self.out / "runs" / k / "result.json").stat().st_mtime_ns)
                       for k, v in self.results().items()}
        footprints = self.footprints()
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.results()
        for job in ("make-file__alpha__r1", "make-file__alpha__r2"):
            self.assertEqual((res[job]["passed"], res[job]["judge_identity"]), (True, {"executor": "host", "model": "unknown"}), job)
        self.assertEqual({k: (v["judge_cell"], (self.out / "runs" / k / "result.json").stat().st_mtime_ns)
                          for k, v in res.items() if v["arm"] == "beta"}, beta_before)  # beta's judge was not asked again
        self.assertEqual(self.footprints(), footprints)
        # re-judging: the host judge is asked of alpha's runs, and beta's launcher judge waits until its replies are in
        self.judge("judge-b", "pass", "b re-judged")
        r = self.run_cli("recheck", str(self.out), "--rejudge")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        again = json.loads((self.out / "judge-dispatch.json").read_text())
        self.assertEqual(len(again), 2)
        self.assertTrue(all("ALPHA_OUTPUT" in Path(e["prompt"]).read_text() for e in again))
        state = json.loads((self.out / "rejudge.json").read_text())
        self.assertEqual((state["judge"], sorted(state["cells"]), state["arms"]["alpha"], state["arms"]["beta"]["model"]),
                         (None, ["make-file__alpha__r1", "make-file__alpha__r2"], {"executor": "host", "model": "unknown"}, "judge-b"))
        self.assertEqual(self.footprints(), footprints)  # beta's judge has not been called
        self.assertEqual({k: v["judge_cell"] for k, v in self.results().items() if v["arm"] == "beta"},
                         {k: cell for k, (cell, _) in beta_before.items()})
        for entry in again:
            Path(entry["reply"]).write_text('{"verdict": "fail", "reason": "a is not thorough"}')
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.out / "rejudge.json").exists() or (self.out / "judge-dispatch.json").exists())
        for job, v in self.results().items():
            reason, passed = ("a is not thorough", False) if v["arm"] == "alpha" else ("b re-judged", True)
            self.assertEqual((v["judge"]["reason"], v["passed"]), (reason, passed), job)
        # beta's judge was called once per run for this re-judge, in new cells; its earlier cells stay with its earlier
        # verdicts, which each run keeps in its history
        current = {v["judge_cell"] for v in self.results().values()}
        self.assertEqual([text.split()[0] for cell, text in self.footprints() if cell in current], ["name=judge-b"] * 2)
        self.assertEqual(sorted(cell for cell, _ in self.footprints() if cell not in current), sorted(c for c, _ in footprints))
        self.assertEqual({v["history"][-1]["judge"]["reason"] for v in self.results().values() if v["arm"] == "beta"}, {"b dislikes it"})

    def test_the_runtime_shows_each_arms_judge_when_arms_differ(self):
        alpha, beta = self.judge("judge-a"), self.judge("judge-b")
        plan = self.plan(self.arms(alpha, beta))
        dry = self.run_cli("run", plan, "--dry-run").stdout.splitlines()
        self.assertIn("arm judge\talpha\tlauncher\tjudge-a", dry)
        self.assertIn("arm judge\tbeta\tlauncher\tjudge-b", dry)
        self.assertFalse([line for line in dry if line.startswith("judge\t")])  # the plan names none of its own
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        summary = (self.out / "summary.md").read_text()
        self.assertIn("**Judges**: the arms were not all judged by one judge: alpha: judge-a (launcher); beta: judge-b (launcher). "
                      "Between arms judged by different judges, a difference may come from the judges as well as the arms.", summary)
        report = trial.report(self.out)["plan"]
        self.assertEqual((report["arms"]["alpha"]["judge"], report["arms"]["beta"]["judge"], report["judge"]),
                         (self.identity("judge-a"), self.identity("judge-b"), None))
        # one judge for every arm needs no such line
        same = self.tmp / "out-same"
        self.assertEqual(self.run_cli("run", self.plan(self.arms(), judge=alpha, name="same"), "--out", str(same)).returncode, 0)
        self.assertNotIn("**Judges**", (same / "summary.md").read_text())
        self.assertEqual([l for l in self.run_cli("run", str(self.tmp / "same.json"), "--dry-run").stdout.splitlines() if l.startswith("judge")],
                         ["judge\tlauncher\tjudge-a"])

    def test_an_arms_judge_is_validated_and_expanded_like_the_plans(self):
        arms = lambda judge: self.arms(alpha=judge)
        launcher = lambda **settings: dict({"executor": "launcher", "script": str(self.tmp / "judge-launcher.sh"), "model": "m"}, **settings)
        for judge, message in [({"executor": "cladue", "model": "m"}, "arm 'alpha' judge must be a JSON object with an executor and a model"),
                               ({"executor": "launcher"}, "arm 'alpha' judge must be a JSON object with an executor and a model"),
                               ({"executor": "claude", "model": "m"}, "valid judge executors: launcher, host"),
                               ({"executor": "host", "resources": {"rubric.md": "rubric.md"}}, "arm 'alpha' judge is a host judge"),
                               (launcher(env_file="missing.env"), "arm 'alpha' judge env_file"),
                               (launcher(resources={"../x": "rubric.md"}), "arm 'alpha' judge resources"),
                               (launcher(model="${TRIAL_TEST_UNSET}"), "arm 'alpha' judge model"),
                               (launcher(model="latest:judge-*"), "arm 'alpha' judge model latest:judge-*: name the model exactly")]:
            with self.subTest(message):
                r = self.run_cli("run", self.plan(arms(judge)), "--out", str(self.out))
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn(message, r.stderr)
                self.assertFalse(self.out.exists())  # refused when the plan loads
        # ${VAR} and ${VAR:-default} expand, and the expansion is what the directory records
        judge = self.judge("judge-a", model="${TRIAL_TEST_ARM_JUDGE:-judge-a}")
        self.assertEqual(self.run_cli("run", self.plan(arms(judge)), "--out", str(self.out), "--repeats", "1").returncode, 0)
        recorded = json.loads((self.out / "plan.json").read_text())["arms"]["alpha"]["judge"]
        self.assertEqual((recorded["model"], recorded["model_spec"]), ("judge-a", "${TRIAL_TEST_ARM_JUDGE:-judge-a}"))

    def test_an_arms_judge_gets_its_resources_read_only(self):
        write(self.tmp / "resources" / "rubric.md", "a rubric\n")
        judge = self.judge("judge-a")
        write(self.bin / "judge-a", Path(judge["binary"]).read_text() + 'cat "$HOME/notes/rubric.md" > "$HOME/rubric-seen.txt" 2>/dev/null || :\n', 0o755)
        judge["resources"] = {"notes/rubric.md": "resources/rubric.md"}
        plan = self.plan(self.arms(alpha=judge))
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out), "--repeats", "1").returncode, 0)
        v = self.results()["make-file__alpha__r1"]
        self.assertEqual((self.cell(v) / "harness" / "home" / "rubric-seen.txt").read_text(), "a rubric\n")
        copy = self.cell(v) / "harness" / "home" / "notes" / "rubric.md"
        self.assertEqual((copy.read_text(), copy.stat().st_mode & stat.S_IWUSR), ("a rubric\n", 0))  # read-only, as an arm's are

    def test_an_arms_judge_that_fails_its_probe_stops_the_trial_before_any_job_is_scheduled(self):
        judge = self.judge("judge-a", binary="judge-a")  # found on the PATH below
        write(self.bin / "judge-a", "#!/bin/sh\nexit 7\n", 0o755)  # an executable that never answers
        r = self.run_cli("run", self.plan(self.arms(alpha=judge)), "--out", str(self.out),
                         env={"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("the launcher probe refused this trial", r.stderr)
        self.assertIn("arm 'alpha' judge: launcher: question 1 gave no verdict", r.stderr)
        self.assertFalse(list(self.out.glob("runs/*")))  # nothing was scheduled

    def test_a_failing_arm_judge_stops_only_the_runs_it_would_decide(self):
        broken = self.judge("judge-a", reply="not a verdict")
        working = self.judge("judge-b", "pass", "fine")
        plan = self.plan(self.arms(broken, working), repeats=6)
        r = self.run_cli("run", plan, "--out", str(self.out), "--jobs", "1", env={"TRIAL_FAILURE_STREAK": "3"})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)  # runs were skipped
        self.assertIn("runs skipped", r.stderr)
        self.assertIn("failed 3 runs in a row", r.stdout)
        res = self.results()
        self.assertEqual(sorted(k for k in res if "__alpha__" in k), [f"make-file__alpha__r{n}" for n in (1, 2, 3)])
        self.assertEqual(sorted(k for k in res if "__beta__" in k), [f"make-file__beta__r{n}" for n in range(1, 7)])
        self.assertEqual({v["judge"]["verdict"] for k, v in res.items() if "__alpha__" in k}, {"error"})
        self.assertEqual({v["passed"] for k, v in res.items() if "__beta__" in k}, {True})
        self.judge("judge-a", "pass", "fixed")  # the cause is fixed
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out), "--retry-invalid", "--jobs", "1").returncode, 0)
        self.assertEqual({v["passed"] for v in self.results().values()}, {True})
        self.assertEqual(len(self.results()), 12)

    def test_two_arm_judges_that_differ_only_in_effort_count_their_failures_apart(self):
        # The same model at the same endpoint, at two efforts: two judges, and one's errors stop none of the other's runs.
        broken = self.judge("judge-a", reply="not a verdict", effort="high")
        working = self.judge("judge-a-low", "pass", "fine", model="judge-a", base_url="http://judge-a.invalid", effort="low")
        plan = self.plan(self.arms(broken, working), repeats=6)
        r = self.run_cli("run", plan, "--out", str(self.out), "--jobs", "1", env={"TRIAL_FAILURE_STREAK": "3"})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("the judge judge-a (launcher) failed 3 runs in a row", r.stdout)
        res = self.results()
        self.assertEqual(sorted(k for k in res if "__alpha__" in k), [f"make-file__alpha__r{n}" for n in (1, 2, 3)])
        self.assertEqual({v["passed"] for k, v in res.items() if "__beta__" in k}, {True})
        self.assertEqual(len([k for k in res if "__beta__" in k]), 6)

    def test_a_plan_judge_that_no_arm_uses_is_not_probed(self):
        unused = self.judge("judge-p")
        write(self.bin / "judge-p", "#!/bin/sh\nexit 7\n", 0o755)  # what the plan's judge would answer with
        plan = self.plan(self.arms(self.judge("judge-a"), self.judge("judge-b")), judge=unused)
        r = self.run_cli("run", plan, "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual({v["arm"]: v["judge_identity"]["model"] for v in self.results().values()}, {"alpha": "judge-a", "beta": "judge-b"})

    def test_pairwise_keeps_using_the_plans_judge(self):
        plan = self.plan(self.arms(self.judge("judge-a"), self.judge("judge-b")), judge=self.judge("judge-p"))
        self.assertEqual(self.run_cli("run", plan, "--out", str(self.out)).returncode, 0)
        r = self.run_cli("pairwise", str(self.out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads((self.out / "pairwise" / "alpha__beta.json").read_text())["judge"]["model"], "judge-p")
        cells = list((self.out / "pairwise" / ".cells").glob("*/order-*/harness/home/who.txt"))
        self.assertEqual(len(cells), 4)  # both orders of two pairs
        self.assertEqual({c.read_text().split()[0] for c in cells}, {"name=judge-p"})
        # with no plan judge there is none for pairwise to use, whatever the arms name
        out = self.tmp / "out-arms-only"
        self.assertEqual(self.run_cli("run", self.plan(self.arms(self.judge("judge-a"), self.judge("judge-b")), name="arms-only"),
                                      "--out", str(out)).returncode, 0)
        r = self.run_cli("pairwise", str(out), "--arms", "alpha,beta")
        self.assertEqual(r.returncode, 2)
        self.assertIn("has no judge in its plan.json", r.stderr)
        self.assertIn("an arm's judge does not apply", r.stderr)


if __name__ == "__main__":
    unittest.main()
