from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "scripts" / "plugin_check.sh"

DESCRIPTION = (
    "Check demo things and explain findings. Use when the task involves: "
    "(1) Auditing demo things, (2) Reviewing demo packaging."
)


def run_plugin_check(
    plugin_dir: Path, *extra: str, home: Path | None = None
) -> tuple[subprocess.CompletedProcess[str], dict]:
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    completed = subprocess.run(
        ["sh", str(SCRIPT), str(plugin_dir), "--format", "json", *extra],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return completed, json.loads(completed.stdout)


def make_plugin(
    tmp: str,
    *,
    name: str = "demo-plugin",
    version: str = "1.0.0",
    codex_version: str | None = None,
    description: str = DESCRIPTION,
    codex_description: str | None = None,
    skills: dict[str, str] | None = None,
    license_field: str | None = None,
) -> Path:
    plugin_dir = Path(tmp) / name
    (plugin_dir / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin_dir / ".codex-plugin").mkdir(parents=True, exist_ok=True)

    claude: dict = {"name": name, "version": version, "description": description}
    codex: dict = {
        "name": name,
        "version": codex_version or version,
        "description": codex_description or description,
    }
    if license_field:
        claude["license"] = license_field
        codex["license"] = license_field

    (plugin_dir / ".claude-plugin/plugin.json").write_text(json.dumps(claude, indent=2), encoding="utf-8")
    (plugin_dir / ".codex-plugin/plugin.json").write_text(json.dumps(codex, indent=2), encoding="utf-8")

    for slug, desc in (skills or {"demo-skill": description}).items():
        d = plugin_dir / "skills" / slug
        d.mkdir(parents=True, exist_ok=True)
        title = " ".join(w.capitalize() for w in slug.split("-"))
        (d / "SKILL.md").write_text(
            f"---\nname: {title}\ndescription: >-\n  {desc}\n---\n\n# {title}\n",
            encoding="utf-8",
        )

    return plugin_dir


class PackageShapeObservationTests(unittest.TestCase):
    """The reporter exposes package facts without deciding package policy."""

    def test_version_disagreement_between_hosts_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, version="1.0.0", codex_version="2.0.0")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("manifest_version_difference", {o["code"] for o in data["observations"]})

    def test_description_disagreement_between_hosts_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, codex_description="Something else entirely.")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("manifest_description_difference", {o["code"] for o in data["observations"]})

    def test_manifest_and_single_skill_difference_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, skills={"demo-skill": "A different description entirely."})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("skill_description_difference", {o["code"] for o in data["observations"]})

    def test_a_missing_codex_manifest_is_observed_without_aborting_other_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            (plugin / ".codex-plugin/plugin.json").unlink()
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("missing_codex_manifest", {o["code"] for o in data["observations"]})
        self.assertEqual(data["skills"], 1)

    def test_a_missing_claude_manifest_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            (plugin / ".claude-plugin/plugin.json").unlink()
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("missing_claude_manifest", {o["code"] for o in data["observations"]})

    def test_no_bundled_skills_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "empty-plugin"
            (plugin_dir / ".claude-plugin").mkdir(parents=True)
            (plugin_dir / ".codex-plugin").mkdir(parents=True)
            manifest = {"name": "empty-plugin", "version": "1.0.0", "description": DESCRIPTION}
            (plugin_dir / ".claude-plugin/plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
            (plugin_dir / ".codex-plugin/plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

            completed, data = run_plugin_check(plugin_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("no_skills", {o["code"] for o in data["observations"]})
        self.assertEqual(data["error_count"], 0)


class EncodingTests(unittest.TestCase):
    def test_a_json_escaped_dash_does_not_read_as_drift(self) -> None:
        # JSON stores non-ASCII as \uXXXX while YAML carries the literal bytes.
        # Without folding both, every description holding an em-dash would be
        # reported as drifted from itself.
        desc = "Check demo things — and explain. Use when the task involves: (1) Auditing, (2) Reviewing."
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, description=desc, skills={"demo-skill": desc})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0, data["errors"])


class RoutingTests(unittest.TestCase):
    def test_multi_skill_plugins_skip_the_single_skill_comparison(self) -> None:
        # A manifest description cannot equal two different skill descriptions.
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(
                tmp,
                skills={"demo-a": "Do A things always.", "demo-b": "Do B things always."},
            )
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertNotIn("skill_description_difference", {o["code"] for o in data["observations"]})
        self.assertEqual(data["skills"], 2)


class CatalogTests(unittest.TestCase):
    def _catalog(self, tmp: str, name: str, version: str | None) -> Path:
        # A description containing a comma is the case that breaks naive parsing.
        entry: dict = {
            "name": name,
            "source": f"./plugins/{name}",
            "description": "Compile bounded, verifiable things.",
        }
        if version is not None:
            entry["version"] = version
        cat = Path(tmp) / "marketplace.json"
        cat.write_text(
            json.dumps({"name": "demo", "plugins": [entry]}, indent=2),
            encoding="utf-8",
        )
        return cat

    def test_catalog_version_difference_is_found_past_a_comma(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, version="2.0.0")
            cat = self._catalog(tmp, "demo-plugin", "1.8.1")
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        self.assertIn("catalog_version_difference", {o["code"] for o in data["observations"]})

    def test_matching_catalog_version_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, version="2.0.0")
            cat = self._catalog(tmp, "demo-plugin", "2.0.0")
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        self.assertNotIn("catalog_version_difference", {o["code"] for o in data["observations"]})

    def test_an_unpublished_plugin_is_observed_not_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            cat = self._catalog(tmp, "some-other-plugin", "1.0.0")
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertIn("not_published", {o["code"] for o in data["observations"]})

    def test_catalog_entry_without_a_version_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            cat = self._catalog(tmp, "demo-plugin", None)
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        self.assertIn("catalog_no_version", {o["code"] for o in data["observations"]})


