"""Behavior of the trial runner, exercised with the deterministic command executor."""
import json
import os
import shutil
import stat
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
        subprocess.run(["chmod", "-R", "u+rwx", str(self.tmp)], capture_output=True)
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=300)

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
        # Confined where bubblewrap exists; hosts without it (CI runners) exercise the same proxy path unconfined.
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), sandbox="confined" if shutil.which("bwrap") else "workspace-write")))
        write(self.tmp / "plan.json", json.dumps({"name": "claude", "repeats": 1, "scenarios": ["scenarios/make-file"],
            "arms": {"c": {"executor": "claude", "model": "m", "binary": str(fake), "base_url": "http://proxy.invalid",
                           "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}}}))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.results()["make-file__c__r1"]
        self.assertEqual(res["checks"]["seen"], "http://proxy.invalid set")
        self.assertEqual(res["checks"]["final"], "all done")
        self.assertEqual(res["usage"].get("output_tokens"), 3)

    def test_recheck_with_another_judge_replaces_verdicts(self):
        s = self.tmp / "scenarios" / "make-file" / "scenario.json"
        s.write_text(json.dumps(dict(json.loads(s.read_text()), judge={"question": "q?", "pass_when": "it passes"})))
        self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "1")
        self.assertTrue(self.results()["make-file__good__r1"]["passed"])
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
        run = trial.Run(job, "ok")
        self.assertIn("f", run.git("status", "--porcelain"))
        self.assertEqual(run.git_rc("rev-parse", "--is-inside-work-tree"), 0)
        self.assertFalse(marker.exists())

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

    @unittest.skipUnless(shutil.which("bwrap"), "needs bubblewrap")
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
                    f"ln -s {victims}/events.jsonl events.jsonl\n", 0o755)
        env_file = self.tmp / "keys.env"
        env_file.write_text("TRIAL_TEST_KEY=not-a-real-key\n")
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "go", "followups": ["again"], "required": [],
                                               "sandbox": "confined" if shutil.which("bwrap") else "workspace-write",
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
                        "echo '{\"structured_output\": {\"verdict\": \"pass\", \"reason\": \"ok\"}}'\n", 0o755)
            judges[name] = {"executor": "claude", "model": name, "binary": str(fake), "base_url": "http://proxy.invalid",
                            "api_key_var": "TRIAL_TEST_KEY", "env_file": str(env_file)}
        made = "echo hi > out.txt; faketool x"
        leave = (made + "; cd .. && mkdir result.json final-0.md && mkdir -p judge/locked judge.next/locked && "
                 "touch judge/locked/f judge.next/locked/f && chmod 000 judge/locked judge.next/locked && "
                 "mkdir home && touch home/models_cache.json && chmod 500 home && chmod 500 .")
        plan = self._plan({"leave": {"executor": "command", "command": leave}, "plain": {"executor": "command", "command": made}},
                          judges["j1"])
        r = self.run_cli("run", plan, "--out", str(self.out), "--jobs", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.out / "summary.md").exists())
        self.assertEqual({k: v["passed"] for k, v in self.results().items()}, {"make-file__leave__r1": True, "make-file__plain__r1": True})
        self.assertEqual(self.run_cli("recheck", str(self.out), "--judge", json.dumps(judges["j2"])).returncode, 0)
        before = {k: v["judge_identity"]["model"] for k, v in self.results().items()}
        self.assertEqual(set(before.values()), {"j2"})
        flag.write_text("")
        r = self.run_cli("recheck", str(self.out), "--rejudge")
        self.assertEqual(r.returncode, 2)
        self.assertIn("judge_context: KeyError: 'boom'", r.stderr)
        self.assertIn("nothing was changed", r.stderr)
        self.assertTrue((self.out / "runs" / "make-file__plain__r1" / "judge" / "verdict.json").is_file())
        self.assertEqual({k: v["passed"] for k, v in self.results().items()}, {"make-file__leave__r1": True, "make-file__plain__r1": True})

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
        plan = {"name": "p", "repeats": 1, "scenarios": ["scenarios/make-file"], "arms": arms}
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
        verdict = self.out / "runs" / "make-file__good__r1" / "judge" / "verdict.json"
        self.assertTrue(verdict.exists())
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(judges["broken"]))
        self.assertEqual(r.returncode, 2)
        self.assertIn("nothing was changed", r.stderr)
        self.assertEqual(json.loads((self.out / "plan.json").read_text())["judge"]["model"], "works")
        self.assertTrue(verdict.exists() and self.results()["make-file__good__r1"]["passed"])
        self.assertFalse((verdict.parent.parent / "judge.next").exists())
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


if __name__ == "__main__":
    unittest.main()
