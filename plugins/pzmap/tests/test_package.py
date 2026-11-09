"""Package checks, not live-site or agent-behavior tests."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
SKILL = PLUGIN / "skills" / "pzmap"
CONVERTER = REPO / "scripts" / "plugin_port.py"


def payload_contract(path: Path):
    """Compare YAML values and instruction text, not YAML line wrapping."""
    if path.name == "SKILL.md":
        _, metadata, body = path.read_text(encoding="utf-8").split("---", 2)
        return yaml.safe_load(metadata), body.strip("\n")
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return path.read_bytes()


class PackageTests(unittest.TestCase):
    def test_manifests_agree(self):
        codex = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
        claude = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        for key in ("name", "version", "description", "author", "license"):
            self.assertEqual(codex[key], claude[key], key)
        self.assertEqual(codex["name"], PLUGIN.name)
        self.assertRegex(codex["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue((PLUGIN / codex["skills"]).is_dir())

    def test_skill_frontmatter_and_display_names(self):
        text = (SKILL / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        metadata = yaml.safe_load(text.split("---", 2)[1])
        self.assertEqual(metadata["name"], SKILL.name)
        self.assertTrue(0 < len(metadata["description"]) <= 1024)
        self.assertIsInstance(metadata["compatibility"], str)
        display = yaml.safe_load((SKILL / "agents/openai.yaml").read_text())
        heading = re.search(r"(?m)^# ([^\n]+)$", text).group(1)
        self.assertEqual(display["interface"]["display_name"], heading)
        codex = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(codex["interface"]["displayName"], heading)

    def test_relative_links_stay_within_package_and_resolve(self):
        for path in PLUGIN.rglob("*.md"):
            text = path.read_text()
            for target in re.findall(r"\]\(([^)\s]+)\)", text):
                if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                    continue
                resolved = (path.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(resolved.is_relative_to(PLUGIN.resolve()), (path, target))
                self.assertTrue(resolved.exists(), (path, target))

    def test_text_files_are_utf8_lf_without_generated_junk(self):
        for path in PLUGIN.rglob("*"):
            self.assertNotIn(path.name, {"__pycache__", ".DS_Store"})
            if path.is_file():
                data = path.read_bytes()
                data.decode("utf-8")
                self.assertNotIn(b"\r", data, str(path))
                self.assertTrue(data.endswith(b"\n"), str(path))

    def test_no_undeclared_executable_surfaces(self):
        for manifest_path in PLUGIN.glob(".*-plugin/plugin.json"):
            manifest = json.loads(manifest_path.read_text())
            for key in ("hooks", "mcpServers", "apps"):
                self.assertNotIn(key, manifest)
        self.assertFalse((PLUGIN / ".mcp.json").exists())

    def test_marketplace_registrations(self):
        codex = json.loads((REPO / ".agents/plugins/marketplace.json").read_text())
        claude = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
        for host, catalogue in (("codex", codex), ("claude", claude)):
            entries = [p for p in catalogue["plugins"] if p["name"] == "pzmap"]
            self.assertEqual(len(entries), 1, host)
            source = entries[0]["source"]
            actual = source["path"] if isinstance(source, dict) else source
            self.assertEqual(actual, "./plugins/pzmap")


    def test_payload_check_ignores_yaml_layout_but_detects_changed_meaning(self):
        with tempfile.TemporaryDirectory(prefix="pzmap-payload-") as tmp:
            first = Path(tmp) / "a" / "SKILL.md"
            second = Path(tmp) / "b" / "SKILL.md"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("---\nname: example\ndescription: Two words\n---\n\n# Example\nKeep the original notes.\n", encoding="utf-8")
            second.write_text("---\nname: example\ndescription: >-\n  Two words\n---\n\n# Example\nKeep the original notes.\n", encoding="utf-8")
            self.assertEqual(payload_contract(first), payload_contract(second))
            second.write_text(second.read_text().replace("original notes", "new notes"), encoding="utf-8")
            self.assertNotEqual(payload_contract(first), payload_contract(second))
            second.write_text(first.read_text().replace("Two words", "Other meaning"), encoding="utf-8")
            self.assertNotEqual(payload_contract(first), payload_contract(second))

    @unittest.skipUnless(CONVERTER.is_file(), "Repository converter is not mounted")
    def test_both_host_roundtrips_and_payload_fidelity(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host), tempfile.TemporaryDirectory(prefix="pzmap-port-") as tmp:
                commands = [
                    [sys.executable, str(CONVERTER), "roundtrip", str(PLUGIN),
                     "--to", host, "--tmp", tmp],
                    [sys.executable, str(CONVERTER), "validate",
                     str(Path(tmp) / f"pzmap-{host}"), "--host", host],
                ]
                for command in commands:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                converted = Path(tmp) / f"pzmap-{host}"
                for original in SKILL.rglob("*"):
                    if original.is_file():
                        copy = converted / original.relative_to(PLUGIN)
                        self.assertEqual(payload_contract(original), payload_contract(copy), str(original))


if __name__ == "__main__":
    unittest.main()