class LicenseTests(unittest.TestCase):
    def test_declared_license_without_a_file_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, license_field="MIT")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertIn("license_without_file", {o["code"] for o in data["observations"]})


class UncheckedSurfaceTests(unittest.TestCase):
    def test_surfaces_that_cannot_be_located_are_named_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            completed, data = run_plugin_check(plugin, "--installed", str(Path(tmp) / "nowhere"))

        self.assertEqual(completed.returncode, 0)
        self.assertIn("install", data["unchecked"])

    def test_multiple_cached_versions_are_not_guessed_as_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            home = Path(tmp) / "home"
            cache_root = home / ".claude" / "plugins" / "cache" / "demo" / "demo-plugin"
            for version in ("1.0.0", "2.0.0"):
                installed = cache_root / version / "skills" / "demo-skill"
                installed.mkdir(parents=True)
                (installed / "SKILL.md").write_text(
                    "---\nname: demo-skill\ndescription: >-\n  " + DESCRIPTION + "\n---\n",
                    encoding="utf-8",
                )

            completed, data = run_plugin_check(plugin, home=home)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("multiple-copies", data["unchecked"])
        self.assertNotIn("install_drift", {item["code"] for item in data["observations"]})


class InstalledTreeTests(unittest.TestCase):
    def test_installed_body_or_script_drift_is_observed_even_when_description_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            source_skill = plugin / "skills" / "demo-skill"
            (source_skill / "scripts").mkdir()
            source_script = source_skill / "scripts" / "run.sh"
            source_script.write_text("#!/bin/sh\necho source\n", encoding="utf-8")
            source_script.chmod(0o755)

            installed = Path(tmp) / "installed"
            installed_skill = installed / "skills" / "demo-skill"
            installed_skill.mkdir(parents=True)
            (installed_skill / "SKILL.md").write_text(
                (source_skill / "SKILL.md").read_text(encoding="utf-8") + "\nStale body.\n",
                encoding="utf-8",
            )
            (installed_skill / "scripts").mkdir()
            installed_script = installed_skill / "scripts" / "run.sh"
            installed_script.write_text("#!/bin/sh\necho installed\n", encoding="utf-8")
            installed_script.chmod(0o644)

            completed, data = run_plugin_check(plugin, "--installed", str(installed))

        self.assertEqual(completed.returncode, 0)
        self.assertIn("install_drift", {o["code"] for o in data["observations"]})


class CleanTargetTests(unittest.TestCase):
    def test_a_coherent_plugin_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(data["observation_count"], 0)
        self.assertEqual(data["skills"], 1)

    def test_active_plugin_passes(self) -> None:
        completed, data = run_plugin_check(PLUGIN_ROOT)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)


class ObservationsOnlyExitTests(unittest.TestCase):
    def test_a_target_whose_only_findings_are_observations_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(
                tmp,
                license_field="MIT",
                skills={
                    "demo-log": "Log things for later review.",
                    "demo-mend": "Mend things. Use when the task involves: (1) Mending, (2) Closing.",
                },
            )
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertGreater(data["observation_count"], 0)


class SourceTagTests(unittest.TestCase):
    def test_every_observation_source_is_open_standard_or_repo_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(
                tmp,
                license_field="MIT",
                skills={
                    "demo-log": "Log things. Do not use for mending (that is demo-mend).",
                    "demo-mend": "Mend things. Use when the task involves: (1) Mending, (2) Closing.",
                },
            )

            completed, data = run_plugin_check(plugin)

        self.assertGreater(data["observation_count"], 0)
        for obs in data["observations"]:
            if "source" in obs:
                self.assertIn(obs["source"], {"open-standard", "repo-overlay", "plugin-fit"})

class UsageExitTests(unittest.TestCase):
    def test_unusable_input_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)

            bad_flag = subprocess.run(
                ["sh", str(SCRIPT), str(plugin), "--nope"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(bad_flag.returncode, 2)

            bad_format = subprocess.run(
                ["sh", str(SCRIPT), str(plugin), "--format", "xml"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(bad_format.returncode, 2)
            self.assertIn("hint:", bad_format.stderr)

        missing_dir = subprocess.run(
            ["sh", str(SCRIPT), "/tmp/definitely-not-a-real-plugin-dir-xyz"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(missing_dir.returncode, 2)

if __name__ == "__main__":
    unittest.main()
