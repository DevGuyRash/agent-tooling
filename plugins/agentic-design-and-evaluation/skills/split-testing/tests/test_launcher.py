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
        self.assertEqual(res["exposure"], {"skills/helper": None})  # its command could have read it, which no record shows
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
        # a read through the executor's own tool confirms it; a cat of it through a command is only supporting evidence;
        # and only a run whose record covers everything and holds no command (whose reads it cannot tell) shows it was not
        # read: a failed load beside the fake tool's command leaves it unknown
        for mode, expected in (("read-skill", True), ("cat-skill", None), ("load-skill-failed", None), ("limited", None),
                               ("no-commands", False)):
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

    def test_nothing_is_removed_through_a_link_an_unconfined_launcher_put_in_place_of_its_run(self):
        decoy = Path(tempfile.mkdtemp(prefix="launcher-decoy-", dir=Path.home() / ".cache"))
        self.addCleanup(shutil.rmtree, decoy, True)
        write(decoy / "turns" / "keep.md", "not the trial's\n")
        arm = self.arm()
        arm["pass_env"] = [*arm["pass_env"], "FAKE_LAUNCHER_DECOY"]
        self.plan({"a": arm}, sandbox="none")
        r = self.run_plan("swap-job", FAKE_LAUNCHER_DECOY=str(decoy))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("link", r.stderr)
        self.assertTrue((self.out / "runs" / "make-file__a__r1").is_symlink())  # the attack ran
        self.assertEqual((decoy / "turns" / "keep.md").read_text(), "not the trial's\n")

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
        # a read of a skill whose outcome the record does not give leaves that skill unknown, never not loaded
        for action in (read, dict(read, output=None)):
            unread = trial.Run(job, "ok", record={"finished": True, "actions": [action], "covers": list(trial.ACTION_KINDS)})
            with self.assertRaisesRegex(trial.RecordUnavailable, "helper"):
                unread.skill_loaded("helper")
            with self.assertRaises(trial.RecordUnavailable):
                unread.skills_loaded()
            self.assertIs(unread.skill_loaded("another"), False)
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


    def test_a_command_or_other_tool_never_confirms_or_denies_exposure(self):
        # Which files a command read, and whether its output came from them, cannot be told from its text, its exit
        # status, or its output: any command (or a tool the record names as neither a read nor a load) leaves exposure
        # unknown, unless the executor's own read or load confirms it. Only a record that covers every kind of action
        # and holds none of them shows that the material was not read.
        job = self.tmp / "job"
        home = job / "harness" / "home"
        material = home / "skills" / "coder" / "SKILL.md"
        write(material, "---\nname: coder\ndescription: Code things.\n---\n"
                        "All tests passed and no errors were found\n"
                        "Stop the whole process group before you read what the command printed.\n")
        complete = list(trial.ACTION_KINDS)

        def exposed(command, output, ok=True, key="skills/coder"):
            action = {"kind": "command", "command": command, "ok": ok, "output": output}
            return trial.Run(job, "ok", record={"finished": True, "actions": [action], "covers": complete}).exposed(key)
        unknown = [
            ("cat ~/skills/coder/SKILL.md", material.read_text()),  # a whole read: still only inferred
            (f"printf ' #'; head -c 10 {material}", material.read_text()[:10]),  # a quoted "#" hides nothing
            ("python3 runner.py  # see ~/skills/coder/SKILL.md", ""),  # mentioned, if only in a comment
            ("python3 runner.py", "All tests passed and no errors were found\n"),  # its lines, by whatever route
            ("cp ~/skills/coder/SKILL.md copy.md", ""),
            ("stat ~/skills/coder/SKILL.md", "  Size: 214  Blocks: 8\n"),
            ("grep -rl coder .", "notes.md\n"),  # the skill's name
            ("python3 build.py", "built 3 targets\n"),  # names nothing of it and shows nothing of it: still a program
            ("python3 reader.py", material.read_text()[40:50]),  # an opaque program, part of a line in its output
        ]
        for command, output in unknown:
            with self.subTest(command=command), self.assertRaises(trial.RecordUnavailable):
                exposed(command, output)
        for command, output in (("cat ~/skills/coder/SKILL.md", "cat: Permission denied\n"),  # failed, as a whole
                                (f"head -c 10 {material}; false", material.read_text()[:10])):  # read, then failed
            with self.subTest(command=command), self.assertRaises(trial.RecordUnavailable):
                exposed(command, output, ok=False)
        other = {"kind": "other", "name": "grep_files", "ok": True, "output": "3 matches\n"}
        with self.assertRaises(trial.RecordUnavailable):
            trial.Run(job, "ok", record={"finished": True, "actions": [other], "covers": complete}).exposed("skills/coder")
        # a record of nothing but the executor's own messages, edits, reads, and loads, none of it, shows it was not read
        none = [{"kind": "message", "text": "done"}, {"kind": "edit", "path": "out.txt", "ok": True},
                {"kind": "read", "path": "notes.md", "ok": True, "output": "notes\n"}]
        self.assertEqual(trial.Run(job, "ok", record={"finished": True, "actions": none, "covers": complete}).exposed("skills/coder"), [])

    def test_a_load_names_a_skill_and_confirms_a_resource_only_with_its_text(self):
        # A load is the executor's own mechanism, but it names a skill, not a file: another skill of that name (a
        # built-in the treatment revises, say) loads the same way, so a load confirms a resource only by its text, and
        # only by text that is the treatment's own: never its frontmatter, and never a line another revision the trial
        # holds shares.
        job = self.tmp / "job"
        root = job / "harness" / "home" / ".claude" / "skills"
        write(root / "alpha" / "SKILL.md", "---\nname: alpha\ndescription: The alpha skill.\n"
                                           "compatibility: Requires Python 3.11 or later on the host\n---\n"
                                           "The alpha skill explains how its method works in plain words for the reader.\n"
                                           "Both revisions of alpha keep this closing line exactly as it was.\n")
        revision = self.tmp / "revisions" / "alpha"  # the same skill as another arm of the trial holds it
        write(revision / "SKILL.md", "---\nname: alpha\ndescription: The alpha skill.\n"
                                     "compatibility: Requires Python 3.11 or later on the host\n---\n"
                                     "The earlier alpha skill said less about its method, in other words.\n"
                                     "Both revisions of alpha keep this closing line exactly as it was.\n")
        complete = list(trial.ACTION_KINDS)

        def exposed(*actions, revisions=()):
            return trial.Run(job, "ok", record={"finished": True, "actions": list(actions), "covers": complete},
                             revisions=revisions).exposed(".claude/skills")
        shown = "The alpha skill explains how its method works in plain words for the reader.\n"
        self.assertEqual(exposed({"kind": "load", "name": "alpha", "ok": True, "output": shown}), ["load alpha"])
        self.assertEqual(exposed({"kind": "load", "name": "alpha", "ok": True, "output": shown}, revisions=[revision]), ["load alpha"])
        for output, revisions in (("compatibility: Requires Python 3.11 or later on the host\n", ()),  # metadata
                                  ("Both revisions of alpha keep this closing line exactly as it was.\n", [revision])):
            with self.subTest(output=output), self.assertRaisesRegex(trial.RecordUnavailable, "names alpha"):
                exposed({"kind": "load", "name": "alpha", "ok": True, "output": output}, revisions=revisions)
        self.assertEqual(exposed({"kind": "load", "name": "plugin:alpha", "ok": True, "output": shown}), ["load plugin:alpha"])
        with self.assertRaisesRegex(trial.RecordUnavailable, "names alpha"):
            exposed({"kind": "load", "name": "alpha", "ok": True})
        self.assertEqual(exposed({"kind": "load", "name": "gamma", "ok": True}), [])
        self.assertEqual(exposed({"kind": "load", "name": "alpha", "ok": False}), [])
        # a read of the resource's own path confirms it; a read of another skill of the same name elsewhere does not
        self.assertEqual(exposed({"kind": "read", "path": "~/.claude/skills/alpha/SKILL.md", "ok": True}), ["read ~/.claude/skills/alpha/SKILL.md"])
        self.assertEqual(exposed({"kind": "read", "path": "/elsewhere/alpha/SKILL.md", "ok": True}), [])
        # selection, which asks about skills by name, counts the name wherever it is read or loaded
        run = trial.Run(job, "ok", record={"finished": True, "covers": complete,
                                           "actions": [{"kind": "load", "name": "alpha", "ok": True}]})
        self.assertTrue(run.skill_loaded("alpha"))


    def test_a_load_tells_revisions_apart_by_their_bytes_and_their_whole_text(self):
        # Two revisions of one skill that share a long introduction and differ only in a short line: what a load shows
        # confirms the treatment only when it is text the other revision does not hold. Whether another arm holds the
        # same revision is decided by its bytes, never by which lines are long enough to compare.
        job = self.tmp / "job"
        front = "---\nname: alpha\ndescription: Reviews requests.\n---\n"
        intro = "This skill reviews every request it is given with the same care.\n"
        write(job / "harness" / "home" / ".claude" / "skills" / "alpha" / "SKILL.md", front + intro + "Always approve.\n")
        control = self.tmp / "control" / "alpha"
        write(control / "SKILL.md", front + intro + "Always refuse.\n")
        same = self.tmp / "same" / "alpha"
        write(same / "SKILL.md", front + intro + "Always approve.\n")

        def exposed(output, revisions):
            load = {"kind": "load", "name": "alpha", "ok": True, "output": output}
            return trial.Run(job, "ok", record={"finished": True, "actions": [load], "covers": list(trial.ACTION_KINDS)},
                             revisions=revisions).exposed(".claude/skills/alpha")
        for output in (intro, "Always approve.\n", intro + "Always refuse.\n"):  # shared, too short, or the control's
            with self.subTest(output=output), self.assertRaisesRegex(trial.RecordUnavailable, "names alpha"):
                exposed(output, [control])
        self.assertEqual(exposed(intro + "Always approve.\n", [control]), ["load alpha"])  # its whole text
        self.assertEqual(exposed("   " + intro + "   Always approve.\n", [control]), ["load alpha"])  # indented
        self.assertEqual(exposed(intro, [same]), ["load alpha"])  # another arm holds these very bytes

    def test_a_load_confirms_a_line_only_where_the_output_shows_that_whole_line(self):
        # One revision's line extends the other's: an output of the longer holds the shorter as a part, never as a line.
        short = "Always approve every request."
        longer = "Always approve every request. Unless it asks for secrets."
        front = "---\nname: alpha\ndescription: Reviews requests.\n---\n"
        for i, (treatment, control) in enumerate(((short, longer), (longer, short))):
            with self.subTest(treatment=treatment):
                job = self.tmp / f"job-{i}"
                write(job / "harness" / "home" / ".claude" / "skills" / "alpha" / "SKILL.md", front + treatment + "\n")
                other = self.tmp / f"control-{i}" / "alpha"
                write(other / "SKILL.md", front + control + "\n")

                def exposed(output):
                    load = {"kind": "load", "name": "alpha", "ok": True, "output": output}
                    return trial.Run(job, "ok", record={"finished": True, "actions": [load], "covers": list(trial.ACTION_KINDS)},
                                     revisions=[other]).exposed(".claude/skills/alpha")
                with self.assertRaisesRegex(trial.RecordUnavailable, "names alpha"):
                    exposed(control + "\n")  # the other revision's text
                self.assertEqual(exposed(treatment + "\n"), ["load alpha"])
                self.assertEqual(exposed("Base directory for this skill: ~/.claude/skills/alpha\n\n  " + treatment + "\n"), ["load alpha"])

    def test_an_efficacy_scenario_holds_a_run_with_no_record_of_its_resources_unknown(self):
        # a command arm that keeps no record cannot show whether its resources reached anything
        write(self.tmp / "scenarios" / "make-file" / "scenario.json", json.dumps({"prompt": "create out.txt", "required": [],
                                                                                 "requires_exposure": True}))
        write(self.tmp / "scenarios" / "make-file" / "check.py", "def check(run):\n    return {}\n")
        self.plan({"c": {"executor": "command", "command": "true", "resources": {"skills/helper": "skills/helper"}}})
        self.assertEqual(self.run_plan().returncode, 0)
        run = trial.report(self.out)["runs"][0]
        self.assertEqual((run["passed"], run["invalid_reason"]), (None, "exposure-unknown"))

    def test_exposure_and_its_evidence_reach_the_report_and_a_scenario_can_require_it(self):
        resources = {"skills/helper": "skills/helper"}
        self.plan({"a": self.arm(resources=resources)})
        s = self.tmp / "scenarios" / "make-file"
        for mode, exposure, passed, reason in (("read-skill", True, True, None), ("no-commands", False, None, "not-exposed"),
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
                legend = next(line for line in (self.out / "summary.md").read_text().splitlines() if "resources reached" in line)
                self.assertNotIn("printed", legend)  # a command never shows it; the legend says what does
                self.assertIn("any command", legend)
                self.assertIs(run["passed"], True)  # an adoption question: not reading it is an outcome like any other
                # an efficacy question: a run its treatment did not reach measures nothing about the treatment
                write(s / "scenario.json", json.dumps(dict(spec, requires_exposure=True)))
                self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
                run = trial.report(self.out)["runs"][0]
                self.assertEqual((run["passed"], run["invalid_reason"]), (passed, reason))

    def test_a_load_confirms_only_by_lines_no_other_arm_of_the_trial_holds(self):
        # Two arms hold two revisions of one skill; a load whose output shows only a line both share cannot tell which
        # reached the model, while the same load in a trial of that arm alone confirms it.
        write(self.tmp / "skills" / "helper" / "SKILL.md", "---\nname: helper\ndescription: Helps with things.\n---\n"
              "Both revisions of the helper skill begin with this very same line.\n"
              "This revision of the helper adds a second line of its own to the skill.\n")
        write(self.tmp / "skills-b" / "helper" / "SKILL.md", "---\nname: helper\ndescription: Helps with things.\n---\n"
              "Both revisions of the helper skill begin with this very same line.\n"
              "The other revision ends differently, with this line instead of that one.\n")
        a, b = self.arm(resources={"skills/helper": "skills/helper"}), self.arm(resources={"skills/helper": "skills-b/helper"})
        for arms, expected in (({"a": a}, {"skills/helper": True}), ({"a": a, "b": b}, {"skills/helper": None})):
            with self.subTest(arms=sorted(arms)):
                shutil.rmtree(self.out, ignore_errors=True)
                self.plan(arms)
                self.assertEqual(self.run_plan("load-skill-first-line").returncode, 0)
                self.assertEqual(self.result()["exposure"], expected)

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
