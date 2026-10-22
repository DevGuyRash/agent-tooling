"""Launcher arms and judges (see references/launching.md), exercised through the CLI with a pretend agent launcher."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "trial.py"
FAKE = Path(__file__).resolve().parent / "fake_launcher.py"
sys.path.insert(0, str(SCRIPT.parent))
import trial  # noqa: E402

CONFINED = bool(shutil.which("bwrap"))


def write(path: Path, text: str, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mode:
        path.chmod(mode)


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="launcher-test-", dir=Path.home() / ".cache"))
        self.sandbox = "confined" if CONFINED else "none"
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "followups": ["anything else?"],
                                               "required": ["made_file", "tool_called"]}))
        write(s / "fixture" / "seed.txt", "seed\n")
        write(s / "bin" / "faketool", '#!/bin/sh\necho "{\\"tool\\": \\"faketool\\"}" >> "$TRIAL_HARNESS/calls.jsonl"\n', 0o755)
        write(s / "check.py", (
            "def check(run):\n"
            "    return {'made_file': run.file('out.txt').strip() == 'hi',\n"
            "            'tool_called': any(c.get('tool') == 'faketool' for c in run.calls),\n"
            "            'commands': len(run.commands)}\n"))
        write(self.tmp / "launcher.py", FAKE.read_text(), 0o755)
        write(self.tmp / "arms" / "note.md", "Be brief.\n")
        write(self.tmp / "skills" / "helper" / "SKILL.md",
              "---\nname: helper\ndescription: Helps with things.\n---\n"
              "This helper skill line is long enough to identify the skill by its content alone.\n")
        self.out = self.tmp / "out"

    def tearDown(self):
        subprocess.run(["chmod", "-R", "u+rwx", str(self.tmp)], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def arm(self, **extra):
        return {"executor": "launcher", "script": "launcher.py", "model": "pretend-1", "effort": "low",
                "instructions": "arms/note.md", "pass_env": ["FAKE_LAUNCHER_MODE", "FAKE_LAUNCHER_MARK"], **extra}

    def plan(self, arms, **extra):
        plan = {"name": "launch", "repeats": 1, "seed": 1, "sandbox": self.sandbox, "arms": arms,
                "scenarios": ["scenarios/make-file"], **extra}
        write(self.tmp / "plan.json", json.dumps(plan))

    def run_cli(self, *args, mode="", **env):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=600,
                              env=dict(os.environ, FAKE_LAUNCHER_MODE=mode, **env))

    def run_plan(self, mode="", **env):
        return self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), mode=mode, **env)

    def result(self, arm="a", scenario="make-file"):
        return json.loads((self.out / "runs" / f"{scenario}__{arm}__r1" / "result.json").read_text())

    def test_a_launcher_arm_runs_every_turn_confined_and_is_scored_from_its_record(self):
        self.plan({"a": self.arm(resources={"skills/helper": "skills/helper"}, watch=["~/.fake/settings.json"])})
        r = self.run_plan()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("passed", r.stdout.split("run directory")[0])  # the probe passed before any run
        res = self.result()
        self.assertTrue(res["passed"], res)
        self.assertEqual(res["checks"]["commands"], 1)
        self.assertEqual(res["usage"], {"input_tokens": 200, "cached_input_tokens": 80, "output_tokens": 20})
        self.assertEqual(res["usage_basis"], "shared")
        self.assertEqual(res["observed_model"], "pretend-1")
        self.assertEqual(res["exposure"], {"skills/helper": False})
        self.assertEqual(res["identity"]["watch"], ["~/.fake/settings.json"])
        self.assertTrue(res["identity"]["script_sha256"])
        run_dir = self.out / "runs" / "make-file__a__r1"
        self.assertTrue((run_dir / "final-0.md").exists() and (run_dir / "final-1.md").exists())
        self.assertFalse((run_dir / "turns").exists())  # each turn's message file is gone once the turn ends
        state = json.loads((run_dir / "harness" / "home" / ".fake" / "state.json").read_text())
        self.assertEqual({t["cwd"] for t in state["turns"]}, {str(run_dir / "work")})  # the run keeps its own path

    def test_the_probe_refuses_a_launcher_that_drops_instructions_forgets_turns_or_keeps_no_record(self):
        self.plan({"a": self.arm()})
        for mode, expected in (("drop-instructions", "code word"), ("fresh", "follow-up reports another session"),
                               ("no-record", "no record at"), ("no-transcripts", "names no native record")):
            with self.subTest(mode=mode):
                shutil.rmtree(self.out, ignore_errors=True)
                r = self.run_plan(mode)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("the launcher probe refused this trial", r.stderr)
                self.assertIn(expected, r.stderr)
                self.assertFalse((self.out / "runs").exists())  # no trial run was started

    def test_the_probe_asks_only_what_the_scenarios_need(self):
        # A scenario with no follow-ups and no workspace: a launcher that cannot continue a session still qualifies.
        s = self.tmp / "scenarios" / "talk"
        write(s / "scenario.json", json.dumps({"prompt": "say hello", "required": []}))
        write(s / "check.py", "def check(run):\n    return {}\n")
        self.plan({"a": self.arm()}, scenarios=["scenarios/talk"])
        r = self.run_plan("fresh")
        self.assertEqual(r.returncode, 0, r.stderr)
        probe = next((self.out / "probes").glob("a*/probe.json"))
        self.assertTrue(json.loads(probe.read_text())["passed"])
        run = probe.parent / "attempt-1" / "run"
        self.assertTrue((run / "final-0.md").exists())
        self.assertFalse((run / "final-1.md").exists())  # no second turn without follow-ups
        self.assertFalse((run / "work" / "probe.txt").exists())  # no file step without a workspace

    def test_a_turn_that_changes_watched_configuration_invalidates_its_run(self):
        self.plan({"a": self.arm(watch=["~/.fake/settings.json"])})
        r = self.run_plan("change-watched")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.result()
        self.assertEqual(res["status"], "config-changed")
        self.assertIsNone(res["passed"])
        self.assertIn("changed watched configuration", (self.out / "runs" / "make-file__a__r1" / "stderr.log").read_text())

    def test_a_run_whose_executor_reports_another_model_is_invalid(self):
        self.plan({"a": self.arm()})
        r = self.run_plan("other-model")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.result()["status"], "model-changed")

    def test_a_transient_exit_retries_the_run_fresh(self):
        # Unconfined, so the mark the launcher leaves on its first attempt outlives that attempt's run directory.
        self.plan({"a": self.arm()}, sandbox="none")
        r = self.run_plan("transient-once", FAKE_LAUNCHER_MARK=str(self.tmp / "mark"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.result()["passed"])
        self.assertEqual(self.result()["confined"], False)
        # the attempt it replaced is kept, and what it cost counts toward what the arm spent
        attempts = self.result()["attempts"]
        self.assertEqual([a["status"] for a in attempts], ["exit-75"])
        self.assertTrue((self.out / attempts[0]["dir"] / "result.json").is_file())
        spent = json.loads(self.run_cli("summarize", str(self.out), "--json").stdout)["arms"]["a"]["spent"]
        self.assertEqual(spent["attempts"], 2)
        # the run's own usage is its two turns' (see fake_launcher.py); the attempt that exited 75 recorded none
        self.assertEqual(spent["usage_total"], {"input_tokens": 200, "cached_input_tokens": 80, "output_tokens": 20})
        self.assertIn("Spent", self.run_cli("summarize", str(self.out)).stdout)

    def test_exposure_comes_from_reads_loads_and_identifying_output(self):
        resources = {"skills/helper": "skills/helper"}
        self.plan({"a": self.arm(resources=resources)})
        for mode, expected in (("read-skill", True), ("cat-skill", True), ("load-skill-failed", False), ("limited", None)):
            with self.subTest(mode=mode):
                shutil.rmtree(self.out, ignore_errors=True)
                r = self.run_plan(mode)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.result()["exposure"], {"skills/helper": expected})

    def test_a_check_asking_for_actions_the_record_does_not_cover_makes_the_run_invalid(self):
        self.plan({"a": self.arm()})
        r = self.run_plan("limited")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.result()
        self.assertIsNone(res["passed"])
        self.assertIn("does not cover the commands", res["checks"]["check_error"])
        self.assertIsNone(res["commands"])

    def test_a_launcher_judge_gives_its_verdict_only_on_standard_output(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "required": ["made_file"],
            "judge": {"question": "Did it report make-file done?", "pass_when": "it does"}}))
        judge = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge", "pass_env": ["FAKE_LAUNCHER_MODE"]}
        self.plan({"a": self.arm()}, judge=judge)
        r = self.run_plan()
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.result()
        self.assertEqual(res["judge"]["verdict"], "pass", res)
        self.assertEqual(res["judge_identity"]["script_sha256"], res["identity"]["script_sha256"])
        for mode, expected in (("judge-forge", "wrote forged-verdict.json"), ("judge-two", "gave no verdict")):
            with self.subTest(mode=mode):
                shutil.rmtree(self.out, ignore_errors=True)
                r = self.run_plan(mode)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn(expected, r.stderr)

    def test_a_changed_launcher_or_watch_list_needs_a_new_run_directory(self):
        self.plan({"a": self.arm()})
        self.assertEqual(self.run_plan().returncode, 0)
        write(self.tmp / "launcher.py", FAKE.read_text() + "\n# changed\n", 0o755)
        r = self.run_plan()
        self.assertEqual(r.returncode, 2)
        self.assertIn("different script", r.stderr)
        write(self.tmp / "launcher.py", FAKE.read_text(), 0o755)
        self.plan({"a": self.arm(watch=["~/.fake/settings.json"])})
        r = self.run_plan()
        self.assertEqual(r.returncode, 2)
        self.assertIn("watch", r.stderr)

    def test_a_rerun_whose_executable_changed_is_refused(self):
        # an executor that updates itself between two calls of the same plan is another executor
        install = Path(tempfile.mkdtemp(prefix="launcher-install-", dir=Path.home() / ".cache"))
        self.addCleanup(shutil.rmtree, install, True)
        write(install / "versions" / "1.0" / "agent", "#!/bin/sh\necho 1.0\n", 0o755)
        os.symlink(install / "versions" / "1.0" / "agent", install / "agent")
        self.plan({"a": self.arm(binary=str(install / "agent"))})
        self.assertEqual(self.run_plan().returncode, 0)
        write(install / "versions" / "1.1" / "agent", "#!/bin/sh\necho 1.1\n", 0o755)
        (install / "agent").unlink()
        os.symlink(install / "versions" / "1.1" / "agent", install / "agent")
        r = self.run_plan()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("arm 'a' now starts a different binary", r.stderr)
        # so is one that copies other configuration into its home
        write(self.tmp / "sign-in", "a sign-in\n")
        self.out = self.tmp / "out-copy"
        self.plan({"a": self.arm()})
        self.assertEqual(self.run_plan().returncode, 0)
        self.plan({"a": self.arm(copy={".fake-sign-in": "sign-in"})})
        r = self.run_plan()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("arm 'a' now copies different files into its home", r.stderr)
        # and so is one that copies to the same place from another file
        write(self.tmp / "other-sign-in", "another sign-in\n")
        self.out = self.tmp / "out-copy-source"
        self.assertEqual(self.run_plan().returncode, 0)
        self.plan({"a": self.arm(copy={".fake-sign-in": "other-sign-in"})})
        r = self.run_plan()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("arm 'a' now copies different files into its home", r.stderr)

    def test_a_launcher_names_its_model_exactly(self):
        self.plan({"a": self.arm(model="latest:pretend-*")})
        r = self.run_plan()
        self.assertEqual(r.returncode, 2)
        self.assertIn("name the model exactly", r.stderr)
        ids = self.tmp / "ids.txt"
        ids.write_text("pretend-1\npretend-1.10\npretend-1.9\npretend-1.10-mini\n")
        r = self.run_cli("latest", "pretend-*", str(ids))
        self.assertEqual(r.stdout.strip(), "pretend-1.10")

    @unittest.skipUnless(CONFINED and os.access("/var/tmp", os.W_OK), "needs bubblewrap and a writable /var/tmp")
    def test_a_confined_launcher_sees_no_trial_input_and_no_file_above_its_run(self):
        planted = Path.home() / ".cache" / f"{self.tmp.name}-planted"
        planted.write_text("secret")
        self.addCleanup(planted.unlink)
        above = Path(tempfile.mkdtemp(prefix="launcher-above-", dir="/var/tmp"))  # outside the home and /tmp
        self.addCleanup(shutil.rmtree, above, True)
        write(above / "AGENTS.md", "instructions above the run\n")
        write(above / ".settings" / "config.json", "{}\n")
        scenario = above / "scenario"
        write(scenario / "check.py", "visible?\n")
        other_scenario = above / "other-scenario"  # another scenario of the plan, also outside the home
        write(other_scenario / "check.py", "visible?\n")
        elsewhere = Path(tempfile.mkdtemp(prefix="launcher-elsewhere-", dir="/var/tmp"))
        self.addCleanup(shutil.rmtree, elsewhere, True)
        write(elsewhere / "real.md", "instructions through a link\n")
        write(elsewhere / "dotdir" / "config.json", "{}\n")
        os.symlink(elsewhere / "real.md", above / "CLAUDE.md")
        os.symlink(elsewhere / "dotdir", above / ".linked")
        system_file = Path("/usr/lib/os-release")  # a file where executables and libraries live, linked as instructions
        if system_file.is_file() and system_file.stat().st_size:
            os.symlink(system_file, above / "GEMINI.md")
        out = above / "out"
        look = self.tmp / "look.sh"
        # Trial inputs and the home are absent; a file above the run may still be named there, but holds nothing.
        absent = [str(planted), str(self.tmp / "plan.json"), str(scenario / "check.py"), str(other_scenario / "check.py"),
                  str(above / ".settings" / "config.json"), str(above / ".linked" / "config.json")]
        empty = [str(above / "AGENTS.md"), str(above / "CLAUDE.md"), *([str(above / "GEMINI.md")] if (above / "GEMINI.md").exists() else [])]
        write(look, "#!/bin/sh\n[ \"$TRIAL_TURN\" = 0 ] && exit 0\n"
                    + "".join(f"[ -e '{p}' ] && echo 'saw {p}' >> \"$TRIAL_REPLY\"\n" for p in absent)
                    + "".join(f"[ -s '{p}' ] && echo 'saw content in {p}' >> \"$TRIAL_REPLY\"\n" for p in empty)
                    + "[ -d '" + str(above) + "' ] && echo 'directories above stay' >> \"$TRIAL_REPLY\"\n"
                    + "echo \"cwd $(pwd)\" >> \"$TRIAL_REPLY\"\n"
                    + "printf '{\"finished\": true, \"limits\": [\"looks only\"]}' > \"$TRIAL_RECORD\"\n", 0o755)
        spec = {"name": "look", "dir": str(scenario), "plan_dir": str(self.tmp), "prompt": "look", "sandbox": "confined",
                "trial_inputs": [str(self.tmp), str(scenario), str(other_scenario)]}
        job = out / "runs" / "look"
        (job / "work").mkdir(parents=True)
        (job / "harness").mkdir()
        arm = {"executor": "launcher", "script": str(look)}
        env = trial.isolated_env(job, out, spec, arm)
        status, confined = trial.run_launcher(arm, spec, job, env, out=out)
        self.assertEqual((status, confined), ("ok", True))
        reply = (job / "final-0.md").read_text()
        self.assertNotIn("saw", reply)
        self.assertIn("directories above stay", reply)
        self.assertIn(f"cwd {job / 'work'}", reply)

    def test_copy_cleanup_never_follows_a_link_the_agent_put_in_place_of_its_harness(self):
        decoy = Path(tempfile.mkdtemp(prefix="launcher-decoy-", dir=Path.home() / ".cache"))
        self.addCleanup(shutil.rmtree, decoy, True)
        write(decoy / "home" / ".fake-sign-in", "another run's copy\n")
        write(self.tmp / "sign-in", "this run's copy\n")
        arm = self.arm(copy={".fake-sign-in": "sign-in"})
        arm["pass_env"] = [*arm["pass_env"], "FAKE_LAUNCHER_DECOY"]
        self.plan({"a": arm}, sandbox="none")
        r = self.run_plan("swap-harness", FAKE_LAUNCHER_DECOY=str(decoy))
        self.assertEqual(r.returncode, 0, r.stderr)
        run_dir = self.out / "runs" / "make-file__a__r1"
        self.assertTrue((run_dir / "harness").is_symlink() and (run_dir / "harness-moved").is_dir())  # the attack ran
        self.assertEqual((decoy / "home" / ".fake-sign-in").read_text(), "another run's copy\n")

    def test_copies_that_overlap_are_refused(self):
        write(self.tmp / "dir" / "a", "x")
        self.plan({"a": self.arm(copy={".x": "dir", ".x/a": "dir/a"})})
        r = self.run_plan()
        self.assertEqual(r.returncode, 2)
        self.assertIn("overlaps copy", r.stderr)

    def test_a_turn_that_changes_watched_configuration_through_a_link_invalidates_its_run(self):
        self.plan({"a": self.arm(watch=["~/.fake/settings.json"])})
        r = self.run_plan("symlink-watch")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.result()["status"], "config-changed")

    def test_a_link_to_nothing_in_a_watched_directory_hides_no_change_beside_it(self):
        self.plan({"a": self.arm(watch=["~/.fake-config"])})
        r = self.run_plan("dangling-watch")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.result()["status"], "config-changed")

    def test_watched_configuration_the_runtime_cannot_read_refuses_the_launcher(self):
        self.plan({"a": self.arm(watch=["~/.fake-config"])})
        for mode in ("deep-watch", "unreadable-watch"):
            with self.subTest(mode):
                r = self.run_plan(mode)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("setup-watch-unreadable", r.stderr)

    @unittest.skipUnless(CONFINED and os.access("/var/tmp", os.W_OK) and Path("/usr/share").is_dir(),
                         "needs bubblewrap and a writable /var/tmp")
    def test_a_dot_link_above_the_run_into_the_systems_directories_refuses_confinement(self):
        above = Path(tempfile.mkdtemp(prefix="launcher-above-", dir="/var/tmp"))
        self.addCleanup(shutil.rmtree, above, True)
        os.symlink("/usr/share", above / ".claude")  # emptying it would empty what executors need
        out = above / "out"
        job = out / "runs" / "look"
        (job / "work").mkdir(parents=True)
        (job / "harness").mkdir()
        write(self.tmp / "look.sh", "#!/bin/sh\nexit 0\n", 0o755)
        spec = {"name": "look", "dir": str(self.tmp / "scenarios" / "make-file"), "plan_dir": str(self.tmp),
                "prompt": "look", "sandbox": "confined"}
        arm = {"executor": "launcher", "script": str(self.tmp / "look.sh")}
        with self.assertRaisesRegex(trial.TrialError, "links to /usr/share, which confinement cannot hide"):
            trial.run_launcher(arm, spec, job, trial.isolated_env(job, out, spec, arm), out=out)

    def test_a_run_that_reports_two_models_is_invalid_even_when_the_probe_saw_none(self):
        self.plan({"a": self.arm()})
        r = self.run_plan("two-models")
        # the probe sees the change across its own two turns and refuses
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("different model for different turns", r.stderr)
        self.assertEqual(trial._launcher_status({}, "ok", {"finished": True, "turns": [{"model": "a"}, {"model": "b"}]}, None),
                         "model-changed")

    def test_the_probe_refuses_a_launcher_whose_executor_never_runs_the_command(self):
        self.plan({"a": self.arm()})
        r = self.run_plan("no-shell")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("may not run shell commands", r.stderr)

    def test_an_arm_named_like_a_judge_is_probed_as_an_arm(self):
        self.plan({"judge-prompts": self.arm()})
        r = self.run_plan("drop-instructions")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("code word", r.stderr)

    def test_a_stored_probe_pass_is_reused_only_for_what_it_qualified(self):
        s = self.tmp / "scenarios" / "talk"
        write(s / "scenario.json", json.dumps({"prompt": "say hello", "required": []}))
        write(s / "check.py", "def check(run):\n    return {}\n")
        self.plan({"a": self.arm()}, scenarios=["scenarios/talk"])
        self.assertEqual(self.run_plan("fresh").returncode, 0)
        self.plan({"a": self.arm()}, scenarios=["scenarios/talk", "scenarios/make-file"])
        r = self.run_plan("fresh")  # make-file has a follow-up, which a fresh session each turn cannot continue
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("follow-up", r.stderr)

    def test_a_launcher_judge_is_retried_after_a_transient_exit_and_must_print_only_its_verdict(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "required": ["made_file"],
            "judge": {"question": "Did it report make-file done?", "pass_when": "it does"}}))
        judge = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge",
                 "pass_env": ["FAKE_LAUNCHER_MODE", "FAKE_LAUNCHER_MARK"]}
        self.plan({"a": self.arm()}, judge=judge, sandbox="none")
        r = self.run_plan("judge-transient-once", FAKE_LAUNCHER_MARK=str(self.tmp / "judge-mark"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.result()["judge"]["verdict"], "pass")
        shutil.rmtree(self.out)
        r = self.run_plan("judge-prose")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("gave no verdict", r.stderr)

    def test_derived_launcher_arms_keep_their_resources_and_an_override_drops_the_launcher(self):
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    return {'made_file': run.file('out.txt').strip() == 'hi',\n            'tool_called': True}\n")
        self.plan({"a": self.arm(resources={"skills/helper": "skills/helper"})})
        self.assertEqual(self.run_plan().returncode, 0)
        consumer = self.tmp / "scenarios" / "consume"
        write(consumer / "scenario.json", json.dumps({"prompt": "go", "required": []}))
        derived = self.tmp / "derived.json"
        r = self.run_cli("derive", str(self.out), "--scenario", "make-file", "--artifact", "out.txt", "--consumer",
                         str(consumer), "--plan", str(derived))
        self.assertEqual(r.returncode, 0, r.stderr)
        arm = json.loads(derived.read_text())["arms"]["a~r1"]
        self.assertEqual(arm["executor"], "launcher")
        self.assertIn("skills/helper", arm["resources"])
        r = self.run_cli("derive", str(self.out), "--scenario", "make-file", "--artifact", "out.txt", "--consumer",
                         str(consumer), "--plan", str(derived), "--executor", json.dumps({"executor": "command", "command": "true"}))
        arm = json.loads(derived.read_text())["arms"]["a~r1"]
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse({"script", "binary", "copy", "hide", "watch"} & set(arm))

    def test_a_replacement_judge_on_recheck_is_probed_before_it_judges(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "required": ["made_file"],
            "judge": {"question": "Did it report make-file done?", "pass_when": "it does"}}))
        judge = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge", "pass_env": ["FAKE_LAUNCHER_MODE"]}
        self.plan({"a": self.arm()}, judge=judge)
        self.assertEqual(self.run_plan().returncode, 0)
        other = dict(judge, script=str(self.tmp / "launcher.py"), model="another-judge")
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(other), mode="judge-forge")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("forged-verdict.json", r.stderr)

    @unittest.skipUnless(CONFINED, "needs bubblewrap: the re-judge changes confinement from confined to none")
    def test_a_rejudge_in_another_confinement_mode_probes_the_stored_judge_first(self):
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "required": ["made_file"],
            "judge": {"question": "Did it report make-file done?", "pass_when": "it does"}}))
        judge = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge", "pass_env": ["FAKE_LAUNCHER_MODE"]}
        self.plan({"a": self.arm()}, judge=judge)
        self.assertEqual(self.run_plan().returncode, 0)
        probes = lambda: sorted(p.name[0] for p in (self.out / "probes").iterdir())
        self.assertEqual(probes(), ["a", "j"])
        r = self.run_cli("recheck", str(self.out), "--rejudge", "--sandbox", "none", mode="judge-forge")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("forged-verdict.json", r.stderr)
        self.assertEqual(probes(), ["a", "j", "j"])  # the judge, newly in this mode; no arm runs on a re-judge
        r = self.run_cli("recheck", str(self.out), "--rejudge", "--sandbox", "none")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIs(self.result()["passed"], True)

    @unittest.skipUnless(CONFINED, "needs bubblewrap: the re-judge changes confinement from confined to none")
    def test_a_rejudge_probes_only_the_judges_of_the_runs_it_judges(self):
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file"],
                                               "judge": {"question": "Did it report make-file done?", "pass_when": "it does"}}))
        write(s / "setup.sh", 'case "$PWD" in *__b__*) exit 1 ;; esac\n')  # arm b's runs never start
        write(self.tmp / "judge-b.sh", (
            '#!/bin/sh\n[ "$TRIAL_TURN" = 0 ] && exit 0\n[ -n "$FAKE_JUDGE_BROKEN" ] && exit 7\n'
            'case "$(cat "$TRIAL_PROMPT_FILE")" in *" is 5."*|*"make-file done"*) v=pass ;; *) v=fail ;; esac\n'
            'printf \'{"verdict": "%s", "reason": "arithmetic"}\\n\' "$v"\n'
            'printf \'{"finished": true, "limits": ["a pretend judge"]}\' > "$TRIAL_RECORD"\n'), 0o755)
        own_a = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge", "pass_env": ["FAKE_LAUNCHER_MODE"]}
        own_b = {"executor": "launcher", "script": "judge-b.sh", "model": "judge-b", "pass_env": ["FAKE_JUDGE_BROKEN"]}
        self.plan({"a": self.arm(judge=own_a), "b": self.arm(judge=own_b)})
        self.run_plan()
        self.assertEqual((self.result("a")["passed"], self.result("b")["status"]), (True, "setup-failed"))
        # b's judge now fails, but no run of b is judged, so the re-judge neither probes nor asks it
        r = self.run_cli("recheck", str(self.out), "--rejudge", "--sandbox", "none", FAKE_JUDGE_BROKEN="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(p.name[0] for p in (self.out / "probes").iterdir()).count("j"), 3)  # a's judge, now unconfined too
        self.assertIs(self.result("a")["passed"], True)

    def test_a_judge_no_selected_run_asks_is_not_probed(self):
        write(self.tmp / "broken-judge.sh", "#!/bin/sh\nexit 7\n", 0o755)  # refused by any probe that asked it
        broken = {"executor": "launcher", "script": "broken-judge.sh", "model": "never-asked"}
        own = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge", "pass_env": ["FAKE_LAUNCHER_MODE"]}
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "required": ["made_file"],
            "judge": {"question": "Did it report make-file done?", "pass_when": "it does"}}))
        self.plan({"a": self.arm(judge=own)}, judge=broken)  # the only arm names its own judge
        r = self.run_plan()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(p.name[0] for p in (self.out / "probes").iterdir()), ["a", "j"])
        self.assertIs(self.result()["passed"], True)
        # no judge is asked at all when no selected scenario asks a judge question
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file"]}))
        self.plan({"a": self.arm()}, judge=broken)
        self.out = self.tmp / "out-unjudged"
        r = self.run_plan()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(p.name[0] for p in (self.out / "probes").iterdir()), ["a"])

    def test_a_launcher_run_whose_record_is_gone_has_no_evidence_on_recheck(self):
        self.plan({"a": self.arm()})
        self.assertEqual(self.run_plan().returncode, 0)
        (self.out / "runs" / "make-file__a__r1" / "record.json").unlink()
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        res = self.result()
        self.assertIsNone(res["passed"])
        self.assertIn("does not cover the commands", res["checks"]["check_error"])

    def test_record_fields_of_the_wrong_type_make_the_record_unusable(self):
        for record, expected in (({"finished": True, "turns": [{"session": ["a"]}]}, '"session" that is not a string'),
                                 ({"finished": True, "actions": [{"kind": "command", "exit_code": "0"}]}, '"exit_code" of the wrong type'),
                                 ({"finished": True, "usage": {"input_tokens": "many"}}, "not a finite, non-negative number")):
            self.assertIn(expected, trial._record_problem(record))
        job = self.tmp / "job"
        job.mkdir()
        (job / "record.json").write_text(json.dumps({"finished": True, "transcripts": ["../../outside"]}))
        self.assertIn("not a file inside the run directory", trial._read_record(job / "record.json")[1])

    def test_exposure_needs_a_known_outcome_and_every_output_channel_to_say_not_read(self):
        home = self.tmp / "job" / "harness" / "home" / "skills" / "helper"
        write(home / "SKILL.md", (self.tmp / "skills" / "helper" / "SKILL.md").read_text())
        job = self.tmp / "job"
        read = {"kind": "read", "path": "~/skills/helper/SKILL.md", "output": ""}
        unknown = trial.Run(job, "ok", record={"finished": True, "actions": [read], "covers": list(trial.ACTION_KINDS)})
        with self.assertRaisesRegex(trial.RecordUnavailable, "no outcome"):  # a read that may have succeeded
            unknown.exposed("skills/helper")
        failed = trial.Run(job, "ok", record={"finished": True, "actions": [dict(read, ok=False)], "covers": list(trial.ACTION_KINDS)})
        self.assertEqual(failed.exposed("skills/helper"), [])
        known = trial.Run(job, "ok", record={"finished": True, "actions": [dict(read, ok=True)], "covers": list(trial.ACTION_KINDS)})
        self.assertTrue(known.exposed("skills/helper"))
        partial = trial.Run(job, "ok", record={"finished": True, "actions": [], "covers": ["read", "load", "command"]})
        with self.assertRaises(trial.RecordUnavailable):
            partial.exposed("skills/helper")
        # a recorded load says yes whatever else the record covers; no still needs a record that could show it
        loaded = trial.Run(job, "ok", record={"finished": True, "covers": ["load"],
                                              "actions": [{"kind": "load", "name": "helper", "ok": True}]})
        self.assertTrue(loaded.skill_loaded("helper"))
        with self.assertRaises(trial.RecordUnavailable):
            loaded.skill_loaded("another")
        with self.assertRaises(trial.RecordUnavailable):
            loaded.skills_loaded()
        self.assertFalse(trial._shows_frontmatter("---\ntitle: x\n---\nname: helper\n", "helper"))
        self.assertTrue(trial._shows_frontmatter("   1\t---\n   2\tname: helper\n   3\t---\n", "helper"))

    def test_a_skill_loaded_from_a_directory_of_skills_exposes_that_directory(self):
        # A resource can place a whole skills root (".claude/skills" holding many skill directories); the executor then
        # loads one skill by its name, and that load is evidence the root reached the model.
        job = self.tmp / "job"
        root = job / "harness" / "home" / ".claude" / "skills"
        for name in ("alpha", "beta"):
            write(root / name / "SKILL.md", f"---\nname: {name}\ndescription: The {name} skill.\n---\n"
                  f"The {name} skill explains how its method works in plain words for the reader.\n")
        complete = list(trial.ACTION_KINDS)

        def exposed(*actions):
            return trial.Run(job, "ok", record={"finished": True, "actions": list(actions), "covers": complete}).exposed(".claude/skills")
        self.assertEqual(exposed({"kind": "load", "name": "alpha", "ok": True}), ["load alpha"])
        self.assertEqual(exposed({"kind": "load", "name": "plugin:beta", "ok": True}), ["load plugin:beta"])
        self.assertEqual(exposed({"kind": "load", "name": "gamma", "ok": True}), [])
        self.assertEqual(exposed({"kind": "load", "name": "alpha", "ok": False}), [])
        self.assertEqual(exposed({"kind": "read", "path": "/elsewhere/beta/SKILL.md", "ok": True}), ["read /elsewhere/beta/SKILL.md"])

    def test_a_command_exposes_what_it_names_and_shows_and_shared_text_exposes_nothing(self):
        # Only the path tells a read from a coincidence: an agent writes and prints common lines itself.
        job = self.tmp / "job"
        home = job / "harness" / "home"
        write(home / "skills" / "coder" / "SKILL.md",
              "---\nname: coder\ndescription: Code things.\n---\n"
              "    except subprocess.TimeoutExpired:\n"
              "All tests passed and no errors were found\n"
              "Stop the whole process group before you read what the command printed.\n")
        write(home / "notes" / "AGENTS.md", "Always run pytest before committing.\n")
        complete = list(trial.ACTION_KINDS)

        def exposed(command, output, key="skills/coder", ok=True):
            action = {"kind": "command", "command": command, "ok": ok, "output": output}
            return trial.Run(job, "ok", record={"finished": True, "actions": [action], "covers": complete}).exposed(key)
        # The executor's own program prints a line the skill also holds: no path named, so no read is shown, but the
        # line may have come from the skill by another way (a copy, a script that opens it), so no absence either.
        for command, output in (("python3 runner.py", "All tests passed and no errors were found\n"),
                                ("cat runner.py", "    except subprocess.TimeoutExpired:\n")):
            with self.assertRaisesRegex(trial.RecordUnavailable, "shows a line of it"):
                exposed(command, output)
        # A body-only read, a one-line grep, and a one-line instruction file, each by the path they name.
        self.assertTrue(exposed("sed -n '6,$p' ~/skills/coder/SKILL.md", "Stop the whole process group before you read what the command printed.\n"))
        self.assertTrue(exposed("grep -n pytest ~/notes/AGENTS.md", "1:Always run pytest before committing.\n", key="notes/AGENTS.md"))
        self.assertTrue(exposed("cat ~/notes/AGENTS.md", "Always run pytest before committing.\n", key="notes/AGENTS.md"))
        # Naming the path without showing it is no read: a copy, a count, its metadata, a listing of the skill's
        # directory, a failure.
        self.assertEqual(exposed("cp ~/skills/coder/SKILL.md copy.md", ""), [])
        self.assertEqual(exposed(f"wc -l {home}/skills/coder/SKILL.md", f"7 {home}/skills/coder/SKILL.md\n"), [])
        self.assertEqual(exposed("stat ~/skills/coder/SKILL.md", f"  File: {home}/skills/coder/SKILL.md\n  Size: 214  Blocks: 8  "
                                 "IO Block: 4096  regular file\nAccess: (0444/-r--r--r--)  Uid: (1000/user)\n"), [])
        # A command that names it with no output recorded, or no outcome, cannot show either way.
        for action in ({"ok": True}, {"ok": None, "output": ""}):
            with self.assertRaisesRegex(trial.RecordUnavailable, "cannot show"):
                trial.Run(job, "ok", record={"finished": True, "covers": complete, "actions": [
                    dict({"kind": "command", "command": "cat ~/skills/coder/SKILL.md"}, **action)]}).exposed("skills/coder")
        self.assertEqual(exposed("cat ~/skills/coder/SKILL.md", "cat: Permission denied, and a long message here\n", ok=False), [])
        for listing in ("ls ~/skills", "ls ~/skills/coder", "ls -d ~/skills/coder/*", "cat src/main.py; ls ~/skills 2>&1 | head"):
            root = trial.Run(job, "ok", record={"finished": True, "covers": complete, "actions": [
                {"kind": "command", "command": listing, "ok": True, "output": "SKILL.md\nreferences and other long names here"}]})
            self.assertEqual(root.exposed("skills"), [], listing)
        cat_all = trial.Run(job, "ok", record={"finished": True, "covers": complete, "actions": [
            {"kind": "command", "command": "cat ~/skills/*/SKILL.md", "ok": True,
             "output": "Stop the whole process group before you read what the command printed.\n"}]})
        self.assertTrue(cat_all.exposed("skills"))
        # A skill's frontmatter in any output names it, however the output came about.
        self.assertTrue(exposed("python3 show.py", "---\nname: coder\ndescription: Code things.\n---\n"))

        def exposed_at(cwd, command, output, key):
            action = {"kind": "command", "command": command, "ok": True, "output": output, "cwd": str(cwd)}
            return trial.Run(job, "ok", record={"finished": True, "actions": [action], "covers": complete}).exposed(key)
        notes = home / "notes"
        # A path printed as written, relative or absolute, is no content.
        self.assertEqual(exposed_at(home, "echo notes/AGENTS.md notes/AGENTS.md", "notes/AGENTS.md notes/AGENTS.md\n",
                                    "notes/AGENTS.md"), [])
        # A file in a skill's directory is read through it.
        write(home / "skills" / "coder" / "references" / "rules.md", "Rules for coding with care in every case here.\n")
        self.assertTrue(exposed("cat ~/skills/coder/references/rules.md", "Rules for coding with care in every case here.\n"))
        # Shell punctuation and a heredoc's lone quote do not hide the path a command names.
        self.assertTrue(exposed_at(home, f"cat {notes}/AGENTS.md; printf done", "Always run pytest before committing.\ndone", "notes/AGENTS.md"))
        write(notes / "rules with spaces.txt", "Rules for the whole team, written down once for everyone.\n")
        self.assertTrue(exposed_at(home, f"cat <<EOF > /dev/null\nit's input\nEOF\ncat '{notes}/rules with spaces.txt'",
                                   "Rules for the whole team, written down once for everyone.\n", "notes/rules with spaces.txt"))
        write(notes / "AGENTS#backup.md", "An older copy of the agent notes kept for reference.\n")
        self.assertTrue(exposed_at(home, f"cat {notes}/AGENTS#backup.md", "An older copy of the agent notes kept for reference.\n",
                                   "notes/AGENTS#backup.md"))
        # A grep's pattern is no path, and what it prints of the material is content, a version in it included.
        self.assertTrue(exposed_at(notes, "grep -n 'pytest before committing' ./AGENTS.md", "1:Always run pytest before committing.\n",
                                   "notes/AGENTS.md"))
        write(notes / "VERSIONS", "1.2.3 1.2.3 1.2.3 1.2.3 1.2.3 1.2.3 1.2.3 1.2.3\n")
        self.assertTrue(exposed_at(notes, "grep 1.2.3 ./VERSIONS", "1.2.3 1.2.3 1.2.3 1.2.3 1.2.3 1.2.3 1.2.3 1.2.3\n", "notes/VERSIONS"))
        # A heredoc's lone quote sends the split to its fallback, which keeps the path after the heredoc's word.
        self.assertTrue(exposed_at(notes, "cat <<EOF ./AGENTS.md\nit's input\nEOF", "Always run pytest before committing.\nit's input\n",
                                   "notes/AGENTS.md"))
        # A word without a slash names no path: a pattern, a version, an option value or a body line that looks like a file's
        # name, and a file named bare, whose content in the output then leaves its reading unknown.
        write(notes / "foo.bar", "A file whose name looks like a dotted grep pattern here.\n")
        self.assertEqual(exposed_at(notes, "grep foo.bar unrelated.txt", "foo.bar matched a line of an unrelated file here\n",
                                    "notes/foo.bar"), [])
        self.assertEqual(exposed_at(notes, "cat <<-EOF\n  EOF\ncat AGENTS.md\nthis is only literal data with more than twenty\nEOF",
                                    "  EOF\ncat AGENTS.md\nthis is only literal data with more than twenty\n", "notes/AGENTS.md"), [])
        with self.assertRaises(trial.RecordUnavailable):
            exposed_at(notes, "cat AGENTS.md", "Always run pytest before committing.\n", "notes/AGENTS.md")
        write(notes / "POLICY", "Every change is reviewed before it merges, without exception.\n")
        write(notes / "never", "A file that happens to be named like an option value here.\n")
        self.assertEqual(exposed_at(notes, "grep POLICY unrelated.txt", "POLICY checks were skipped because the input is empty.\n",
                                    "notes/POLICY"), [])
        self.assertEqual(exposed_at(notes, "grep --color=never pattern unrelated.txt", "a pattern matched in an unrelated file here\n",
                                    "notes/never"), [])
        with self.assertRaises(trial.RecordUnavailable):
            exposed_at(notes, "cat POLICY", "Every change is reviewed before it merges, without exception.\n", "notes/POLICY")
        self.assertTrue(exposed_at(notes, "cat ./POLICY", "Every change is reviewed before it merges, without exception.\n", "notes/POLICY"))
        # An "=" in a file's name is part of it: this names another file, not the material.
        write(notes / "reference", "The reference file has its own contents in it.\n")
        write(notes / "reference=copy.md", "A different file with other contents in it.\n")
        self.assertEqual(exposed_at(notes, f"cat {notes}/reference=copy.md", "A different file with other contents in it.\n",
                                    "notes/reference"), [])

    def test_exposure_and_its_evidence_reach_the_report_and_a_scenario_can_require_it(self):
        resources = {"skills/helper": "skills/helper"}
        self.plan({"a": self.arm(resources=resources)})
        s = self.tmp / "scenarios" / "make-file"
        for mode, exposure, passed, reason in (("read-skill", True, True, None), ("", False, None, "not-exposed"),
                                               ("read-unknown", None, None, "exposure-unknown")):
            with self.subTest(mode=mode):
                spec = json.loads((s / "scenario.json").read_text())
                spec.pop("requires_exposure", None)
                write(s / "scenario.json", json.dumps(spec))
                shutil.rmtree(self.out, ignore_errors=True)
                self.assertEqual(self.run_plan(mode).returncode, 0)
                run = trial.report(self.out)["runs"][0]
                self.assertEqual(run["exposure"], {"skills/helper": exposure})
                self.assertTrue(run["exposure_evidence"]["skills/helper"])  # what decided it, or why it is unknown
                self.assertIs(run["passed"], True)  # an adoption question: not reading it is an outcome like any other
                # an efficacy question: a run its treatment did not reach measures nothing about the treatment
                write(s / "scenario.json", json.dumps(dict(spec, requires_exposure=True)))
                self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
                run = trial.report(self.out)["runs"][0]
                self.assertEqual((run["passed"], run["invalid_reason"]), (passed, reason))

    def test_recheck_reads_exposure_again_from_the_stored_record(self):
        self.plan({"a": self.arm(resources={"skills/helper": "skills/helper"})})
        r = self.run_plan("read-skill")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.result()["exposure"], {"skills/helper": True})
        path = self.out / "runs" / "make-file__a__r1" / "result.json"
        stale = dict(json.loads(path.read_text()), exposure={"skills/helper": False})  # as an older rule recorded it
        path.write_text(json.dumps(stale))
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.result()["exposure"], {"skills/helper": True})

    def test_a_run_whose_executor_ran_counts_its_time_whatever_its_status(self):
        measures = trial._cost_measures([{"status": "exit-1", "seconds": 120, "commands": 0, "usage": {}, "executed": True},
                                         {"status": "setup-exit-1", "seconds": 1, "usage": {}, "executed": False}])
        self.assertEqual(measures["seconds_mean"], 120)

    def test_a_host_record_with_actions_of_no_known_kind_keeps_the_job_waiting(self):
        self.plan({"a": {"executor": "host", "model": "pretend", "host_env": True}})
        r = self.run_plan()
        self.assertEqual(r.returncode, 4, r.stderr)
        entry = json.loads((self.out / "dispatch.json").read_text())[0]
        self.assertEqual((entry["model"], entry["timeout_s"]), ("pretend", None))
        Path(entry["reply"]).write_text("done")
        Path(entry["record"]).write_text(json.dumps({"finished": True, "actions": [{"kind": "dance"}]}))
        r = self.run_plan()
        self.assertEqual(r.returncode, 4)
        self.assertIn("without a \"kind\"", r.stdout)


if __name__ == "__main__":
    unittest.main()
