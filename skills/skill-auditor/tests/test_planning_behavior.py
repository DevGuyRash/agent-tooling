from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_MD = ROOT / "SKILL.md"
FIXTURES = ROOT / "tests" / "fixtures"


def load_json(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    cleaned = text.lower().replace("`", "")
    return re.sub(r"\s+", " ", cleaned).strip()


class PlanningBehaviorTests(unittest.TestCase):
    def test_question_router_maps_fixture_cases(self) -> None:
        content = SKILL_MD.read_text(encoding="utf-8")
        mappings = dict(
            re.findall(
                r"^- ([A-Za-z ]+) → `([^`]+)`$",
                content,
                flags=re.MULTILINE,
            )
        )

        for case in load_json("planning_cases.json"):
            with self.subTest(case=case["question"]):
                self.assertEqual(mappings[case["question"]], case["reference"])
                reference_text = (ROOT / case["reference"].replace("<skills-file-root>/", "")).read_text(
                    encoding="utf-8"
                ).lower()
                for term in case["terms"]:
                    self.assertIn(term.lower(), reference_text)

    def test_profile_rules_cover_fixture_profiles(self) -> None:
        profile_rules = normalize((ROOT / "references" / "profile-rules.md").read_text(encoding="utf-8"))

        for case in load_json("profile_cases.json"):
            with self.subTest(profile=case["profile"]):
                self.assertIn(case["profile"], profile_rules)
                self.assertIn(normalize(case["cue"]), profile_rules)

    def test_start_here_work_order_stays_short_and_ordered(self) -> None:
        normalized = normalize(SKILL_MD.read_text(encoding="utf-8"))
        positions = []

        for step in load_json("work_order_steps.json"):
            index = normalized.find(normalize(step))
            self.assertNotEqual(index, -1, step)
            positions.append(index)

        self.assertEqual(sorted(positions), positions)
        self.assertLessEqual(len(SKILL_MD.read_text(encoding="utf-8").splitlines()), 120)

    def test_active_skill_drops_router_cli_and_domain_taxonomy(self) -> None:
        content = SKILL_MD.read_text(encoding="utf-8")

        self.assertNotIn("audit-skill", content)
        self.assertNotIn("25 domains", content.lower())
        self.assertIsNone(re.search(r"\bD\d+\b", content))


if __name__ == "__main__":
    unittest.main()
