from __future__ import annotations

import json
import tempfile
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "duplication_check.sh"
FIXTURES = ROOT / "tests" / "fixtures" / "duplication"


def run_duplication_json(fixture_name: str, *args: str) -> dict:
    cmd = [
        "sh",
        str(SCRIPT),
        str(FIXTURES / fixture_name),
        "--format",
        "json",
        *args,
    ]
    output = subprocess.check_output(cmd, text=True)
    return json.loads(output)


class DuplicationCheckTests(unittest.TestCase):
    def test_reports_blocker_for_operative_contradiction(self):
        data = run_duplication_json("tiered", "--scope", "all", "--max-hops", "2")

        self.assertEqual(data["summary"]["highest_operative_severity"], "BLOCKER")
        self.assertEqual(data["gate"]["status"], "FAIL")
        self.assertGreaterEqual(data["summary"]["contradiction_findings"], 1)
        self.assertEqual(data["confidence"], "HIGH [H]")

        advisory_findings = [
            finding
            for finding in (data["directive_duplicates"] + data["block_duplicates"] + data["contradiction_candidates"])
            if finding["scope"] == "advisory"
        ]
        self.assertTrue(advisory_findings)

    def test_operative_scope_excludes_advisory_findings(self):
        data = run_duplication_json("tiered", "--scope", "operative", "--max-hops", "2")

        self.assertEqual(data["summary"]["advisory_docs_scanned"], 0)
        findings = data["directive_duplicates"] + data["block_duplicates"] + data["contradiction_candidates"]
        self.assertTrue(findings)
        self.assertTrue(all(finding["scope"] == "operative" for finding in findings))

    def test_max_hops_promotes_reachable_markdown_to_operative(self):
        hop1 = run_duplication_json("hop-sensitive", "--scope", "operative", "--max-hops", "1")
        hop2 = run_duplication_json("hop-sensitive", "--scope", "operative", "--max-hops", "2")

        self.assertEqual(hop1["summary"]["directive_findings"], 0)
        self.assertEqual(hop1["summary"]["highest_operative_severity"], "NONE")

        self.assertGreaterEqual(hop2["summary"]["directive_findings"], 1)
        self.assertEqual(hop2["summary"]["highest_operative_severity"], "MINOR")
        self.assertEqual(hop2["summary"]["operative_docs_scanned"], 3)

    def test_excludes_test_markdown_from_scan_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nYou SHALL keep one source of truth.\n",
                encoding="utf-8",
            )
            fixture_dir = skill_dir / "tests" / "fixtures" / "duplication"
            fixture_dir.mkdir(parents=True)
            (fixture_dir / "notes.md").write_text(
                "# Fixture\n\nYou SHALL keep one source of truth.\n",
                encoding="utf-8",
            )

            output = subprocess.check_output(
                ["sh", str(SCRIPT), str(skill_dir), "--format", "json", "--scope", "all"],
                text=True,
            )

        data = json.loads(output)
        self.assertEqual(data["summary"]["total_markdown_docs"], 1)
        self.assertEqual(data["summary"]["directive_findings"], 0)
        self.assertEqual(data["summary"]["block_findings"], 0)
        self.assertEqual(data["summary"]["contradiction_findings"], 0)


if __name__ == "__main__":
    unittest.main()
