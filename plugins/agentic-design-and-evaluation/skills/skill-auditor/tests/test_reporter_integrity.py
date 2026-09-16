"""Independent input fixtures for preservation and collection-failure contracts."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def fixture(base, name="fixture", descriptions=("Show 猫", "Show 猫")):
    root = base / name
    for host, description in zip(("claude", "codex"), descriptions):
        path = root / f".{host}-plugin/plugin.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(
            {"name": root.name, "version": "1.0.0", "description": description},
            ensure_ascii=host == "claude", indent=2), encoding="utf-8")
    skill = root / "skills/example"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: example\ndescription: 'Show 猫'\n---\n# Example\n", encoding="utf-8")
    catalog = root / "catalog.json"
    catalog.write_text(json.dumps({"name": "test", "plugins": [
        {"name": root.name, "version": "1.0.0", "source": "./" + root.name}
    ]}, indent=2), encoding="utf-8")
    return root, skill, catalog


def report(name, target, *flags):
    result = subprocess.run(
        ["sh", str(SCRIPTS / f"{name}.sh"), str(target), "--format", "json", *map(str, flags)],
        text=True, capture_output=True, timeout=20)
    return result, json.loads(result.stdout) if result.stdout else None


def plugin_report(root, catalog, installed=None):
    return report("plugin_check", root, "--marketplace", catalog,
                  "--installed", root if installed is None else installed)


def codes(data):
    return {item["code"] for item in data["observations"]}


class UnicodeAndCatalogTests(unittest.TestCase):
    def test_unicode_and_json_representation_are_distinct_properties(self):
        for left, right, differs in [
            ("Show 猫", "Show 犬", True),
            ("Show 猫", "Show 猫", False),
            ("literal \\u732b", "literal 猫", True),
            ("line\n", "line", True),
        ]:
            with self.subTest(left=left, right=right), tempfile.TemporaryDirectory() as tmp:
                root, _, catalog = fixture(Path(tmp), descriptions=(left, right))
                result, data = plugin_report(root, catalog)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual("manifest_description_difference" in codes(data), differs)
                if not differs:
                    self.assertNotIn("skill_description_difference", codes(data))

    def test_catalog_whitespace_and_key_order_do_not_change_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _, catalog = fixture(Path(tmp))
            result, pretty = plugin_report(root, catalog)
            self.assertEqual(result.returncode, 0, result.stderr)
            catalog.write_text(json.dumps(json.loads(catalog.read_text()),
                                          separators=(",", ":"), sort_keys=True), encoding="utf-8")
            result, compact = plugin_report(root, catalog)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pretty, compact)
            self.assertNotIn("catalog_no_version", codes(compact))

    def test_name_mentioned_in_another_entry_does_not_publish_the_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _, catalog = fixture(Path(tmp))
            catalog.write_text(json.dumps({"name": "test", "plugins": [
                {"name": "unrelated", "version": "1.0.0", "description": root.name}
            ]}), encoding="utf-8")
            result, data = plugin_report(root, catalog)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("not_published", codes(data))


class LinkAndPathTests(unittest.TestCase):
    def test_regular_file_named_scripts_is_not_a_script_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, skill, _ = fixture(Path(tmp))
            (skill / "scripts").write_text("A data file, not a scripts directory.\n")
            result, data = report("script_sanity", skill)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(data["script_count"], 0)

    def test_symlink_retarget_changes_identity_without_reading_its_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, skill, catalog = fixture(Path(tmp))
            refs = skill / "references"
            refs.mkdir()
            (refs / "a.md").write_text("First source\n")
            (refs / "b.md").write_text("Second source\n")
            (refs / "current.md").symlink_to("a.md")
            (refs / "loop").symlink_to(".", target_is_directory=True)
            installed = Path(tmp) / "installed"
            shutil.copytree(root, installed, symlinks=True)
            result, same = plugin_report(root, catalog, installed)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("install_drift", codes(same))
            link = installed / "skills/example/references/current.md"
            link.unlink()
            link.symlink_to("b.md")
            result, changed = plugin_report(root, catalog, installed)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("install_drift", codes(changed))
            self.assertEqual((refs / "current.md").readlink().as_posix(), "a.md")

    def test_path_characters_survive_json_and_script_collection(self):
        for name in ["tab\tparent", "line\nparent", 'quote"parent', "slash\\parent", "crlf\r\nparent"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root, skill, catalog = fixture(Path(tmp) / name)
                scripts = skill / "scripts"
                scripts.mkdir()
                script = scripts / 'odd\tname\n".sh'
                script.write_text("#!/bin/sh\nexit 0\n")
                script.chmod(0o755)
                for reporter in ("frontmatter_check", "plugin_check", "script_sanity", "reference_check"):
                    target = root if reporter == "plugin_check" else skill
                    flags = ("--marketplace", catalog, "--installed", root) if reporter == "plugin_check" else ()
                    result, data = report(reporter, target, *flags)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    field = "plugin_dir" if reporter == "plugin_check" else "skill_dir"
                    self.assertEqual(data[field], str(target))
                    if reporter == "script_sanity":
                        self.assertEqual(data["script_count"], 1)
                self.assertEqual(script.read_text(), "#!/bin/sh\nexit 0\n")


class FailedCollectionTests(unittest.TestCase):
    def test_malformed_or_ambiguous_json_is_failed_collection(self):
        malformed = [
            ("manifest", '{"description":"partial"'),
            ("manifest", '{"description":"one","description":"two"}'),
            ("catalog", '{"plugins":'),
            ("catalog", '{"plugins":{}}'),
        ]
        for surface, payload in malformed:
            with self.subTest(surface=surface, payload=payload), tempfile.TemporaryDirectory() as tmp:
                root, _, catalog = fixture(Path(tmp))
                path = root / ".codex-plugin/plugin.json" if surface == "manifest" else catalog
                path.write_text(payload)
                result, data = plugin_report(root, catalog)
                self.assertEqual(result.returncode, 2)
                self.assertIsNone(data)
                self.assertIn("error:", result.stderr)
                self.assertIn("hint:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
