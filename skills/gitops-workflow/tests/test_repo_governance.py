from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "repo-governance.py"

spec = importlib.util.spec_from_file_location("repo_governance", MODULE_PATH)
repo_governance = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = repo_governance
assert spec.loader is not None
spec.loader.exec_module(repo_governance)


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    def api_json(self, path: str, method: str = "GET", payload=None):
        key = (method.upper(), path)
        if key not in self.responses:
            raise repo_governance.GovernanceError(f"Missing fixture for {key}", repo_governance.EXIT_APPLY_FAILED)
        return deepcopy(self.responses[key])


class GovernanceUnitTests(unittest.TestCase):
    def setUp(self):
        self.policy_fixture = json.loads((ROOT / "tests" / "fixtures" / "policy" / "policy_valid.json").read_text())
        self.labels_fixture = json.loads((ROOT / "tests" / "fixtures" / "github_api" / "labels_page1.json").read_text())
        self.rulesets_fixture = json.loads((ROOT / "tests" / "fixtures" / "github_api" / "rulesets_list.json").read_text())
        self.golden = json.loads((ROOT / "tests" / "golden" / "plan_drift.json").read_text())

    def _manager(self):
        responses = {
            ("GET", "repos/acme/widget/labels?per_page=100&page=1"): self.labels_fixture,
            ("GET", "repos/acme/widget/rulesets"): self.rulesets_fixture,
        }
        return repo_governance.GovernanceManager(client=FakeClient(responses))

    def test_validate_policy_rejects_unknown_keys(self):
        invalid = json.loads((ROOT / "tests" / "fixtures" / "policy" / "policy_invalid_unknown_key.json").read_text())
        with self.assertRaises(repo_governance.GovernanceError) as ctx:
            repo_governance.validate_policy(invalid)
        self.assertEqual(ctx.exception.exit_code, repo_governance.EXIT_INVALID_POLICY)
        self.assertIn("Unknown policy keys", str(ctx.exception))

    def test_desired_ruleset_includes_sorted_required_checks(self):
        policy = repo_governance.validate_policy(self.policy_fixture)
        desired = repo_governance.desired_rulesets_from_policy(policy)
        managed = [r for r in desired if r["name"] == "default-branch-protection"][0]
        required_rule = [r for r in managed["rules"] if r["type"] == "required_status_checks"][0]
        contexts = [item["context"] for item in required_rule["parameters"]["required_status_checks"]]
        self.assertEqual(contexts, ["a-check", "z-check"])

    def test_plan_drift_matches_golden_fixture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codeowners_path = Path(temp_dir) / "CODEOWNERS"
            codeowners_path.write_text(
                "# Managed by skills/gitops-workflow/scripts/repo-governance.py\n\n* @acme/maintainers\n",
                encoding="utf-8",
            )
            policy = deepcopy(self.policy_fixture)
            policy["codeowners"]["path"] = str(codeowners_path)
            validated = repo_governance.validate_policy(policy)
            report = self._manager().plan(validated)

        self.assertEqual(report, self.golden)

    def test_plan_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codeowners_path = Path(temp_dir) / "CODEOWNERS"
            codeowners_path.write_text(
                "# Managed by skills/gitops-workflow/scripts/repo-governance.py\n\n* @acme/maintainers\n",
                encoding="utf-8",
            )
            policy = deepcopy(self.policy_fixture)
            policy["codeowners"]["path"] = str(codeowners_path)
            validated = repo_governance.validate_policy(policy)
            manager = self._manager()
            first = manager.plan(validated)
            second = manager.plan(validated)

        self.assertEqual(first, second)

    def test_github_client_maps_permission_error_to_exit_five(self):
        def failing_runner(_cmd, input_text=None):
            raise subprocess.CalledProcessError(
                1,
                ["gh", "api"],
                output="",
                stderr="Resource not accessible by integration",
            )

        client = repo_governance.GitHubClient(runner=failing_runner)
        with self.assertRaises(repo_governance.GovernanceError) as ctx:
            client.api_json("repos/acme/widget/rulesets")
        self.assertEqual(ctx.exception.exit_code, repo_governance.EXIT_PERMISSIONS)


if __name__ == "__main__":
    unittest.main()
