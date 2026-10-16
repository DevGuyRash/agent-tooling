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
            "            'commands': len(run.commands),\n"
            "            'workdir': run.executor_workdir}\n"))
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
        if CONFINED:
            self.assertEqual(res["mounted_at"], "/tmp/run")
            self.assertEqual(res["checks"]["workdir"], "/tmp/run/work")
            state = json.loads((run_dir / "harness" / "home" / ".fake" / "state.json").read_text())
            self.assertEqual({t["cwd"] for t in state["turns"]}, {"/tmp/run/work"})

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

    def test_a_launcher_names_its_model_exactly(self):
        self.plan({"a": self.arm(model="latest:pretend-*")})
        r = self.run_plan()
        self.assertEqual(r.returncode, 2)
        self.assertIn("names its model exactly", r.stderr)
        ids = self.tmp / "ids.txt"
        ids.write_text("pretend-1\npretend-1.10\npretend-1.9\npretend-1.10-mini\n")
        r = self.run_cli("latest", "pretend-*", str(ids))
        self.assertEqual(r.stdout.strip(), "pretend-1.10")

    @unittest.skipUnless(CONFINED, "needs bubblewrap")
    def test_a_confined_launcher_sees_neither_the_trial_inputs_nor_the_home(self):
        planted = Path.home() / ".cache" / f"{self.tmp.name}-planted"
        planted.write_text("secret")
        self.addCleanup(planted.unlink)
        outside = Path(tempfile.mkdtemp(prefix="launcher-inputs-", dir="/var/tmp")) if os.access("/var/tmp", os.W_OK) else None
        if outside:
            self.addCleanup(shutil.rmtree, outside, True)
            write(outside / "check.py", "visible?\n")
        look = self.tmp / "look.sh"
        paths = [str(planted), str(self.tmp / "plan.json"), str(self.tmp / "scenarios" / "make-file" / "check.py"),
                 str(self.out / "plan.json"), *([str(outside / "check.py")] if outside else [])]
        write(look, "#!/bin/sh\n[ \"$TRIAL_TURN\" = 0 ] && exit 0\n"
                    + "".join(f"[ -e '{p}' ] && echo 'saw {p}' >> \"$TRIAL_REPLY\"\n" for p in paths)
                    + "echo \"cwd $(pwd)\" >> \"$TRIAL_REPLY\"\n"
                    + "printf '{\"finished\": true, \"limits\": [\"looks only\"]}' > \"$TRIAL_RECORD\"\n", 0o755)
        spec = {"name": "look", "dir": str(outside or self.tmp / "scenarios" / "make-file"), "plan_dir": str(self.tmp),
                "prompt": "look", "sandbox": "confined"}
        job = self.out / "runs" / "look"
        (job / "work").mkdir(parents=True)
        (job / "harness").mkdir()
        arm = {"executor": "launcher", "script": str(look)}
        env = trial.isolated_env(job, self.out, spec, arm)
        status, confined = trial.run_launcher(arm, spec, job, env, out=self.out)
        self.assertEqual((status, confined), ("ok", True))
        reply = (job / "final-0.md").read_text()
        self.assertNotIn("saw", reply)
        self.assertIn("cwd /tmp/run/work", reply)

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
