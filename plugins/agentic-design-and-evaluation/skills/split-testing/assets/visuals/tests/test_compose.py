"""The reader-first trial composition and the trial views it composes, checked
against the built bundle in node:vm (see compose.cjs)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from visual_harness import VISUALS, NodeCases


class ComposeTest(NodeCases):
    """Section order and shape, case variants, the verdict's rule and counts,
    failure causes, checks by case, invalid reasons and escaping."""

    script = "compose.cjs"
    minimum = 30

    def test_composition_follows_the_trial(self) -> None:
        self.run_script_cases()



def load_trial():
    """The split-testing runtime, trial.py, imported without writing bytecode beside it."""
    spec = importlib.util.spec_from_file_location("trial_runtime", VISUALS.parent.parent / "scripts" / "trial.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    kept, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = kept
    return module


class RetryDirectoryTest(unittest.TestCase):
    """The invalid-run remedies (compose.cjs) send a retry with the plan unchanged into the same run directory, and a
    repair that changes an arm or a scenario into a new one, because trial.py refuses that repair there. Checked with
    trial.py's own _merge_stored_plan on a directory holding one invalid launcher run."""

    def test_a_repair_is_refused_in_the_same_directory_and_an_unchanged_retry_is_not(self) -> None:
        trial = load_trial()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenario_dir = root / "scenarios" / "c"
            scenario_dir.mkdir(parents=True)
            scenario = {"prompt": "Reply.", "followups": ["continue"], "timeout_s": 60, "required": []}
            (scenario_dir / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
            spec = dict(scenario, name="c", dir=str(scenario_dir))
            arm = {"executor": "launcher", "script_sha256": "a" * 64, "watch": ["~/.config/tool.toml"]}
            out = root / "out"
            (out / "runs" / "c__a__r1").mkdir(parents=True)
            (out / "plan.json").write_text(json.dumps({"arms": {"a": arm}, "scenarios": [spec]}), encoding="utf-8")
            run = {"job": "c__a__r1", "arm": "a", "scenario": "c", "repeat": 1, "status": "config-changed", "passed": None,
                   "identity": trial._identity(arm), "conditions": trial._conditions(arm, trial._effective_sandbox({}, spec))}
            (out / "runs" / "c__a__r1" / "result.json").write_text(json.dumps(run), encoding="utf-8")
            plan = lambda arm_now, spec_now: {"arms": {"a": arm_now}, "scenarios": [spec_now]}  # noqa: E731
            self.assertIsInstance(trial._merge_stored_plan(out, plan(dict(arm), dict(spec))), dict, "a retry with the plan unchanged is accepted")
            refused = "restore them or use a new --out"
            # config-changed and setup-watch-unreadable: the arm's watch list; session-changed, no-record, record-invalid
            # and setup-exit-N: the launcher (its script).
            for what, arm_now in {"watch": dict(arm, watch=[]), "launcher": dict(arm, script_sha256="b" * 64)}.items():
                with self.subTest(repair=what), self.assertRaisesRegex(trial.TrialError, refused):
                    trial._merge_stored_plan(out, plan(arm_now, dict(spec)))
            # timeout and setup-timeout: the scenario's timeout_s.
            (scenario_dir / "scenario.json").write_text(json.dumps(dict(scenario, timeout_s=600)), encoding="utf-8")
            with self.subTest(repair="timeout_s"), self.assertRaisesRegex(trial.TrialError, refused):
                trial._merge_stored_plan(out, plan(dict(arm), dict(spec, timeout_s=600)))
            (scenario_dir / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
            # setup-failed: the scenario's setup.sh.
            (scenario_dir / "setup.sh").write_text("git init -q\n", encoding="utf-8")
            with self.subTest(repair="setup.sh"), self.assertRaisesRegex(trial.TrialError, refused):
                trial._merge_stored_plan(out, plan(dict(arm), dict(spec)))


if __name__ == "__main__":
    unittest.main()
