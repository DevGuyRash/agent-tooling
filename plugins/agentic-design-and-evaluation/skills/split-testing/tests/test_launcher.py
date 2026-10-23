"""Launcher arms and judges (see references/launching.md), exercised through the CLI with a pretend agent launcher."""
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "trial.py"
FAKE = Path(__file__).resolve().parent / "fake_launcher.py"
sys.path.insert(0, str(SCRIPT.parent))
import trial  # noqa: E402

CONFINED = bool(shutil.which("bwrap"))


def copies_container() -> Path:
    """Where this user's copied credentials are kept, worked out apart from the runtime: trial-copies-<uid> under
    /run/user/<uid> when that is a real directory of the user's own with no link on the way to it, else under /tmp."""
    uid, run = os.getuid(), Path(f"/run/user/{os.getuid()}")
    try:
        st = os.lstat(run)  # the directory itself, never where a link leads
        ours = stat.S_ISDIR(st.st_mode) and st.st_uid == uid and os.path.realpath(run) == str(run)
    except OSError:
        ours = False
    return (run if ours else Path("/tmp")) / f"trial-copies-{uid}"


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
        self.root = copies_container()  # where every run of this user's keeps its copies, whatever its environment

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

    def test_the_probe_names_the_listed_skills_the_arm_did_not_place(self):
        # whatever a harness or a copied login adds to what the executor lists (an account's skills, say) shows in the
        # probe, by name, whichever harness it is: the arm placed helper, as its directory or as its SKILL.md alone,
        # and the executor listed one more
        for placed in ({"skills/helper": "skills/helper"}, {"skills/helper/SKILL.md": "skills/helper/SKILL.md"}):
            with self.subTest(placed=next(iter(placed))):
                subprocess.run(["chmod", "-R", "u+rwx", str(self.out)], capture_output=True)
                shutil.rmtree(self.out, ignore_errors=True)
                self.plan({"a": self.arm(resources=placed)})
                r = self.run_plan("list-account-skill")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("the executor listed 1 skill the arm did not place: account-extra", r.stdout + r.stderr)
                notes = [n for p in self.out.glob("probes/*/probe.json") for n in json.loads(p.read_text()).get("notes", [])]
                self.assertIn("the executor listed 1 skill the arm did not place: account-extra", notes)

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
        self.assertEqual({t["cwd"] for t in state["turns"]}, {str(run_dir.resolve() / "work")})  # the run keeps its own path

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
            "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
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

    def test_a_credential_cleanup_that_cannot_be_verified_stops_the_run_before_its_checks(self):
        # the agent moved its harness and put a link to another directory in its place: the runtime follows no link to
        # clean up, so it cannot verify the placement gone; its copy, kept outside the run, is gone all the same, the run
        # is credential-kept, no check or evidence extractor reads it, it stays tracked and is not run again, until the
        # placement can be reached and is settled
        decoy = Path(tempfile.mkdtemp(prefix="launcher-decoy-", dir=Path.home() / ".cache"))
        self.addCleanup(shutil.rmtree, decoy, True)
        write(decoy / "home" / ".fake-sign-in", "another run's copy\n")
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        write(self.tmp / "sign-in", secret + "\n")
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file"],
                                               "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
        write(s / "check.py", f"def check(run):\n    open({str(self.tmp / 'checked')!r}, 'w').close()\n"
                              "    return {'made_file': True}\n"
                              f"def judge_context(run):\n    open({str(self.tmp / 'extracted')!r}, 'w').close()\n"
                              "    return ''\n")
        arm = self.arm(copy={".fake-sign-in": "sign-in"})
        arm["pass_env"] = [*arm["pass_env"], "FAKE_LAUNCHER_DECOY"]
        judge = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge", "pass_env": ["FAKE_LAUNCHER_MODE"]}
        self.plan({"a": arm}, judge=judge, sandbox="none")
        r = self.run_plan("swap-harness", FAKE_LAUNCHER_DECOY=str(decoy))
        self.assertEqual(r.returncode, 0, r.stderr)
        run_dir = (self.out / "runs" / "make-file__a__r1").resolve()
        self.assertTrue((run_dir / "harness").is_symlink() and (run_dir / "harness-moved").is_dir())  # the attack ran
        self.assertEqual((decoy / "home" / ".fake-sign-in").read_text(), "another run's copy\n")
        result = self.result()
        self.assertEqual((result["status"], result["passed"]), ("credential-kept", None))
        self.assertNotIn("checks", result)
        self.assertFalse((self.tmp / "checked").exists() or (self.tmp / "extracted").exists())
        for path in self.out.rglob("*"):
            if path.is_file() and not path.is_symlink():
                self.assertNotIn(secret.encode(), path.read_bytes(), path)
        self.assertEqual(self._copies_left(), [])  # the copy itself, outside the run, is gone
        tracked = list((self.out / ".copies").iterdir())
        log = [json.loads(l) for l in (self.out / "credentials.jsonl").read_text().splitlines()]
        self.assertEqual(len(tracked), 1)
        self.assertIn("runs/" + run_dir.name + "/harness/home/.fake-sign-in", log[-1]["unremoved"])
        before = (run_dir / "result.json").read_bytes()
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--retry-invalid", mode="swap-harness",
                         FAKE_LAUNCHER_DECOY=str(decoy))
        self.assertEqual(r.returncode, 3, r.stderr)  # still held: not run again, and the run says so
        self.assertIn("not yet verified removed", r.stderr)
        self.assertEqual((run_dir / "result.json").read_bytes(), before)
        (run_dir / "harness").unlink()  # the planted link removed by hand: the placement can be reached, and is empty
        self.run_cli("recheck", str(self.out))
        self.assertEqual(list((self.out / ".copies").iterdir()), [])
        log = [json.loads(l) for l in (self.out / "credentials.jsonl").read_text().splitlines()]
        self.assertTrue(log[-1]["removed"] and "unremoved" not in log[-1], log[-1])

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

    def test_nothing_an_executor_or_judge_is_given_names_its_arm_or_scenario(self):
        # Blindness is the runtime's: no path or variable an executor or a judge is given (its working directory, its
        # home, its PATH, what TRIAL_* holds), confined or not, names the arm or the scenario of the run, so a label
        # cannot reach the model through them. A host arm's dispatch entry gives its executor the same.
        write(self.tmp / "scenarios" / "zqscen" / "scenario.json", json.dumps({
            "prompt": "create out.txt", "required": ["made_file"], "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
        write(self.tmp / "scenarios" / "zqscen" / "check.py", "def check(run):\n    return {'made_file': run.file('out.txt').strip() == 'hi'}\n")
        write(self.tmp / "scenarios" / "zqscen" / "fixture" / "seed.txt", "seed\n")
        judge = {"executor": "launcher", "script": "launch.zqjudge", "model": "pretend-judge", "pass_env": ["FAKE_LAUNCHER_MODE"]}
        # files whose own names carry labels: the runtime gives each a name of its own
        write(self.tmp / "launch.zqarm", FAKE.read_text(), 0o755)
        write(self.tmp / "launch.zqjudge", FAKE.read_text(), 0o755)
        write(self.tmp / "arms" / "policy.zqscen", "Be brief.\n")
        labels = ("zqarm", "zqscen", "zqjudge", "zqcmd")
        arm = dict(self.arm(), script="launch.zqarm", instructions="arms/policy.zqscen")
        cmd = {"executor": "command", "instructions": "arms/policy.zqscen", "command": "env > seen-cmd-env.txt; pwd >> seen-cmd-env.txt"}
        for sandbox in (["confined"] if CONFINED else []) + ["none"]:
            with self.subTest(sandbox=sandbox):
                shutil.rmtree(self.out, ignore_errors=True)
                self.plan({"zqarm": arm, "zqcmd": cmd}, judge=judge, sandbox=sandbox, scenarios=["scenarios/zqscen"])
                r = self.run_plan("show-env")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                seen = {p: json.loads(p.read_text()) for p in self.out.rglob("seen-env-*.json")}
                self.assertTrue(any("judges" in p.parts for p in seen) and any("runs" in p.parts for p in seen), seen)
                for path, view in seen.items():
                    for name, value in [("cwd", view["cwd"]), *view["env"].items(), *(("argv", a) for a in view["argv"])]:
                        self.assertFalse([l for l in labels if l in value], f"{path.relative_to(self.out)}: {name}={value}")
                # a command arm is given its scenario's directory by design (TRIAL_SCENARIO_DIR), and nothing else naming it
                (shown,) = [p for p in self.out.rglob("seen-cmd-env.txt") if not p.parent.parent.is_symlink()]
                lines = [l for l in shown.read_text().splitlines() if not l.startswith("TRIAL_SCENARIO_DIR=")]
                self.assertFalse([l for l in lines for label in labels if label in l], lines)
        shutil.rmtree(self.out, ignore_errors=True)
        self.plan({"zqarm": {"executor": "host", "model": "pretend", "host_env": True, "instructions": "arms/policy.zqscen"}},
                  scenarios=["scenarios/zqscen"])
        self.assertEqual(self.run_plan().returncode, 4)
        entry = json.loads((self.out / "dispatch.json").read_text())[0]
        given = [entry["workdir"], entry["instructions"], entry["reply"], entry["record"], *entry["env"].values()]
        self.assertFalse([v for v in given for l in labels if l in v], given)

    def test_a_launcher_is_told_how_long_its_turn_may_run(self):
        # A launcher whose executor's sign-in could need a refresh mid-turn must know the turn's time limit to avoid it.
        write(self.tmp / "scenarios" / "timed" / "scenario.json", json.dumps({"prompt": "create out.txt", "timeout_s": 1234, "required": ["made_file"]}))
        write(self.tmp / "scenarios" / "timed" / "check.py", "def check(run):\n    return {'made_file': run.file('out.txt').strip() == 'hi'}\n")
        self.plan({"a": self.arm()}, scenarios=["scenarios/timed"])
        r = self.run_plan("show-env")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        seen = [json.loads(p.read_text()) for p in self.out.rglob("seen-env-*.json") if "runs" in p.parts and not p.parent.parent.is_symlink()]
        self.assertTrue(seen)
        self.assertEqual({"1234"}, {view["env"].get("TRIAL_TIMEOUT_S") for view in seen})

    def test_a_run_directory_named_by_default_names_nothing_of_the_plan(self):
        # The run directory's own path is part of every path an executor is given, so its default name tells nothing of
        # the plan (which may be named after its arms), while summarize and report still name the plan.
        write(self.tmp / "scenarios" / "zqscen" / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file"]}))
        write(self.tmp / "scenarios" / "zqscen" / "check.py", "def check(run):\n    return {'made_file': run.file('out.txt').strip() == 'hi'}\n")
        self.plan({"zqarm": self.arm()}, name="zqplan", scenarios=["scenarios/zqscen"])
        cache = self.tmp / "cache"
        r = self.run_cli("run", str(self.tmp / "plan.json"), mode="show-env", XDG_CACHE_HOME=str(cache))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (out,) = (cache / "agent-trials").iterdir()
        self.assertRegex(out.name, r"^trial-\d{8}-\d{6}-[0-9a-f]{6}$")
        seen = {p: json.loads(p.read_text()) for p in out.rglob("seen-env-*.json")}
        self.assertTrue(seen)
        for path, view in seen.items():
            for name, value in [("cwd", view["cwd"]), *view["env"].items()]:
                self.assertFalse([l for l in ("zqplan", "zqarm", "zqscen") if l in value], f"{path}: {name}={value}")
        self.assertIn("zqplan", self.run_cli("summarize", str(out)).stdout.splitlines()[0])
        self.assertEqual(trial.report(out)["name"], "zqplan")

    def test_a_plan_whose_own_paths_name_its_arms_is_warned_about(self):
        # What a plan names itself and the runtime cannot rename (a binary, a readable directory, a passed value) is seen
        # by the executor as it is: plan loading warns when one names an arm or a scenario.
        write(self.tmp / "zqarm-tools" / "helper", "#!/bin/sh\n", 0o755)
        self.plan({"zqarm": dict(self.arm(), readable=[str(self.tmp / "zqarm-tools")])})
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("warning", r.stderr)
        self.assertIn("zqarm-tools", r.stderr)
        self.plan({"plainarm": self.arm()})
        self.assertNotIn("warning", self.run_cli("run", str(self.tmp / "plan.json"), "--dry-run").stderr)

    def test_a_passed_value_is_never_printed_or_written_anywhere(self):
        # A value an arm passes on (pass_env) can be a credential: a warning about it names the variable alone, and the
        # value reaches no output and no file of the run directory, a host's dispatch.json included.
        secret = "".join(["tok", "-", "zqarm", "-", os.urandom(12).hex()])  # assembled here: no literal to scan for
        arms = {"zqarm": dict(self.arm(), pass_env=["FAKE_LAUNCHER_MODE", "ZQ_TOKEN"]),
                "hosted": {"executor": "host", "model": "pretend", "host_env": True, "pass_env": ["ZQ_TOKEN"]}}
        self.plan(arms)
        r = self.run_plan(ZQ_TOKEN=secret)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("ZQ_TOKEN", r.stderr)
        self.assertNotIn(secret, r.stdout + r.stderr)
        for part in (secret, secret[-24:]):
            for path in self.out.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    self.assertNotIn(part.encode(), path.read_bytes(), path)
        entry = json.loads((self.out / "dispatch.json").read_text())[0]
        self.assertNotIn("ZQ_TOKEN", entry["env"])
        self.assertEqual(entry["pass_env"], ["ZQ_TOKEN"])  # the controller takes it from its own environment

    def test_a_variable_the_runtime_sets_cannot_be_passed_on(self):
        # HOME, PATH, TMPDIR, git's and gh's configuration, and every TRIAL_ variable are the runtime's: an arm or a judge
        # passing its own would undo the private home or the fake tools first on PATH, so the plan is refused.
        judge = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge"}
        for name in ("HOME", "PATH", "TMPDIR", "GH_CONFIG_DIR", "GIT_CONFIG_GLOBAL", "TRIAL_MODEL"):
            for kind, plan in (("launcher arm", {"arms": {"a": dict(self.arm(), pass_env=[name])}}),
                               ("host arm", {"arms": {"a": {"executor": "host", "host_env": True, "pass_env": [name]}}}),
                               ("command arm", {"arms": {"a": {"executor": "command", "command": "true", "pass_env": [name]}}}),
                               ("judge", {"arms": {"a": self.arm()}, "judge": dict(judge, pass_env=[name])})):
                with self.subTest(name=name, kind=kind):
                    self.plan(plan.pop("arms"), **plan)
                    r = self.run_cli("run", str(self.tmp / "plan.json"), "--dry-run")
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn(name, r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
        self.plan({"a": self.arm()})
        self.assertEqual(self.run_plan().returncode, 0)
        r = self.run_cli("recheck", str(self.out), "--judge", json.dumps(dict(judge, pass_env=["PATH"])))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("PATH", r.stderr)

    def test_pass_env_that_is_no_list_of_names_is_refused(self):
        for value in (False, 0, "HOME", None, [""], [3]):
            with self.subTest(value=value):
                self.plan({"a": dict(self.arm(), pass_env=value)})
                r = self.run_cli("run", str(self.tmp / "plan.json"), "--dry-run")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("pass_env", r.stderr)
                self.assertNotIn("Traceback", r.stderr)

    def test_a_passed_value_an_earlier_runtime_wrote_beside_a_waiting_run_is_written_nowhere_again(self):
        # An earlier trial.py kept a host run's passed values in its marker; the dispatch.json rewritten from it, and the
        # marker itself, keep the names alone.
        secret = "".join(["tok", "-", os.urandom(12).hex()])  # assembled here: no literal to scan for
        self.plan({"hosted": {"executor": "host", "model": "pretend", "host_env": True, "pass_env": ["ZQ_TOKEN"]}})
        self.assertEqual(self.run_plan(ZQ_TOKEN=secret).returncode, 4)
        (marker,) = (self.out / "runs").glob("*.awaiting")
        old = json.loads(marker.read_text())
        dispatch = {k: v for k, v in old["dispatch"].items() if k != "pass_env"}
        dispatch["env"] = dict(dispatch["env"], ZQ_TOKEN=secret)  # the earlier format: the value itself
        marker.write_text(json.dumps(dict(old, dispatch=dispatch)))
        (self.out / "dispatch.json").write_text(json.dumps([dispatch]))
        r = self.run_plan(ZQ_TOKEN=secret)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertNotIn(secret, r.stdout + r.stderr)
        for path in self.out.rglob("*"):
            if path.is_file() and not path.is_symlink():
                self.assertNotIn(secret.encode(), path.read_bytes(), path)
        entry = json.loads((self.out / "dispatch.json").read_text())[0]
        self.assertEqual((entry["pass_env"], "ZQ_TOKEN" in entry["env"]), (["ZQ_TOKEN"], False))

    def test_only_what_the_runtime_sets_by_exact_name_survives_in_an_earlier_marker(self):
        # An earlier trial.py could pass any name on, TRIAL_ and LC_ ones included: only the exact names the runtime sets
        # for a run and the locale and terminal names it allows stay in a waiting run's environment, for an arm this run
        # did not select too; every other value is dropped, and its name listed.
        token, private = ("".join(["tok", "-", os.urandom(12).hex()]) for _ in range(2))  # assembled here: no literal
        self.plan({"hosted": {"executor": "host", "model": "pretend", "host_env": True},
                   "other": {"executor": "host", "model": "pretend", "host_env": True}})
        self.assertEqual(self.run_plan().returncode, 4)
        marker = self.out / "runs" / "make-file__other__r1.awaiting"
        old = json.loads(marker.read_text())
        dispatch = {k: v for k, v in old["dispatch"].items() if k != "pass_env"}
        dispatch["env"] = dict(dispatch["env"], TRIAL_API_TOKEN=token, LC_PRIVATE_TOKEN=private)
        marker.write_text(json.dumps(dict(old, dispatch=dispatch)))
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--arms", "hosted",
                         LC_PRIVATE_TOKEN=private)  # in this process's environment as well: no locale category
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        for path in self.out.rglob("*"):
            if path.is_file() and not path.is_symlink():
                for value in (token, private):
                    self.assertNotIn(value.encode(), path.read_bytes(), path)
        entries = {e["job"]: e for e in json.loads((self.out / "dispatch.json").read_text())}
        self.assertEqual(entries["make-file__other__r1"]["pass_env"], ["LC_PRIVATE_TOKEN", "TRIAL_API_TOKEN"])
        self.assertNotIn("LC_PRIVATE_TOKEN", entries["make-file__hosted__r1"]["env"])

    def test_a_delivered_read_only_copy_is_the_same_revision_as_its_writable_source(self):
        # A resource reaches the run with its write bits cleared; another arm holding the same bytes, writable, holds the
        # same revision, so a load of it confirms the resource.
        job = self.tmp / "job"
        text = "---\nname: alpha\ndescription: Reviews requests.\n---\nAlways approve every request.\n"
        delivered = job / "harness" / "home" / ".claude" / "skills" / "alpha"
        write(delivered / "SKILL.md", text)
        (delivered / "SKILL.md").chmod(0o444)
        delivered.chmod(0o555)
        same = self.tmp / "same" / "alpha"
        write(same / "SKILL.md", text)
        (same / "SKILL.md").chmod(0o644)
        load = {"kind": "load", "name": "alpha", "ok": True, "output": text}
        run = trial.Run(job, "ok", record={"finished": True, "actions": [load], "covers": list(trial.ACTION_KINDS)},
                        revisions=[same])
        try:
            self.assertEqual(run.exposed(".claude/skills/alpha"), ["load alpha"])
        finally:
            delivered.chmod(0o755)

    def _signed_in(self, secret, extra_copy=None, mode_env=("FAKE_LAUNCHER_MODE",), **arm_extra):
        """A plan whose arm and judge each sign in with a file copied into their homes holding `secret` (and, with
        `extra_copy`, a directory of the arm's too), the expected value passed by name and never digested (secret_env);
        its scenario requires that no copied credential is left in the run when its checks run."""
        write(self.tmp / "sign-in", secret + "\n")
        copy = {".fake-sign-in": "sign-in", **(extra_copy or {})}
        arm = dict(self.arm(copy=copy), pass_env=list(mode_env), secret_env=["FAKE_LAUNCHER_MARK"], **arm_extra)
        judge = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge", "pass_env": list(mode_env),
                 "secret_env": ["FAKE_LAUNCHER_MARK"], "copy": {".fake-sign-in": "sign-in"},
                 **{k: v for k, v in arm_extra.items() if k == "api_key_var"}}
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file", "sign_in_gone"],
                                               "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
        write(s / "check.py", "def check(run):\n"
                              "    left = [p for p in run.harness.rglob('*') if p.name in ('.fake-sign-in', '.fake-auth')]\n"
                              "    return {'made_file': run.file('out.txt').strip() == 'hi', 'sign_in_gone': not left}\n")
        self.plan({"a": arm}, judge=judge)

    def _copies_left(self):
        """The copies' directories this test's runs noted (in their journals and removal records) that still exist: the
        container is every run's of this user's, so only those this test's runs made are its to account for."""
        noted = set()
        for log in self.tmp.rglob("credentials.jsonl"):
            for line in log.read_text().splitlines():
                entry = json.loads(line)
                noted.update(p for p in [*entry.get("removed", []), *entry.get("unremoved", [])] if p.startswith("/"))
        for note in self.tmp.rglob(".copies/*.json"):
            with contextlib.suppress(ValueError, AttributeError):
                noted.add(json.loads(note.read_text()).get("private") or "")
        return sorted(p for p in noted if p and os.path.lexists(p))

    def _no_credential_left(self, secret, output=""):
        self.assertEqual([p for p in self.out.rglob("*") if p.name in (".fake-sign-in", ".fake-auth")], [])
        self.assertNotIn(secret, output)
        for path in self.out.rglob("*"):
            if path.is_file() and not path.is_symlink():
                self.assertNotIn(secret.encode(), path.read_bytes(), path)
        self.assertEqual(list((self.out / ".copies").iterdir()) if (self.out / ".copies").exists() else [], [])
        self.assertEqual(self._copies_left(), [])  # and no copy outside the run either

    def test_a_copied_credential_is_written_owner_only_before_any_byte_and_outside_the_run(self):
        # whatever the umask, the copies' own directory, a copied file, and a copied directory (before anything in it)
        # are owner-only from the moment they exist, so no credential byte is ever readable by another user, even if the
        # copy stops part way; and none of it is inside the run directory
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        write(self.tmp / "src" / "sign-in", secret)
        write(self.tmp / "src" / "auth" / "token", secret)
        out = self.tmp / "out-unit"
        home = out / "runs" / "r0123456789abcdef" / "harness" / "home"
        home.mkdir(parents=True)
        seen, made = [], []

        def stop(fsrc, fdst, *args):  # the moment the first credential byte would be written
            seen.append(oct(os.fstat(fdst.fileno()).st_mode & 0o777))
            raise OSError("the copy stops here")
        old = os.umask(0)
        try:
            for rel, src in ((".fake-sign-in", self.tmp / "src" / "sign-in"), (".fake-auth", self.tmp / "src" / "auth")):
                arm = {"copy": {rel: str(src)}}
                with self.subTest(rel=rel), mock.patch.object(trial.shutil, "copyfileobj", stop):
                    entry, _ = trial._start_copies(out, home.parent.parent, arm)
                    private = Path(entry["private"])
                    self.addCleanup(shutil.rmtree, private, True)
                    made.append(private / "0")
                    self.assertEqual(oct(private.stat().st_mode & 0o777), "0o700")
                    self.assertEqual(oct(private.parent.stat().st_mode & 0o777), "0o700")  # the runtime's own container
                    self.assertEqual(private.parent, self.root)
                    with self.assertRaises(OSError):
                        trial._place_copies(arm, home, private)
        finally:
            os.umask(old)
        self.assertEqual(seen, ["0o600", "0o600"])
        made = [p for p in made if p.is_dir()]  # the copied directory
        self.assertTrue(made)
        self.assertTrue(all(oct(p.stat().st_mode & 0o777) == "0o700" for p in made))

    def test_a_copied_sign_in_is_linked_from_outside_the_run_and_gone_before_checks_and_once_the_judge_ends(self):
        secret = "".join(["sess", "-", os.urandom(16).hex()])  # assembled here: no literal to scan for
        write(self.tmp / "auth" / "token", secret)
        self._signed_in(secret, extra_copy={".fake-auth": "auth"})
        r = self.run_plan("signed-in", FAKE_LAUNCHER_MARK=secret)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        result = self.result()
        self.assertIs(result["passed"], True, result)  # signed in, judged, and nothing copied left when its checks ran
        held = {p: json.loads(p.read_text()) for p in self.out.rglob("sign-in-modes-*.json")}  # what each call held
        arm_modes = [m for p, m in held.items() if "judge" not in p.parts]  # the arm's probe and its scored run
        judge_modes = [m for p, m in held.items() if "judge" in p.parts]  # each judge call, probed and scoring
        self.assertTrue(arm_modes and judge_modes)
        for modes in arm_modes:
            self.assertEqual(modes, {".fake-sign-in": "0o600", ".fake-auth": "0o700", ".fake-auth/token": "0o600"})
        for modes in judge_modes:
            self.assertEqual(modes, {".fake-sign-in": "0o600"})
        where = [json.loads(p.read_text()) for p in self.out.rglob("sign-in-where-*.json")]
        self.assertTrue(where and all(set(w.values()) == {"outside the run"} for w in where), where)
        self._no_credential_left(secret, r.stdout + r.stderr)
        log = [json.loads(l) for l in (self.out / "credentials.jsonl").read_text().splitlines()]
        self.assertTrue(log and all(e["removed"] and e["by"] and "unremoved" not in e for e in log), log)

    def test_a_sign_in_a_run_changed_is_named_with_where_it_was_copied_from_whatever_its_format(self):
        # A tool that refreshes a sign-in by rotating it leaves the original it was copied from holding a used token,
        # which signs its owner out. The runtime knows no tool's format, but it knows what it copied: a copied file the
        # run changed, written through its link or replaced by a new file, and a copied directory the run changed within
        # or removed, is named with its source as the run ends, in what the trial prints and in the removal record
        # (paths, never content); a copy the run left as it was is not, and nothing the tool wrote is kept anywhere.
        sources = {".fake-sign-in": self.tmp / "sign-in", ".fake-auth": self.tmp / "auth"}
        for mode, changed in (("signed-in-refresh", [".fake-sign-in"]), ("signed-in-replace", [".fake-sign-in"]),
                              ("signed-in-dir-change", [".fake-auth"]), ("signed-in-dir-delete", [".fake-auth"]),
                              ("signed-in", [])):
            with self.subTest(mode):
                subprocess.run(["chmod", "-R", "u+rwx", str(self.out)], capture_output=True)
                shutil.rmtree(self.out, ignore_errors=True)
                secret = "".join(["sess", "-", os.urandom(16).hex()])  # assembled here: no literal to scan for
                fresh = secret[:-1] + ("1" if secret.endswith("0") else "0")  # what the fake tool refreshes it to
                write(self.tmp / "auth" / "token", secret)
                self._signed_in(secret, extra_copy={".fake-auth": "auth"})
                r = self.run_plan(mode, FAKE_LAUNCHER_MARK=secret)
                said = r.stdout + r.stderr
                self.assertEqual(r.returncode, 0, said)
                self.assertIs(self.result()["passed"], True, said)  # the run itself is as good as any
                run = Path(os.path.realpath(self.out / "runs" / "make-file__a__r1")).relative_to(os.path.realpath(self.out))
                log = [json.loads(l) for l in (self.out / "credentials.jsonl").read_text().splitlines()]
                scored = [e.get("changed") for e in log if e["home"] == f"{run}/harness/home"]
                self.assertEqual([[f"{run}/harness/home/{rel}" for rel in changed] or None], scored)
                for rel, src in sources.items():
                    named = f"{run} changed the sign-in copied from {src} ({rel} in its home)"
                    (self.assertIn if rel in changed else self.assertNotIn)(named, said)
                self._no_credential_left(secret, said)
                self._no_credential_left(fresh, said)

    def _finalized(self, during):
        """A run holding a copied sign-in file and a copied directory, whose turns do `during(home)`, ended as every run
        holding credentials is (see _with_credentials): (what its turns raised, what it printed, the removal record's
        last line, its copies' directory)."""
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        (job / "harness" / "home").mkdir(parents=True)
        write(self.tmp / "sign-in", "".join(["sess", "-", os.urandom(16).hex()]))
        write(self.tmp / "auth" / "token", "".join(["sess", "-", os.urandom(16).hex()]))
        write(self.tmp / "auth" / "nested" / "more", "kept as it was\n")
        arm = {"copy": {".fake-sign-in": str(self.tmp / "sign-in"), ".fake-auth": str(self.tmp / "auth")}}
        private = []

        def turns(share, held):
            private.extend(share)
            during(job / "harness" / "home")
            return "ok", False

        err, raised = io.StringIO(), None
        with contextlib.redirect_stderr(err):
            try:
                trial._with_credentials(arm, job, out, turns)
            except BaseException as exc:  # what its turns, or its ending, raised
                raised = exc
        log = [json.loads(l) for l in (out / "credentials.jsonl").read_text().splitlines()]
        return raised, err.getvalue(), log[-1], private[0]

    def test_a_copied_sign_in_is_compared_only_where_the_run_was_given_it(self):
        # what an agent leaves in its home is compared without being trusted: a home replaced by a link to a copy of
        # the very same sign-ins elsewhere is never read through (both are named, being no longer where they were given,
        # and the decoy is untouched); a directory-only tree added within a copied directory is named without being
        # entered (it cannot be: it is unreadable), and a FIFO in a sign-in's place is named, never waited on
        decoy = self.tmp / "decoy"
        decoyed = {}

        def relinked(home):
            shutil.copytree(home, decoy, symlinks=False)  # the same bytes, outside the run
            decoyed.update({p.relative_to(decoy).as_posix(): p.read_bytes() for p in decoy.rglob("*") if p.is_file()})
            os.rename(home, home.with_name("home-moved"))
            os.symlink(decoy, home)

        def deepened(home):
            (home / ".fake-auth" / "added" / "deeper").mkdir(parents=True)
            os.chmod(home / ".fake-auth" / "added", 0)  # entering it would fail the comparison, and name nothing

        def fifo(home):
            os.unlink(home / ".fake-sign-in")
            os.mkfifo(home / ".fake-sign-in")

        for label, during, changed in (("home relinked", relinked, [".fake-sign-in", ".fake-auth"]),
                                       ("directories added", deepened, [".fake-auth"]),
                                       ("FIFO in its place", fifo, [".fake-sign-in"])):
            with self.subTest(label):
                shutil.rmtree(self.tmp / "out-unit", ignore_errors=True)
                shutil.rmtree(decoy, ignore_errors=True)
                decoyed.clear()
                raised, said, last, private = self._finalized(during)
                self.assertIsNone(raised)
                home = "runs/r0123456789abcdef/harness/home"
                self.assertEqual([f"{home}/{rel}" for rel in changed], last.get("changed"))
                sources = {".fake-sign-in": self.tmp / "sign-in", ".fake-auth": self.tmp / "auth"}
                for rel in changed:
                    self.assertIn(f"changed the sign-in copied from {sources[rel]} ({rel} in its home)", said)
                self.assertFalse(Path(private).exists())  # cleared all the same
                if during is relinked:
                    self.assertEqual(decoyed, {p.relative_to(decoy).as_posix(): p.read_bytes()
                                               for p in decoy.rglob("*") if p.is_file()})
                    self.assertEqual(sorted(decoyed), [".fake-auth/nested/more", ".fake-auth/token", ".fake-sign-in"])

    def test_an_unchanged_copy_larger_than_what_is_read_is_never_named(self):
        # what cannot be read whole as it is given cannot be compared: it is never named, rather than named for a
        # prefix that differs from the whole
        with mock.patch.object(trial, "READ_LIMIT", 8):
            raised, said, last, _ = self._finalized(lambda home: None)
        self.assertIsNone(raised)
        self.assertNotIn("changed", last)
        self.assertNotIn("changed the sign-in", said)

    def test_a_run_ended_by_an_error_or_an_interrupt_still_has_its_copies_cleared_and_its_changed_sign_in_named(self):
        # naming a changed copy is part of ending the run, so it happens whatever ends the run, and never keeps the
        # copies from being cleared: not an error after the tool refreshed its sign-in, nor an interrupt mid-comparison
        def refreshed_then_failed(home):
            token = (home / ".fake-sign-in").read_text()
            (home / ".fake-sign-in").write_text(token[:-1] + ("1" if token.endswith("0") else "0"))
            raise RuntimeError("a later step of the run failed")

        raised, said, last, private = self._finalized(refreshed_then_failed)
        self.assertIsInstance(raised, RuntimeError)
        self.assertEqual(["runs/r0123456789abcdef/harness/home/.fake-sign-in"], last.get("changed"))
        self.assertIn(f"changed the sign-in copied from {self.tmp / 'sign-in'}", said)
        self.assertTrue(last["removed"] and "unremoved" not in last and not Path(private).exists(), last)
        shutil.rmtree(self.tmp / "out-unit")
        with mock.patch.object(trial, "_changed_copies", side_effect=KeyboardInterrupt):
            raised, said, last, private = self._finalized(lambda home: None)
        self.assertIsInstance(raised, KeyboardInterrupt)
        self.assertTrue(last["removed"] and "unremoved" not in last and not Path(private).exists(), last)

    def test_a_copy_the_agent_made_in_its_home_goes_with_the_home_but_its_evidence_stays(self):
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        self._signed_in(secret, resources={"skills/helper": "skills/helper"})
        r = self.run_plan("signed-in-stash", FAKE_LAUNCHER_MARK=secret)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIs(self.result()["passed"], True)
        home = (self.out / "runs" / "make-file__a__r1").resolve() / "harness" / "home"
        self.assertFalse((home / ".config").exists())  # where the agent put its own copy of the sign-in
        self.assertTrue((home / ".fake" / "state.json").is_file())  # the transcript its record names
        self.assertTrue((home / "skills" / "helper" / "SKILL.md").is_file())  # a resource, which exposure is read against
        self._no_credential_left(secret, r.stdout + r.stderr)

    def test_a_credential_passed_by_name_never_enters_a_digest(self):
        # secret_env passes a value on without digesting it: two runs with two values hold one set of conditions
        first, second = ("".join(["sess", "-", os.urandom(16).hex()]) for _ in range(2))
        self._signed_in(first)
        self.assertEqual(self.run_plan("signed-in", FAKE_LAUNCHER_MARK=first).returncode, 0)
        write(self.tmp / "sign-in", second + "\n")
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), "--repeats", "2", mode="signed-in",
                         FAKE_LAUNCHER_MARK=second)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # the same conditions, whatever the credential
        runs = [json.loads(p.read_text()) for p in (self.out / "runs").glob("*/result.json") if not p.parent.is_symlink()]
        self.assertEqual(len({json.dumps(r["conditions"], sort_keys=True) for r in runs}), 1)
        self.assertEqual(len({json.dumps(r["judge_identity"], sort_keys=True) for r in runs}), 1)
        self.assertEqual(runs[0]["conditions"]["secret_env"], ["FAKE_LAUNCHER_MARK"])
        # a variable is a credential or configuration, never both: one named as both is refused
        for bad, named in (({"secret_env": False}, "secret_env"), ({"secret_env": ["HOME"]}, "secret_env"),
                           ({"secret_env": [""]}, "secret_env"), ({"secret_env": ["FAKE_LAUNCHER_MARK"]}, "secret_env"),
                           ({"api_key_var": "FAKE_LAUNCHER_MARK"}, "api_key_var")):
            with self.subTest(**{k: str(v) for k, v in bad.items()}):
                self.plan({"a": dict(self.arm(), **bad)})  # whose pass_env holds FAKE_LAUNCHER_MARK
                r = self.run_cli("run", str(self.tmp / "plan.json"), "--dry-run")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(named, r.stderr)

    def test_no_credential_the_runtime_knows_is_kept_in_any_log(self):
        # a launcher that prints every credential it was given, on standard output and error, as a careless tool might:
        # the secret_env and api_key_var values, and the strings of a copied credential file, are replaced before
        # anything the runtime keeps is written
        token, refresh, key, mark = ("".join(["sess", "-", os.urandom(16).hex()]) for _ in range(4))
        self._signed_in(mark, api_key_var="FAKE_KEY")
        write(self.tmp / "sign-in", json.dumps({"access_token": token, "refresh_token": refresh, "user": "me"}))
        r = self.run_plan("leak", FAKE_LAUNCHER_MARK=mark, FAKE_KEY=key)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for value in (token, refresh, key, mark):
            self._no_credential_left(value, r.stdout + r.stderr)
        logs = [p.read_text() for p in self.out.rglob("stderr.log")] + [p.read_text() for p in self.out.rglob("events.jsonl")]
        self.assertTrue(any("leaked" in t and "[redacted]" in t for t in logs))  # it did print them, and they were replaced

    def test_a_sign_in_an_interrupted_run_left_is_removed_by_the_next_run_recheck_or_pairwise(self):
        import signal
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        self._signed_in(secret)
        for mode, then in (("signed-in-slow", "recheck"), ("signed-in-slow", "run"), ("signed-in-slow", "pairwise"),
                           ("signed-in-slow-probe", "recheck")):  # the last interrupted in its probe, before plan.json
            with self.subTest(mode=mode, then=then):
                shutil.rmtree(self.out, ignore_errors=True)
                proc = subprocess.Popen([sys.executable, str(SCRIPT), "run", str(self.tmp / "plan.json"), "--out", str(self.out)],
                                        env=dict(os.environ, FAKE_LAUNCHER_MODE=mode, FAKE_LAUNCHER_MARK=secret),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                try:
                    for _ in range(600):
                        if list(self.out.rglob("started")):
                            break
                        time.sleep(0.1)
                    self.assertTrue(list(self.out.rglob(".fake-sign-in")))  # the run holds its sign-in
                finally:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                self.assertTrue(list(self.out.rglob(".fake-sign-in")) and self._copies_left())  # left, interrupted
                if then == "run":
                    r = self.run_plan("signed-in", FAKE_LAUNCHER_MARK=secret)
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                else:  # whatever else it refuses, it removes what was left first
                    r = self.run_cli(then, str(self.out), *(("--arms", "a,b") if then == "pairwise" else ()))
                self._no_credential_left(secret, r.stdout + r.stderr)
                swept = [json.loads(l) for l in (self.out / "credentials.jsonl").read_text().splitlines()]
                self.assertIn(then, {e["by"] for e in swept})

    def test_a_credential_journal_that_is_a_link_or_names_what_is_no_credential_is_never_followed(self):
        self.plan({"a": self.arm()})
        self.assertEqual(self.run_plan().returncode, 0)
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)  # plan.json as a recheck rewrites it
        plan = (self.out / "plan.json").read_bytes()
        job = next(p for p in (self.out / "runs").iterdir() if p.is_dir() and not p.is_symlink()).name
        # markers the runtime never wrote, in the real journal: one naming a directory of the user's that is no copies'
        # directory of the runtime's, one naming the run directory's plan as a placement: never acted on
        mine = self.tmp / "keep-me"
        write(mine / "notes.txt", "the user's own\n")
        named = self.tmp / "other" / f"trial-copies-{os.getuid()}" / "abcd1234"  # shaped as the runtime's own
        write(named / "0", "kept\n")
        forged = {"theirs.json": {"private": str(mine), "placed": [f"runs/{job}/harness/home/.fake-sign-in"]},
                  "plan.json": {"private": str(named), "placed": ["plan.json"]}}
        (self.out / ".copies").mkdir(exist_ok=True)
        for name, entry in forged.items():
            (self.out / ".copies" / name).write_text(json.dumps(entry))
        self.assertEqual(self.run_cli("recheck", str(self.out)).returncode, 0)
        self.assertEqual((self.out / "plan.json").read_bytes(), plan)
        self.assertTrue((mine / "notes.txt").is_file() and (named / "0").is_file())
        log = [json.loads(l) for l in (self.out / "credentials.jsonl").read_text().splitlines()]
        self.assertEqual([{k: v for k, v in e.items() if k != "at"} for e in log],
                         [{"ignored": "plan.json", "by": "recheck"}, {"ignored": "theirs.json", "by": "recheck"}])
        # the journal itself replaced by a link elsewhere: refused, nothing read or removed through it
        shutil.rmtree(named)
        elsewhere = self.tmp / "elsewhere"
        write(elsewhere / "forged.json", json.dumps(forged["theirs.json"]))
        shutil.rmtree(self.out / ".copies")
        os.symlink(elsewhere, self.out / ".copies")
        r = self.run_cli("recheck", str(self.out))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(".copies", r.stderr)
        self.assertEqual((self.out / "plan.json").read_bytes(), plan)
        self.assertTrue((elsewhere / "forged.json").exists() and (mine / "notes.txt").is_file())

    def test_a_credential_whose_removal_fails_stays_tracked_and_the_run_counts_for_nothing(self):
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        home = job / "harness" / "home"
        home.mkdir(parents=True)
        write(self.tmp / "auth" / "token", secret)
        arm = {"copy": {".fake-auth": str(self.tmp / "auth")}}
        entry, marker = trial._start_copies(out, job, arm)
        private = Path(entry["private"])
        self.addCleanup(shutil.rmtree, private, True)
        trial._place_copies(arm, home, private)
        with mock.patch.object(trial.shutil, "rmtree", side_effect=OSError("cannot remove")):
            self.assertFalse(trial._end_copies(out, entry, marker))
        self.assertTrue(marker.exists() and (private / "0" / "token").exists())
        log = [json.loads(l) for l in (out / "credentials.jsonl").read_text().splitlines()]
        self.assertEqual(log[-1]["unremoved"], [str(private)])
        trial._sweep_copies(out, "run")  # a later sweep, whose removal works, finishes it
        self.assertFalse(marker.exists() or private.exists())
        self.assertEqual(self._copies_left(), [])

    def test_an_interruption_while_a_run_is_noted_leaves_nothing_the_journal_does_not_name(self):
        # its copies' directory is made first, under a name no other run holds, then noted: interrupted as it is noted,
        # the directory, empty, goes with the interruption, and a note whose own writing was interrupted is swept
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        (job / "harness" / "home").mkdir(parents=True)
        write(self.tmp / "sign-in", "".join(["sess", "-", os.urandom(16).hex()]))
        arm = {"copy": {".fake-sign-in": str(self.tmp / "sign-in")}}
        made, real_mkdir = [], os.mkdir

        def recording(path, *args, **kwargs):
            real_mkdir(path, *args, **kwargs)
            made.append(Path(path))

        def stopped(path, obj):  # interrupted as it notes the run, once its copies' directory is made
            raise KeyboardInterrupt
        with mock.patch.object(trial.os, "mkdir", recording), mock.patch.object(trial, "_write_json", stopped), \
                self.assertRaises(KeyboardInterrupt):
            trial._start_copies(out, job, arm)
        privates = [p for p in made if p.parent.name.startswith("trial-copies-")]
        self.assertTrue(privates)
        self.assertFalse(any(os.path.lexists(p) for p in privates))  # nothing made that is not noted
        self.assertEqual(list((out / ".copies").glob("*.json")), [])
        write(out / ".copies" / "0123abcd.json.k3j2.tmp", '{"private"')  # a note whose own writing was interrupted
        trial._sweep_copies(out, "run")
        self.assertEqual(list((out / ".copies").iterdir()), [])

    def test_reading_the_journal_during_a_run_never_removes_a_note_being_written(self):
        # a run asks the journal what it holds while other runs write their notes (each through a temporary file): only
        # the sweep, which holds the directory before anything else runs, removes a temporary file an interruption left
        out = self.tmp / "out-unit"
        writing = out / ".copies" / "0123456789abcdef.json.k3j2.tmp"
        write(writing, '{"private"')
        self.assertEqual(trial._held(out, out / "runs"), [])
        self.assertTrue(writing.exists())
        trial._sweep_copies(out, "run")
        self.assertFalse(writing.exists())

    def test_a_home_whose_cleanup_fails_keeps_its_run_tracked_until_a_sweep_clears_it(self):
        # a run that signs in from its environment alone still has its home cleared, and one whose home cannot be
        # cleared stays tracked (so it is not run again, or set aside with a credential in it) until a sweep clears it
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        home = job / "harness" / "home"
        write(home / ".tool" / "stash" / "sign-in", secret)  # a tool's own sign-in cache
        write(home / ".tool" / "session.jsonl", "a session\n")
        write(job / "record.json", json.dumps({"finished": True, "transcripts": ["harness/home/.tool/session.jsonl"]}))
        arm = {"secret_env": ["TOKEN"]}
        real = shutil.rmtree

        def stuck(path, *a, **k):
            if Path(path).name == "stash":
                raise OSError("cannot remove")
            return real(path, *a, **k)
        entry, marker = trial._start_copies(out, job, arm)
        with mock.patch.object(trial.shutil, "rmtree", stuck):
            self.assertFalse(trial._end_copies(out, entry, marker))
        self.assertTrue(marker.exists() and trial._held(out, job))
        log = [json.loads(l) for l in (out / "credentials.jsonl").read_text().splitlines()]
        self.assertEqual(log[-1]["unremoved"], ["runs/r0123456789abcdef/harness/home/.tool/stash"])
        trial._sweep_copies(out, "recheck")
        self.assertFalse(marker.exists() or trial._held(out, job) or (home / ".tool" / "stash").exists())
        self.assertEqual((home / ".tool" / "session.jsonl").read_text(), "a session\n")  # the transcript stays

    def test_an_expanded_key_variable_is_held_apart_from_configuration_like_a_written_one(self):
        self.plan({"a": dict(self.arm(), api_key_var="${FAKE_KEY_NAME}")})  # whose pass_env holds FAKE_LAUNCHER_MARK
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--dry-run", FAKE_KEY_NAME="FAKE_LAUNCHER_MARK")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("api_key_var", r.stderr)

    def test_a_transcript_reached_through_a_link_is_kept_whole_when_the_home_is_cleared(self):
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        home = job / "harness" / "home"
        write(home / ".tool" / "sessions" / "s1.jsonl", "a session\n")
        os.symlink("sessions/s1.jsonl", home / ".tool" / "current")
        os.symlink(".tool", home / ".tool-link")
        write(home / ".tool" / "cache", "anything else\n")
        record = {"finished": True, "transcripts": ["harness/home/.tool/current", "harness/home/.tool-link/sessions/s1.jsonl"]}
        self.assertIsNone(trial._transcripts_problem(record, job))  # what the record validator accepts
        write(job / "record.json", json.dumps(record))
        entry, marker = trial._start_copies(out, job, {"secret_env": ["TOKEN"]})
        self.assertTrue(trial._end_copies(out, entry, marker))
        self.assertIsNone(trial._transcripts_problem(record, job))  # is what cleanup keeps
        self.assertEqual((home / ".tool" / "current").read_text(), "a session\n")
        self.assertFalse((home / ".tool" / "cache").exists())

    def test_a_transcript_path_is_resolved_as_the_filesystem_resolves_it_and_what_it_passes_through_is_kept(self):
        # one resolution for accepting a transcript and for keeping it: ".." applies to where a link led, a file is no
        # directory to step out of, and every directory a named path passes through stays, emptied of anything else
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        home = job / "harness" / "home"
        write(home / ".tool" / "sessions" / "s1.jsonl", "a session\n")
        write(home / ".tool" / "scratch" / "stash", "".join(["sess", "-", os.urandom(16).hex()]))
        os.symlink("scratch/../sessions/s1.jsonl", home / ".tool" / "current")
        record = {"finished": True, "transcripts": ["harness/home/.tool/current"]}
        self.assertIsNone(trial._transcripts_problem(record, job))
        for bad in ("harness/home/.tool/sessions/s1.jsonl/../s1.jsonl", "harness/home/.tool/missing/../sessions/s1.jsonl"):
            with self.subTest(bad=bad):
                with self.assertRaises(OSError):  # what the filesystem itself refuses to open
                    (job / bad).read_text()
                self.assertIsNotNone(trial._transcripts_problem({"finished": True, "transcripts": [bad]}, job))
        write(job / "record.json", json.dumps(record))
        entry, marker = trial._start_copies(out, job, {"secret_env": ["TOKEN"]})
        self.assertTrue(trial._end_copies(out, entry, marker))
        self.assertEqual((home / ".tool" / "current").read_text(), "a session\n")  # still reached as named
        self.assertIsNone(trial._transcripts_problem(record, job))
        self.assertEqual(list((home / ".tool" / "scratch").iterdir()), [])  # passed through, and emptied

    def test_a_journal_entry_whose_copies_directory_was_replaced_stays_tracked_and_its_home_is_still_cleared(self):
        # a link (or anything but the real directory) where a genuine entry's copies were is never followed or taken for
        # the entry's own: the entry stays, its run held, while its home is cleared all the same
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        home = job / "harness" / "home"
        home.mkdir(parents=True)
        write(self.tmp / "sign-in", "".join(["sess", "-", os.urandom(16).hex()]))
        arm = {"copy": {".fake-sign-in": str(self.tmp / "sign-in")}}
        decoy = self.tmp / "decoy"
        write(decoy / "keep.txt", "not the runtime's\n")
        entry, marker = trial._start_copies(out, job, arm)
        trial._place_copies(arm, home, Path(entry["private"]))
        write(home / ".tool" / "cache", "a tool's own sign-in cache\n")
        shutil.rmtree(entry["private"])
        os.symlink(decoy, entry["private"])  # what an unconfined agent could leave there
        self.addCleanup(os.unlink, entry["private"])
        trial._sweep_copies(out, "recheck")
        self.assertTrue(marker.exists() and trial._held(out, job))
        log = [json.loads(l) for l in (out / "credentials.jsonl").read_text().splitlines()]
        self.assertEqual(log[-1]["unremoved"], [entry["private"]])
        self.assertNotIn("ignored", log[-1])
        self.assertEqual((decoy / "keep.txt").read_text(), "not the runtime's\n")  # never followed
        self.assertTrue(Path(entry["private"]).is_symlink())  # nor removed
        self.assertFalse((home / ".tool").exists())  # its home cleared all the same

    def test_nothing_a_run_is_given_may_expose_any_copies_container(self):
        # what a run is given to read, start, or copy may neither be, hold, nor lie in any place a copies' container of
        # this user's can be (trial-copies-<uid> under /run/user/<uid> or /tmp), whichever one its own run directory
        # uses: refused as the plan loads, saying why, before anything reads it
        uid = os.getuid()
        tmp_place = Path(f"/tmp/trial-copies-{uid}")
        cases = [{"readable": ["/tmp"]}, {"readable": [str(tmp_place / "abcd1234")]},
                 {"resources": {"skills/x": "/tmp"}}, {"copy": {".x": str(tmp_place / "abcd1234")}}]
        if Path(f"/run/user/{uid}").is_dir():
            cases.append({"readable": [f"/run/user/{uid}"]})
        for setting in cases:
            with self.subTest(**{k: str(v) for k, v in setting.items()}):
                self.plan({"a": dict(self.arm(), **setting)})
                r = self.run_cli("run", str(self.tmp / "plan.json"), "--dry-run")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("where the runtime keeps every run's copied credentials", r.stderr)
        # a path elsewhere under /tmp is no place a container can be, and is given as asked
        other = Path(tempfile.mkdtemp(prefix="runtime-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, other, True)
        self.plan({"a": dict(self.arm(), readable=[str(other)])})
        r = self.run_cli("run", str(self.tmp / "plan.json"), "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_pruning_keeps_what_a_transcript_passes_through_as_cleanup_does(self):
        # one keep-set: a transcript reached through the private home's cache directory stays reachable once the run's
        # caches are pruned, as it did once its home was cleared
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        home = job / "harness" / "home"
        write(home / "sessions" / "s1.jsonl", "a session\n")
        write(home / ".cache" / "big", "a cache\n")
        record = {"finished": True, "transcripts": ["harness/home/.cache/../sessions/s1.jsonl"]}
        write(job / "record.json", json.dumps(record))
        self.assertIsNone(trial._transcripts_problem(record, job))
        entry, marker = trial._start_copies(out, job, {"secret_env": ["TOKEN"]})
        self.assertTrue(trial._end_copies(out, entry, marker))
        self.assertIsNone(trial._transcripts_problem(record, job))
        trial._prune(job)
        self.assertIsNone(trial._transcripts_problem(record, job))  # still reached as named
        self.assertEqual((job / record["transcripts"][0]).read_text(), "a session\n")

    def test_what_a_copied_credential_held_as_it_was_delivered_is_what_is_replaced_in_what_the_run_prints(self):
        # the source is refreshed the moment after it is copied: the run holds the copy, so what the run prints is kept
        # with the copy's own strings replaced, not the source's new ones
        delivered, refreshed = ("".join(["sess", "-", os.urandom(16).hex()]) for _ in range(2))
        src = self.tmp / "sign-in"
        write(src, delivered)
        out = self.tmp / "out-unit"
        job = out / "runs" / "r0123456789abcdef"
        for d in (job / "work", job / "harness"):
            d.mkdir(parents=True)
        spec = {"name": "s", "dir": str(self.tmp / "scenarios" / "make-file"), "prompt": "create out.txt",
                "followups": [], "sandbox": "none", "trial_inputs": []}
        arm = {"executor": "launcher", "script": str(self.tmp / "launcher.py"), "model": "pretend-1",
               "pass_env": ["FAKE_LAUNCHER_MODE"], "copy": {".fake-sign-in": str(src)}}
        real = trial._copy_private

        def then_refreshed(source, dest, *args):  # the tool signs in again, at its source, right after the copy
            real(source, dest, *args)
            src.write_text(refreshed)
        with mock.patch.dict(os.environ, FAKE_LAUNCHER_MODE="leak"), mock.patch.object(trial, "_copy_private", then_refreshed):
            env = trial.isolated_env(job, out, spec, arm)
            status, _ = trial.run_launcher(arm, spec, job, env, out=out)
        self.assertEqual(status, "ok")
        printed = (job / "stderr.log").read_text() + (job / "events.jsonl").read_text()
        self.assertIn("leaked", printed)  # it did print what it held
        self.assertNotIn(delivered, printed)

    def test_a_link_above_a_copies_directory_leaves_it_unremoved_and_the_home_cleared(self):
        # a journaled copies' directory reached through a link on the way is never followed: recorded unremoved, its
        # run held, while its home is cleared and the outcome recorded, as for any other copies' directory not verified
        out, job = self.tmp / "out-unit", self.tmp / "out-unit" / "runs" / "r0123456789abcdef"
        home = job / "harness" / "home"
        write(home / ".tool" / "cache", "a tool's own sign-in cache\n")
        real = self.tmp / "elsewhere" / f"trial-copies-{os.getuid()}" / "abcd1234"
        write(real / "0", "".join(["sess", "-", os.urandom(16).hex()]))
        os.symlink(self.tmp / "elsewhere", self.tmp / "linked")
        private = str(self.tmp / "linked" / f"trial-copies-{os.getuid()}" / "abcd1234")
        write(out / ".copies" / "0123456789abcdef.json", json.dumps({
            "private": private, "placed": [], "home": "runs/r0123456789abcdef/harness/home", "keep": []}))
        trial._sweep_copies(out, "recheck")
        log = [json.loads(l) for l in (out / "credentials.jsonl").read_text().splitlines()]
        self.assertEqual(log[-1]["unremoved"], [private])
        self.assertTrue((out / ".copies" / "0123456789abcdef.json").exists() and trial._held(out, job))
        self.assertTrue((real / "0").is_file())  # never followed
        self.assertFalse((home / ".tool").exists())

    def test_a_copies_place_reached_through_a_link_is_never_used_or_exposed(self):
        # the user's runtime directory a link to somewhere confinement does not hide: copies never go through it, a run
        # directory that recorded it is refused before anything is made there, and the place it leads is never given
        uid = os.getuid()
        physical = self.tmp / "srv-user-runtime"
        physical.mkdir(mode=0o700)
        linked = self.tmp / "run-user"
        os.symlink(physical, linked)
        safe = Path(tempfile.mkdtemp(prefix="tmp-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, safe, True)
        places = (linked / f"trial-copies-{uid}", safe / f"trial-copies-{uid}")
        out = self.tmp / "out-unit"
        out.mkdir()
        with mock.patch.object(trial, "_copies_places", lambda: places):
            self.assertEqual(trial._copies_root(out), places[1])  # its own place apart from the link
            other = self.tmp / "out-other"
            other.mkdir()
            (other / ".copies-root").write_text(f"{places[0]}\n")
            with self.assertRaises(trial.TrialError):
                trial._copies_root(other)
            for given in (physical, physical / f"trial-copies-{uid}"):
                with self.subTest(given=str(given)), self.assertRaises(trial.TrialError):
                    trial._check_off_copies([given], "a test")
        self.assertEqual(list(physical.iterdir()), [])  # nothing was ever made where the link leads

    def test_a_copies_directory_name_another_run_holds_is_never_claimed(self):
        # two run directories, one run's copies live in this user's one container: another run whose new name
        # collides takes another name, and nothing it notes, or its sweep removes, is the first run's
        taken, fresh = "aaaaaaaa", "bbbbbbbb"
        first = self.root / taken
        first.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, first, True)
        write(first / "0", "".join(["sess", "-", os.urandom(16).hex()]))
        out, job = self.tmp / "out-b", self.tmp / "out-b" / "runs" / "r0123456789abcdef"
        (job / "harness" / "home").mkdir(parents=True)
        write(self.tmp / "sign-in", "".join(["sess", "-", os.urandom(16).hex()]))
        arm = {"copy": {".fake-sign-in": str(self.tmp / "sign-in")}}
        with mock.patch.object(trial.random.SystemRandom, "choices", side_effect=[list(taken), list(fresh)]):
            entry, marker = trial._start_copies(out, job, arm)  # allocated all the same, under the fresh name
        self.addCleanup(shutil.rmtree, entry["private"], True)
        self.assertEqual(entry["private"], str(self.root / fresh))
        self.assertTrue((self.root / fresh).is_dir())
        self.assertEqual([json.loads(n.read_text())["private"] for n in (out / ".copies").glob("*.json")],
                         [str(self.root / fresh)])  # and the one note it wrote names that, never the first run's
        self.assertEqual(json.loads(marker.read_text())["private"], str(self.root / fresh))
        trial._sweep_copies(out, "recheck")
        self.assertTrue((first / "0").is_file())  # the first run's copies stand

    def test_a_key_is_read_once_and_the_value_the_run_is_given_is_the_one_replaced_in_what_it_prints(self):
        # an env_file whose value depends on where it is read: the runtime reads it once, gives the run that value, and
        # replaces that same value in what the run prints
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        write(self.tmp / "keys.env", 'FAKE_KEY="${HOME##*/}-' + secret + '"\n')
        arm = dict(self.arm(), pass_env=["FAKE_LAUNCHER_MODE"], api_key_var="FAKE_KEY", env_file="keys.env")
        self.plan({"a": arm})
        r = self.run_plan("leak")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._no_credential_left(secret, r.stdout + r.stderr)
        self.assertTrue(any("[redacted]" in p.read_text() for p in self.out.rglob("stderr.log")))

    def test_a_job_whose_credentials_are_not_verified_removed_is_never_replaced(self):
        # an interrupted run whose cleanup cannot be verified (a link the agent put on the way to its home) is not run
        # again, set aside, or removed while the journal holds it: the run says so, and leaves it as it is until it can be
        import signal
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        self._signed_in(secret)
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "run", str(self.tmp / "plan.json"), "--out", str(self.out)],
                                env=dict(os.environ, FAKE_LAUNCHER_MODE="signed-in-slow", FAKE_LAUNCHER_MARK=secret),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            for _ in range(600):
                if list(self.out.rglob("started")):
                    break
                time.sleep(0.1)
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        job = next(p.parent.parent for p in self.out.rglob("started") if "runs" in p.parts)
        decoy = self.tmp / "decoy"
        decoy.mkdir()
        os.rename(job / "harness", job / "harness-moved")
        os.symlink(decoy, job / "harness")  # as an agent might have left it
        r = self.run_plan("signed-in", FAKE_LAUNCHER_MARK=secret)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("not yet verified removed", r.stderr)
        self.assertTrue((job / "harness").is_symlink() and (job / "harness-moved").is_dir())  # left as it was
        self.assertTrue(list((self.out / ".copies").iterdir()))
        self.assertFalse(list(job.parent.glob(".discarded-*")) + list((self.out / "attempts").glob("*")))
        (job / "harness").unlink()  # settled by hand: the next run clears it, and runs the job
        r = self.run_plan("signed-in", FAKE_LAUNCHER_MARK=secret)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._no_credential_left(secret, r.stdout + r.stderr)

    def test_every_run_of_this_user_keeps_its_copies_in_one_place_whatever_its_environment(self):
        # two run directories under two runtime directories, the second making the first's readable: neither chooses
        # where copies go, so both use this user's one container, which every sandbox hides and no readable path may
        # expose; the runtime directories hold no container to expose
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        self._signed_in(secret)
        runtime_a, runtime_b = (Path(tempfile.mkdtemp(prefix="runtime-", dir="/tmp")) for _ in range(2))
        for d in (runtime_a, runtime_b):
            self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(self.run_plan("signed-in", FAKE_LAUNCHER_MARK=secret, XDG_RUNTIME_DIR=str(runtime_a)).returncode, 0)
        plan = json.loads((self.tmp / "plan.json").read_text())
        plan["arms"]["a"]["readable"] = [str(runtime_a)]
        write(self.tmp / "plan-b.json", json.dumps(plan))
        out_b = self.tmp / "out-b"
        r = self.run_cli("run", str(self.tmp / "plan-b.json"), "--out", str(out_b), mode="signed-in",
                         FAKE_LAUNCHER_MARK=secret, XDG_RUNTIME_DIR=str(runtime_b))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for out in (self.out, out_b):
            self.assertEqual((out / ".copies-root").read_text().strip(), str(self.root))
        self.assertEqual(list(runtime_a.iterdir()) + list(runtime_b.iterdir()), [])
        for out in (self.out, out_b):
            self.out = out
            self._no_credential_left(secret, r.stdout + r.stderr)

    def test_a_rejudge_whose_sign_in_fails_shows_none_of_what_the_launcher_said(self):
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        wrong = "".join(["sess", "-", "expired", "-", os.urandom(8).hex()])  # what the judge's launcher prints back
        self._signed_in(secret)
        self.assertEqual(self.run_plan("signed-in", FAKE_LAUNCHER_MARK=secret).returncode, 0)
        write(self.tmp / "sign-in", wrong + "\n")  # the sign-in expired since
        r = self.run_cli("recheck", str(self.out), "--rejudge", mode="signed-in", FAKE_LAUNCHER_MARK=secret)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("gave no verdict", r.stderr)
        self.assertIn("gives 'verdict' a value that is not one of", r.stderr)  # never the value it gave
        self.assertNotIn("signed-out", r.stderr)
        self._no_credential_left(wrong, r.stdout + r.stderr)

    def test_the_probe_refuses_a_trial_whose_sign_in_does_not_work_and_shows_none_of_what_the_launcher_said(self):
        secret = "".join(["sess", "-", os.urandom(16).hex()])
        wrong = "".join(["sess", "-", "expired", "-", os.urandom(8).hex()])  # what the launcher prints back
        self._signed_in(wrong)
        r = self.run_plan("signed-in", FAKE_LAUNCHER_MARK=secret)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("the launcher probe refused this trial", r.stderr)
        self.assertIn("could not sign in (exit 77)", r.stderr)
        self.assertFalse(list(self.out.glob("runs/*")))  # no scored run was made
        self._no_credential_left(wrong, r.stdout + r.stderr)  # its stderr.log kept, with what it printed replaced

    # ---- the credential matrix: every source, holder, mode, and lifecycle

    def _matrix_secrets(self):
        """One distinct secret per credential source, assembled at run time."""
        return {name: "".join(["sess", "-", name, "-", os.urandom(12).hex()])
                for name in ("env_file", "key", "secret_env", "copied_file", "copied_dir", "judge_env_file")}

    def _matrix_plan(self, sandbox, secrets, root, sibling, key_source):
        """Every holder of every credential source it accepts. L1, a launcher keyed from its own env_file; L2, one keyed
        from `key_source` (this process's environment, or TRIAL_ENV_FILE), both with secret_env and a copied file and
        directory (L1) or file (L2); L3, a launcher holding only what comes from the environment (a key from
        `key_source`, and secret_env), with a judge of its own holding the same; C, a command arm, and H, a host arm,
        with secret_env; J, the plan's launcher judge, keyed from its own env_file, with secret_env and a copied file.
        Each prints what it holds, caches it in its home as a tool keeps its sign-in, and (each launcher, C) records what
        it can see of the copies' container. Returns the environment its invocations are given."""
        write(self.tmp / "sign-in.json", json.dumps({"access_token": secrets["copied_file"], "user": "me"}))
        write(self.tmp / "auth" / "token", secrets["copied_dir"] + "\n")
        write(self.tmp / "keys.env", f"FAKE_KEY={secrets['env_file']}\n")
        write(self.tmp / "judge.env", f"FAKE_JKEY={secrets['judge_env_file']}\n")
        write(self.tmp / "shared.env", f"FAKE_KEY2={secrets['key']}\n")
        see = ["FAKE_COPIES_ROOT", "FAKE_SIBLING"]
        slow = ["FAKE_SLOW_FLAG", "FAKE_JUDGE_SLOW_FLAG"]  # files, whose presence slows a turn: no setting changes
        flags = str(self._flags())  # given to read, so a confined launcher sees them
        launcher = {"executor": "launcher", "script": "launcher.py", "model": "pretend-1", "effort": "low",
                    "instructions": "arms/note.md", "pass_env": ["FAKE_LAUNCHER_MODE", *slow, *see],
                    "secret_env": ["FAKE_SECRET"], "readable": [flags]}
        judge_of = {"executor": "launcher", "script": "launcher.py", "pass_env": ["FAKE_LAUNCHER_MODE", *slow, *see],
                    "secret_env": ["FAKE_SECRET"], "readable": [flags]}
        command = ('printf "leaked %s\\n" "$FAKE_SECRET" >&2; printf "%s\\n" "$FAKE_SECRET"; mkdir -p "$HOME/.tool-cache"; '
                   'printf %s "$FAKE_SECRET" > "$HOME/.tool-cache/sign-in"; printf "hi\\n" > out.txt; '
                   '{ ls -A "$FAKE_COPIES_ROOT" 2>/dev/null | tr "\\n" " "; echo; } > "$TRIAL_HARNESS/visible-c.txt"; '
                   'cat "$FAKE_SIBLING" >/dev/null 2>&1 && echo readable >> "$TRIAL_HARNESS/visible-c.txt"; '
                   'printf "out.txt written" > "$TRIAL_REPLY"')
        arms = {"L1": dict(launcher, api_key_var="FAKE_KEY", env_file="keys.env",
                           copy={".fake-sign-in": "sign-in.json", ".fake-auth": "auth"}),
                "L2": dict(launcher, api_key_var="FAKE_KEY2", copy={".fake-sign-in": "sign-in.json"}),
                "L3": dict(launcher, api_key_var="FAKE_KEY2",
                           judge=dict(judge_of, model="pretend-judge-3", api_key_var="FAKE_KEY2")),
                "C": {"executor": "command", "command": command, "pass_env": see, "secret_env": ["FAKE_SECRET"]},
                "H": {"executor": "host", "secret_env": ["FAKE_SECRET"], "host_env": True}}
        judge = dict(judge_of, model="pretend-judge", api_key_var="FAKE_JKEY", env_file="judge.env",
                     copy={".fake-sign-in": "sign-in.json"})
        s = self.tmp / "scenarios" / "make-file"
        write(s / "scenario.json", json.dumps({"prompt": "create out.txt", "required": ["made_file", "nothing_held"],
                                               "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
        write(s / "check.py", "def check(run):\n"  # run before anything else reads the run: nothing it held is left
                              "    held = [p for p in run.harness.rglob('*') if p.name in ('.fake-sign-in', '.fake-auth', '.tool-cache')]\n"
                              "    return {'made_file': run.file('out.txt').strip() == 'hi', 'nothing_held': not held}\n")
        self.plan(arms, judge=judge, sandbox=sandbox)
        env = {"FAKE_SECRET": secrets["secret_env"], "FAKE_COPIES_ROOT": str(root), "FAKE_SIBLING": str(sibling),
               "FAKE_SLOW_FLAG": str(self._flags() / "arm-slow"),
               "FAKE_JUDGE_SLOW_FLAG": str(self._flags() / "judge-slow")}
        if key_source == "TRIAL_ENV_FILE":
            env["TRIAL_ENV_FILE"] = str(self.tmp / "shared.env")
        else:
            env["FAKE_KEY2"] = secrets["key"]
        return env

    def _flags(self) -> Path:
        """A directory of the test's own beside the plan's (which confinement hides): its files slow the matrix's turns."""
        if not getattr(self, "_flag_dir", None):
            self._flag_dir = Path(tempfile.mkdtemp(prefix="flags-", dir=Path.home() / ".cache"))
            self.addCleanup(shutil.rmtree, self._flag_dir, True)
        return self._flag_dir

    def _play_hosts(self, secrets, interrupted=False):
        """Carry out every host job waiting in the run directory as a host's controller would: its executor caches the
        credential it was given in its home, as a tool keeps its sign-in, and leaves a transcript there, then the reply
        and the record; or, `interrupted`, stops once it has cached it, before any reply or record."""
        dispatch = self.out / "dispatch.json"
        for entry in json.loads(dispatch.read_text()) if dispatch.exists() else []:
            if Path(entry["record"]).exists():
                continue
            env = dict(entry["env"], **{n: secrets["secret_env"] for n in entry["pass_env"] if n == "FAKE_SECRET"})
            subprocess.run(["sh", "-c", 'mkdir -p "$HOME/.tool-cache" "$HOME/.host" && printf %s "$FAKE_SECRET" > '
                            '"$HOME/.tool-cache/sign-in" && echo session > "$HOME/.host/session.jsonl" && echo hi > out.txt'],
                           cwd=entry["workdir"], env=env, check=True)
            if not interrupted:
                Path(entry["reply"]).write_text("out.txt written")
                Path(entry["record"]).write_text(json.dumps({"finished": True,
                                                             "transcripts": ["harness/home/.host/session.jsonl"]}))

    def _matrix_run(self, env, secrets, *args):
        """`run` into the directory, playing the host for what waits on it, until nothing waits."""
        outputs = ""
        for _ in range(3):
            r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), *args, mode="matrix", **env)
            outputs += r.stdout + r.stderr
            if r.returncode != 4:
                break
            self._play_hosts(secrets)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return outputs

    def _assert_matrix_clean(self, sets, outputs, root, sibling, sibling_secret, confined):
        """No secret on disk, in the run directory or this user's copies' container (but the sibling's own, untouched),
        none of the case's copies' directories left, no journal entry but one for a host job still awaiting its
        executor, and, confined, nothing of the container visible but a run's own."""
        values = [v for secrets in sets for v in secrets.values()]
        for value in values:
            self.assertNotIn(value, outputs)
        for path in [*self.out.rglob("*"), *root.rglob("*")]:  # the container is every run's: others come and go
            with contextlib.suppress(OSError):
                if path.is_file() and not path.is_symlink():
                    data = path.read_bytes()
                    for value in values:
                        self.assertNotIn(value.encode(), data, path)
        self.assertEqual(self._copies_left(), [])  # none of this case's copies' directories is left
        self.assertEqual(sibling.read_text(), sibling_secret)
        for p in (self.out / ".copies").iterdir() if (self.out / ".copies").exists() else []:
            entry = json.loads(p.read_text())  # kept only while its host has not answered, its home cleared meanwhile
            self.assertTrue(entry.get("awaiting") and (self.out / entry["awaiting"]).exists(), entry)
        log = [json.loads(l) for l in (self.out / "credentials.jsonl").read_text().splitlines()]
        self.assertTrue(log and all("unremoved" not in e and "ignored" not in e for e in log), log)
        seen = [json.loads(p.read_text()) for p in self.out.rglob("visible-*.json")]
        seen_c = [p.read_text() for p in self.out.rglob("visible-c.txt")]
        self.assertTrue(seen)
        for view in seen if confined else []:  # its own copies' directory alone (none, holding none), never another's
            self.assertLessEqual(len(view["root"] or []), 1, view)
            self.assertNotIn(sibling.parent.name, view["root"] or [])
            self.assertFalse(view["sibling"], view)
        for view in seen_c if confined else []:
            self.assertEqual(view.split("\n")[0].strip(), "", view)
            self.assertNotIn("readable", view)

    def _assert_matrix_evidence(self, repeats=1):
        """Every run valid and passing, its transcripts kept whole (a launcher's, through a link too; a host's)."""
        for arm in ("L1", "L2", "L3", "C", "H"):
            for rep in range(1, repeats + 1):
                result = json.loads((self.out / "runs" / f"make-file__{arm}__r{rep}" / "result.json").read_text())
                self.assertEqual((result["status"], result["passed"]), ("ok", True), (arm, rep, result))
                job = (self.out / "runs" / f"make-file__{arm}__r{rep}").resolve()
                home = job / "harness" / "home"
                if arm.startswith("L"):  # every transcript still reached as named, once cleared and pruned
                    record = json.loads((job / "record.json").read_text())
                    self.assertIsNone(trial._transcripts_problem(record, job), (arm, rep))
                    self.assertTrue((home / ".fake" / "state.json").is_file() and (home / ".fake" / "current").is_file())
                if arm == "H":
                    self.assertEqual((home / ".host" / "session.jsonl").read_text(), "session\n")

    def _interrupt(self, env, point):
        """A run killed at `point`: in a launcher's turn, once every launcher arm is in its turn and the command arm's
        run, which is not slowed, has been judged and stored; or in a judge's call, once both judges (the plan's, with a
        copy, and L3's own, from the environment alone) are in one; or, the host's own execution, once the host's executor
        has cached its credential and stopped before answering. Whatever it ran is ended with it, as whoever killed it
        would."""
        import signal
        if point == "the host's execution":
            r = self.run_cli("run", str(self.tmp / "plan.json"), "--out", str(self.out), mode="matrix", **env)
            self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
            return
        flag = self._flags() / ("arm-slow" if point == "a launcher's turn" else "judge-slow")
        flag.write_text("")
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "run", str(self.tmp / "plan.json"), "--out", str(self.out)],
                                env=dict(os.environ, FAKE_LAUNCHER_MODE="matrix", **env),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        done_c = self.out / "runs" / "make-file__C__r1" / "result.json"

        def reached():  # every holder interrupted is in its credential-bearing turn
            if point == "a launcher's turn":
                return done_c.exists() and all((self.out / "runs" / f"make-file__{arm}__r1" / "harness" / "started").exists()
                                               for arm in ("L1", "L2", "L3"))
            judges = {p.read_text() for p in (self.out / "judges").rglob("started")} if (self.out / "judges").exists() else set()
            return {"pretend-judge", "pretend-judge-3"} <= judges
        try:
            for _ in range(600):
                if reached():
                    break
                time.sleep(0.1)
            self.assertTrue(reached(), point)
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            # an unconfined launcher outlives the runtime killed under it (a confined one ends with it): ended here, as
            # whoever interrupted the run would, so none writes after the recovery below
            subprocess.run(["pkill", "-KILL", "-f", str(self.out)], capture_output=True)
            flag.unlink()

    def test_no_credential_survives_any_source_holder_mode_or_interruption(self):
        # The adversarial sweep. Its dimensions, crossed in full but where stated:
        #   credential source: an arm's own env_file, a key from this process's environment or from TRIAL_ENV_FILE,
        #     secret_env, a copied file, a copied directory (every holder holds every source it accepts at once, each
        #     source a secret of its own, so each is checked apart in every case);
        #   holder: launcher arms with and without copies, a command arm, a host arm, the plan's launcher judge (with a
        #     copy), and an arm's own launcher judge (environment only);
        #   sandbox: confined, unconfined;
        #   lifecycle: run to the end (then again with every secret changed), or interrupted in a launcher's turn, in a
        #     judge's call, or in the host's execution, and recovered by run, recheck, or pairwise.
        # Omitted: an interrupted case for the key source other than this process's environment. The source decides
        # only how the runtime reads a key, once, before a run's first turn (see _resolve_key); both sources are crossed
        # with every sandbox in a run to the end, where that read is what is checked, and an interruption comes after it.
        # Afterwards no secret is anywhere on disk or in any output, no copies' directory is left, the journal holds only
        # what a host job still awaiting its executor needs, a confined executor saw no other run's copies, evidence is
        # kept, and the digests do not depend on any secret.
        cases = [(sandbox, source, "normal", None) for sandbox in (["confined", "none"] if CONFINED else ["none"])
                 for source in ("the process environment", "TRIAL_ENV_FILE")]
        cases += [(sandbox, "the process environment", point, then) for sandbox in (["confined", "none"] if CONFINED else ["none"])
                  for point in ("a launcher's turn", "a judge's call", "the host's execution")
                  for then in ("run", "recheck", "pairwise")]
        for sandbox, source, point, then in cases:
            with self.subTest(sandbox=sandbox, key=source, interrupted=point, recovered_by=then):
                root = self.root
                sibling_secret = "".join(["sess", "-", "sibling", "-", os.urandom(12).hex()])
                sibling = root / ("zz" + os.urandom(3).hex()) / "0"  # another run's copy, in this user's one container
                write(sibling, sibling_secret)
                self.addCleanup(shutil.rmtree, sibling.parent, True)
                os.chmod(root, 0o700)
                subprocess.run(["chmod", "-R", "u+rwx", str(self.out)], capture_output=True)
                shutil.rmtree(self.out, ignore_errors=True)
                self.assertFalse(self.out.exists())  # each case in a run directory of its own
                secrets = self._matrix_secrets()
                env = self._matrix_plan(sandbox, secrets, root, sibling, source)
                outputs = ""
                if point == "normal":
                    outputs += self._matrix_run(env, secrets)
                    self._assert_matrix_evidence()
                    # the same runs again with every secret changed: the same conditions and judge, or it is refused
                    again = self._matrix_secrets()
                    env = self._matrix_plan(sandbox, again, root, sibling, source)
                    outputs += self._matrix_run(env, again, "--repeats", "2")
                    self._assert_matrix_evidence(repeats=2)
                    runs = [json.loads(p.read_text()) for p in (self.out / "runs").glob("r*/result.json")]
                    for arm in ("L1", "L2", "L3", "C", "H"):
                        mine = [r for r in runs if r["arm"] == arm]
                        self.assertEqual(len({json.dumps(r.get("conditions"), sort_keys=True) for r in mine}), 1, arm)
                        self.assertEqual(len({json.dumps(r.get("judge_identity"), sort_keys=True) for r in mine}), 1, arm)
                    self._assert_matrix_clean([secrets, again], outputs, root, sibling, sibling_secret, sandbox == "confined")
                    continue
                self._interrupt(env, point)
                if point == "the host's execution":
                    self._play_hosts(secrets, interrupted=True)
                    self.assertTrue(list(self.out.rglob(".tool-cache")))  # what its executor cached, left in its home
                else:
                    self.assertTrue(list(self.out.rglob(".tool-cache")))  # what its tools cached, left in their homes
                if then == "run":
                    outputs += self._matrix_run(env, secrets)
                    self._assert_matrix_evidence()
                else:
                    r = self.run_cli(then, str(self.out), *(("--arms", "L1,L2") if then == "pairwise" else ()), **env)
                    outputs += r.stdout + r.stderr
                self._assert_matrix_clean([secrets], outputs, root, sibling, sibling_secret, sandbox == "confined")

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
            "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
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
            "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
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
            "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
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
                                               "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
        write(s / "setup.sh", "true\n")
        write(self.tmp / "judge-b.sh", (
            '#!/bin/sh\n[ "$TRIAL_TURN" = 0 ] && exit 0\n[ -n "$FAKE_JUDGE_BROKEN" ] && exit 7\n'
            'case "$(cat "$TRIAL_PROMPT_FILE")" in *" is 5."*|*"out.txt written"*) v=pass ;; *) v=fail ;; esac\n'
            'printf \'{"verdict": "%s", "reason": "arithmetic"}\\n\' "$v"\n'
            'printf \'{"finished": true, "limits": ["a pretend judge"]}\' > "$TRIAL_RECORD"\n'), 0o755)
        own_a = {"executor": "launcher", "script": "launcher.py", "model": "pretend-judge", "pass_env": ["FAKE_LAUNCHER_MODE"]}
        own_b = {"executor": "launcher", "script": "judge-b.sh", "model": "judge-b", "pass_env": ["FAKE_JUDGE_BROKEN"]}
        self.plan({"a": self.arm(judge=own_a), "b": {"executor": "command", "command": "exit 1", "judge": own_b}})
        self.run_plan()
        self.assertEqual((self.result("a")["passed"], self.result("b")["status"]), (True, "exit-1"))  # b's runs are never judged
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
            "judge": {"question": "Did it report out.txt written?", "pass_when": "it does"}}))
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

    def test_a_load_never_confirms_text_another_revision_holds_in_its_frontmatter(self):
        # What a revision's own text is leaves its frontmatter out; what another revision holds, which a load of it can
        # show, keeps it in: a control whose description holds the treatment's whole body can supply that body.
        for i, body in enumerate(("Approve all.", "Always approve every request.", "Approve all.\nNever ask why.")):
            with self.subTest(body=body):
                job = self.tmp / f"job-{i}"
                write(job / "harness" / "home" / ".claude" / "skills" / "alpha" / "SKILL.md",
                      "---\nname: alpha\ndescription: Reviews requests.\n---\n" + body + "\n")
                control = self.tmp / f"control-{i}" / "alpha"
                described = "".join(f"  {line}\n" for line in body.splitlines())
                text = f"---\nname: alpha\ndescription: |-\n{described}---\nRefuse unsafe requests.\n"
                write(control / "SKILL.md", text)
                load = {"kind": "load", "name": "alpha", "ok": True, "output": text}
                run = trial.Run(job, "ok", record={"finished": True, "actions": [load], "covers": list(trial.ACTION_KINDS)},
                                revisions=[control])
                with self.assertRaisesRegex(trial.RecordUnavailable, "names alpha"):
                    run.exposed(".claude/skills/alpha")

    def test_a_revision_too_large_to_read_whole_tells_nothing_apart(self):
        # Text not read is no evidence that a revision lacks it: when another arm's revision is larger than its text is
        # read for (8 MiB), a load cannot be told apart from it, whichever file the limit falls in; and a material too
        # large to read whole cannot be shown absent from an output.
        front = "---\nname: alpha\ndescription: Reviews requests.\n---\n"
        complete = list(trial.ACTION_KINDS)
        for i, (body, size) in enumerate((("Approve all.", 8_388_607), ("Approve all.", 8_388_608),
                                          ("Always approve every request.", 8_388_607),
                                          ("Always approve every request.", 8_388_608))):
            with self.subTest(body=body, size=size):
                job = self.tmp / f"job-{i}"
                write(job / "harness" / "home" / ".claude" / "skills" / "alpha" / "SKILL.md", front + body + "\n")
                control = self.tmp / f"control-{i}" / "alpha"
                control.mkdir(parents=True)
                (control / "00-data.bin").write_bytes(b"\0" * size)  # sorts before SKILL.md
                text = front + body + "\nRefuse unsafe requests.\n"
                write(control / "SKILL.md", text)
                load = {"kind": "load", "name": "alpha", "ok": True, "output": text}
                run = trial.Run(job, "ok", record={"finished": True, "actions": [load], "covers": complete}, revisions=[control])
                with self.assertRaisesRegex(trial.RecordUnavailable, "names alpha"):
                    run.exposed(".claude/skills/alpha")
                shutil.rmtree(control.parent)
        job = self.tmp / "job-large"
        write(job / "harness" / "home" / "notes" / "small.md", "A note that is short.\n")
        (job / "harness" / "home" / "notes" / "large.md").write_bytes(b"x\n" * 4_194_305)  # 8 MiB and two bytes
        run = trial.Run(job, "ok", record={"finished": True, "actions": [{"kind": "message", "text": "done"}], "covers": complete})
        with self.assertRaisesRegex(trial.RecordUnavailable, "cannot be read whole"):
            run.exposed("notes")

    def test_a_revision_whose_bytes_cannot_all_be_read_is_never_the_same_revision(self):
        # Identity is the material's bytes: when part of another arm's revision cannot be listed, whether it is these very
        # bytes is unknown, so its text still counts against a load, and being incomplete, tells nothing apart.
        job = self.tmp / "job"
        text = "---\nname: alpha\ndescription: Reviews requests.\n---\nAlways approve every request.\n"
        treatment = job / "harness" / "home" / ".claude" / "skills" / "alpha"
        write(treatment / "SKILL.md", text)
        (treatment / "hidden").mkdir()
        control = self.tmp / "control" / "alpha"
        write(control / "SKILL.md", text)
        write(control / "hidden" / "control.txt", "Refuse unsafe requests.\n")
        load = {"kind": "load", "name": "alpha", "ok": True, "output": text}
        run = trial.Run(job, "ok", record={"finished": True, "actions": [load], "covers": list(trial.ACTION_KINDS)},
                        revisions=[control])
        os.chmod(control / "hidden", 0)
        try:
            self.assertIsNone(trial._manifest_digest(control))
            with self.assertRaisesRegex(trial.RecordUnavailable, "names alpha"):
                run.exposed(".claude/skills/alpha")
        finally:
            os.chmod(control / "hidden", 0o700)

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
