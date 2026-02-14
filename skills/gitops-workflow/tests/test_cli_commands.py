from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "repo-governance.py"

spec = importlib.util.spec_from_file_location("repo_governance", MODULE_PATH)
repo_governance = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = repo_governance
assert spec.loader is not None
spec.loader.exec_module(repo_governance)


class CliCommandTests(unittest.TestCase):
    def setUp(self):
        self.valid_policy = json.loads((ROOT / "tests" / "fixtures" / "policy" / "policy_valid.json").read_text())

    def _write_policy(self, payload):
        temp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with temp:
            temp.write(json.dumps(payload))
        return temp.name

    def test_validate_returns_zero_for_valid_policy(self):
        path = self._write_policy(self.valid_policy)
        code = repo_governance.main(["validate", "--policy", path])
        self.assertEqual(code, 0)

    def test_validate_returns_two_for_invalid_policy(self):
        invalid = dict(self.valid_policy)
        invalid["unknownKey"] = True
        path = self._write_policy(invalid)
        code = repo_governance.main(["validate", "--policy", path])
        self.assertEqual(code, repo_governance.EXIT_INVALID_POLICY)

    def test_plan_returns_three_on_drift(self):
        path = self._write_policy(self.valid_policy)
        with mock.patch.object(
            repo_governance.GovernanceManager,
            "plan",
            return_value={"repo": "acme/widget", "hasDrift": True, "drift": [{"resourceType": "label", "resourceId": "bug", "action": "update", "before": {}, "after": {}, "status": "pending"}]},
        ):
            code = repo_governance.main(["plan", "--policy", path])
        self.assertEqual(code, repo_governance.EXIT_DRIFT)

    def test_plan_returns_zero_when_clean(self):
        path = self._write_policy(self.valid_policy)
        with mock.patch.object(
            repo_governance.GovernanceManager,
            "plan",
            return_value={"repo": "acme/widget", "hasDrift": False, "drift": []},
        ):
            code = repo_governance.main(["plan", "--policy", path])
        self.assertEqual(code, 0)

    def test_apply_returns_four_on_apply_failure(self):
        path = self._write_policy(self.valid_policy)
        with mock.patch.object(
            repo_governance.GovernanceManager,
            "apply",
            side_effect=repo_governance.GovernanceError("partial failure", repo_governance.EXIT_APPLY_FAILED),
        ):
            code = repo_governance.main(["apply", "--policy", path, "--write-codeowners"])
        self.assertEqual(code, repo_governance.EXIT_APPLY_FAILED)

    def test_audit_json_returns_three_on_drift(self):
        path = self._write_policy(self.valid_policy)
        with mock.patch.object(
            repo_governance.GovernanceManager,
            "audit",
            return_value={"repo": "acme/widget", "hasDrift": True, "drift": [{"resourceType": "ruleset", "resourceId": "default", "action": "create", "before": None, "after": {}, "status": "pending"}]},
        ):
            code = repo_governance.main(["audit", "--policy", path, "--format", "json"])
        self.assertEqual(code, repo_governance.EXIT_DRIFT)


if __name__ == "__main__":
    unittest.main()
