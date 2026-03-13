from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPENAI_YAML = ROOT / "agents" / "openai.yaml"


def read_interface_value(key: str) -> str:
    content = OPENAI_YAML.read_text(encoding="utf-8")
    match = re.search(rf"^\s{{2}}{re.escape(key)}:\s*\"([^\"]+)\"$", content, flags=re.MULTILINE)
    if match is None:
        raise AssertionError(f"missing interface key: {key}")
    return match.group(1)


class OpenAiYamlTests(unittest.TestCase):
    def test_openai_yaml_exists_with_expected_interface_values(self) -> None:
        self.assertTrue(OPENAI_YAML.exists())
        self.assertEqual(read_interface_value("display_name"), "Skill Auditor")
        self.assertEqual(
            read_interface_value("short_description"),
            "Audit and improve a skill's packaging, triggers, workflow, and verification loop",
        )
        self.assertEqual(
            read_interface_value("default_prompt"),
            "Use $skill-auditor to audit a skill's packaging, trigger behavior, task leverage, context design, and verification loop, then produce a concise Skill Improvement Brief with concrete changes and checks.",
        )

    def test_openai_yaml_uses_interface_root_only(self) -> None:
        content = OPENAI_YAML.read_text(encoding="utf-8")

        self.assertTrue(content.startswith("interface:\n"))
        self.assertNotIn("metadata:", content)


if __name__ == "__main__":
    unittest.main()
