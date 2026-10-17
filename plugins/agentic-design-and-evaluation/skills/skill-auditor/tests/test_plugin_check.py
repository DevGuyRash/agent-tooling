from __future__ import annotations

import json
import os
import shutil
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
    plugin_dir: Path,
    *extra: str,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict | None]:
    """Run the command line with HOME at a temporary directory and no inherited `*_HOME` variable."""
    with tempfile.TemporaryDirectory() as empty_home:
        environment = {k: v for k, v in os.environ.items() if not k.endswith("_HOME")}
        environment["HOME"] = str(home) if home is not None else empty_home
        environment.update(env or {})
        completed = subprocess.run(
            ["sh", str(SCRIPT), str(plugin_dir), "--format", "json", *extra],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
    return completed, json.loads(completed.stdout) if completed.stdout else None


def codes_of(data: dict) -> list[str]:
    return [o["code"] for o in data["observations"]]


def unchecked_of(data: dict) -> list[str]:
    return [token for token in data["unchecked"].split(",") if token]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def make_plugin(
    tmp: str,
    *,
    name: str = "demo-plugin",
    under: str = "",
    version: str = "1.0.0",
    description: str = DESCRIPTION,
    manifests: dict[str, dict] | None = None,
    skills: dict[str, str] | None = None,
    license_field: str | None = None,
) -> Path:
    """Build a plugin whose host manifests are `manifests` (host -> field overrides); two agreeing hosts by default."""
    plugin_dir = Path(tmp) / under / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    for host, overrides in ({"alpha": {}, "beta": {}} if manifests is None else manifests).items():
        manifest: dict = {"name": name, "version": version, "description": description}
        if license_field:
            manifest["license"] = license_field
        manifest.update(overrides)
        write_json(plugin_dir / f".{host}-plugin" / "plugin.json", manifest)

    for slug, desc in ({"demo-skill": description} if skills is None else skills).items():
        d = plugin_dir / "skills" / slug
        d.mkdir(parents=True, exist_ok=True)
        title = " ".join(w.capitalize() for w in slug.split("-"))
        (d / "SKILL.md").write_text(
            f"---\nname: {title}\ndescription: >-\n  {desc}\n---\n\n# {title}\n",
            encoding="utf-8",
        )

    return plugin_dir


def write_catalog(path: Path, name: str, version: str | None) -> Path:
    # A description containing a comma is the case that breaks naive parsing.
    entry: dict = {
        "name": name,
        "source": f"./plugins/{name}",
        "description": "Compile bounded, verifiable things.",
    }
    if version is not None:
        entry["version"] = version
    write_json(path, {"name": "demo", "plugins": [entry]})
    return path


def install_copy(base: Path, plugin: Path, *, stale: bool = False, version: str = "1.0.0") -> Path:
    """Copy the plugin's skills to <base>/plugins/cache/market/<plugin>/<version>; return the plugin's cache directory."""
    cached = base / "plugins" / "cache" / "market" / plugin.name
    shutil.copytree(plugin / "skills", cached / version / "skills")
    if stale:
        with (cached / version / "skills" / "demo-skill" / "SKILL.md").open("a", encoding="utf-8") as skill:
            skill.write("\nStale body.\n")
    return cached


class PackageShapeObservationTests(unittest.TestCase):
    """The reporter exposes package facts without deciding package policy."""

    def test_version_disagreement_between_hosts_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {"version": "1.0.0"}, "beta": {"version": "2.0.0"}})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(codes_of(data), ["manifest_version_difference"])
        for expected in ("alpha", "beta", "1.0.0", "2.0.0"):
            self.assertIn(expected, data["observations"][0]["fact"])

    def test_description_disagreement_between_hosts_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {}, "beta": {"description": "Something else entirely."}})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        differences = [o for o in data["observations"] if o["code"] == "manifest_description_difference"]
        self.assertEqual(len(differences), 1)
        self.assertIn("alpha", differences[0]["fact"])
        self.assertIn("beta", differences[0]["fact"])

    def test_license_disagreement_between_hosts_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {"license": "MIT"}, "beta": {"license": "Apache-2.0"}})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        differences = [o for o in data["observations"] if o["code"] == "manifest_license_difference"]
        self.assertEqual(len(differences), 1)
        for expected in ("alpha", "beta", "MIT", "Apache-2.0"):
            self.assertIn(expected, differences[0]["fact"])

    def test_a_field_declared_by_one_host_only_is_not_a_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {"license": "MIT"}, "beta": {}})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertNotIn("manifest_license_difference", codes_of(data))

    def test_manifest_and_single_skill_difference_is_observed_for_each_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, skills={"demo-skill": "A different description entirely."})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        differences = [o for o in data["observations"] if o["code"] == "skill_description_difference"]
        self.assertEqual(len(differences), 2)
        self.assertTrue(any("alpha" in o["fact"] for o in differences))
        self.assertTrue(any("beta" in o["fact"] for o in differences))

    def test_no_bundled_skills_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, name="empty-plugin", skills={})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("no_skills", codes_of(data))
        self.assertEqual(data["error_count"], 0)


class ManifestDiscoveryTests(unittest.TestCase):
    """Hosts come from `.<host>-plugin` directory names: none is special and none is required."""

    def test_a_package_with_one_hosts_manifest_is_not_missing_the_others(self) -> None:
        for host in ("claude", "codex", "gamma"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tmp:
                plugin = make_plugin(tmp, manifests={host: {}})
                completed, data = run_plugin_check(plugin)

                self.assertEqual(completed.returncode, 0)
                self.assertEqual(codes_of(data), [])
                self.assertNotIn("manifest-fields", unchecked_of(data))

    def test_two_hosts_that_agree_have_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {"license": "MIT"}, "beta": {"license": "MIT"}})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        for code in codes_of(data):
            self.assertFalse(code.startswith("manifest_"), code)
            self.assertFalse(code.startswith("missing_"), code)
            self.assertNotEqual(code, "no_manifest")

    def test_a_third_hosts_manifest_is_compared_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {}, "beta": {}, "gamma": {"version": "3.0.0"}})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        differences = [o for o in data["observations"] if o["code"] == "manifest_version_difference"]
        self.assertTrue(differences)
        # Alpha and beta agree, so every reported difference involves gamma.
        for observation in differences:
            self.assertIn("gamma", observation["fact"])
            self.assertIn("3.0.0", observation["fact"])

    def test_three_hosts_that_agree_have_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {}, "beta": {}, "gamma": {}})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(codes_of(data), [])

    def test_a_package_with_no_manifest_gets_one_observation_and_other_checks_continue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={})
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(codes_of(data), ["no_manifest"])
        self.assertIn("manifest-fields", unchecked_of(data))
        self.assertEqual(data["skills"], 1)

    def test_an_unreadable_manifest_in_any_host_directory_fails_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            (plugin / ".gamma-plugin").mkdir()
            (plugin / ".gamma-plugin" / "plugin.json").write_text('{"version":', encoding="utf-8")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 2)
        self.assertIsNone(data)
        self.assertIn(".gamma-plugin", completed.stderr)


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
        self.assertNotIn("skill_description_difference", codes_of(data))
        self.assertEqual(data["skills"], 2)


class CatalogTests(unittest.TestCase):
    def test_catalog_version_difference_is_found_past_a_comma(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, version="2.0.0")
            cat = write_catalog(Path(tmp) / "marketplace.json", "demo-plugin", "1.8.1")
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        # The catalog is compared with each of the two manifests' versions.
        differences = [o for o in data["observations"] if o["code"] == "catalog_version_difference"]
        self.assertEqual(len(differences), 2)
        self.assertTrue(any("alpha" in o["fact"] for o in differences))
        self.assertTrue(any("beta" in o["fact"] for o in differences))
        for observation in differences:
            self.assertIn("1.8.1", observation["fact"])
            self.assertIn("2.0.0", observation["fact"])

    def test_the_catalog_version_is_compared_with_every_manifests_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {"version": "1.0.0"}, "beta": {"version": "2.0.0"}})
            cat = write_catalog(Path(tmp) / "marketplace.json", "demo-plugin", "1.0.0")
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        # The catalog agrees with alpha and differs from beta alone.
        differences = [o for o in data["observations"] if o["code"] == "catalog_version_difference"]
        self.assertEqual(len(differences), 1)
        self.assertIn("beta", differences[0]["fact"])
        self.assertIn("2.0.0", differences[0]["fact"])
        self.assertNotIn("alpha", differences[0]["fact"])

    def test_matching_catalog_version_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, version="2.0.0")
            cat = write_catalog(Path(tmp) / "marketplace.json", "demo-plugin", "2.0.0")
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        self.assertNotIn("catalog_version_difference", codes_of(data))

    def test_an_unpublished_plugin_is_observed_not_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            cat = write_catalog(Path(tmp) / "marketplace.json", "some-other-plugin", "1.0.0")
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertIn("not_published", codes_of(data))

    def test_catalog_entry_without_a_version_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            cat = write_catalog(Path(tmp) / "marketplace.json", "demo-plugin", None)
            completed, data = run_plugin_check(plugin, "--marketplace", str(cat))

        self.assertEqual(completed.returncode, 0)
        self.assertIn("catalog_no_version", codes_of(data))

    def test_a_catalog_under_any_hosts_directory_is_found_in_the_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {"version": "2.0.0"}})
            write_catalog(Path(tmp) / ".gamma-plugin" / "marketplace.json", "demo-plugin", "1.8.1")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        differences = [o for o in data["observations"] if o["code"] == "catalog_version_difference"]
        self.assertEqual(len(differences), 1)
        for expected in (".gamma-plugin/marketplace.json", "1.8.1", "alpha", "2.0.0"):
            self.assertIn(expected, differences[0]["fact"])
        self.assertNotIn("catalog", unchecked_of(data))

    def test_a_matching_catalog_under_any_hosts_directory_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {}})
            write_catalog(Path(tmp) / ".gamma-plugin" / "marketplace.json", "demo-plugin", "1.0.0")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(codes_of(data), [])
        self.assertNotIn("catalog", unchecked_of(data))

    def test_an_unpublished_plugin_is_observed_in_a_discovered_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {}})
            write_catalog(Path(tmp) / ".gamma-plugin" / "marketplace.json", "some-other-plugin", "1.0.0")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(codes_of(data), ["not_published"])
        self.assertIn(".gamma-plugin/marketplace.json", data["observations"][0]["fact"])

    def test_catalogs_of_several_hosts_are_each_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, under="outer", manifests={"alpha": {}})
            # The nearer catalog agrees with the manifest; the farther one of another host does not.
            write_catalog(Path(tmp) / "outer" / ".beta-plugin" / "marketplace.json", "demo-plugin", "1.0.0")
            write_catalog(Path(tmp) / ".gamma-plugin" / "marketplace.json", "demo-plugin", "9.9.9")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        differences = [o for o in data["observations"] if o["code"] == "catalog_version_difference"]
        self.assertEqual(len(differences), 1)
        self.assertIn(".gamma-plugin/marketplace.json", differences[0]["fact"])
        self.assertIn("9.9.9", differences[0]["fact"])
        self.assertNotIn("catalog", unchecked_of(data))

    def test_only_the_nearest_catalog_of_a_host_is_consulted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, under="outer", manifests={"alpha": {}})
            write_catalog(Path(tmp) / "outer" / ".gamma-plugin" / "marketplace.json", "demo-plugin", "1.0.0")
            write_catalog(Path(tmp) / ".gamma-plugin" / "marketplace.json", "demo-plugin", "7.7.7")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(codes_of(data), [])

    def test_catalogs_are_searched_five_parents_up_and_no_further(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fifth = make_plugin(tmp, under="a/b/c/d", manifests={"alpha": {}})
            sixth = make_plugin(tmp, under="a/b/c/d/e", manifests={"alpha": {}})
            write_catalog(Path(tmp) / ".gamma-plugin" / "marketplace.json", "demo-plugin", "9.9.9")
            _, found = run_plugin_check(fifth)
            _, missed = run_plugin_check(sixth)

        self.assertIn("catalog_version_difference", codes_of(found))
        self.assertNotIn("catalog", unchecked_of(found))
        self.assertNotIn("catalog_version_difference", codes_of(missed))
        self.assertIn("catalog", unchecked_of(missed))

    def test_a_malformed_catalog_of_any_host_fails_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {}})
            broken = Path(tmp) / ".gamma-plugin" / "marketplace.json"
            broken.parent.mkdir()
            broken.write_text('{"plugins":', encoding="utf-8")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 2)
        self.assertIsNone(data)
        self.assertIn(".gamma-plugin", completed.stderr)

    @unittest.skipUnless(shutil.which("git"), "git is required to track the plugin directory")
    def test_a_plugin_published_in_several_catalogs_is_reported_untracked_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, manifests={"alpha": {}})
            write_catalog(Path(tmp) / ".beta-plugin" / "marketplace.json", "demo-plugin", "1.0.0")
            write_catalog(Path(tmp) / ".gamma-plugin" / "marketplace.json", "demo-plugin", "1.0.0")
            subprocess.run(
                ["git", "init", "-q", tmp],
                check=True,
                env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
            )
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(codes_of(data), ["published_but_untracked"])


class LicenseTests(unittest.TestCase):
    def test_declared_license_without_a_file_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp, license_field="MIT")
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertIn("license_without_file", codes_of(data))


class UncheckedSurfaceTests(unittest.TestCase):
    def test_surfaces_that_cannot_be_located_are_named_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            completed, data = run_plugin_check(plugin, "--installed", str(Path(tmp) / "nowhere"))

        self.assertEqual(completed.returncode, 0)
        self.assertIn("install", unchecked_of(data))

    def test_an_installed_copy_that_exists_nowhere_is_unchecked_by_default_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            completed, data = run_plugin_check(plugin)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("install", unchecked_of(data))
        self.assertIn("catalog", unchecked_of(data))

    def test_multiple_cached_versions_are_not_guessed_as_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            home = Path(tmp) / "home"
            cache_root = home / ".agentx" / "plugins" / "cache" / "demo" / "demo-plugin"
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
        self.assertNotIn("install_drift", codes_of(data))


class InstalledCopyDiscoveryTests(unittest.TestCase):
    """Without --installed, candidates sit at plugins/cache/*/<plugin> under hidden home directories and `*_HOME` directories."""

    def test_a_copy_in_a_hidden_home_directory_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            home = Path(tmp) / "home"
            install_copy(home / ".agentx", plugin, stale=True)
            completed, data = run_plugin_check(plugin, home=home)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("install_drift", codes_of(data))
        self.assertNotIn("install", unchecked_of(data))

    def test_an_identical_copy_in_a_hidden_home_directory_shows_no_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            home = Path(tmp) / "home"
            install_copy(home / ".agentx", plugin)
            completed, data = run_plugin_check(plugin, home=home)

        self.assertEqual(completed.returncode, 0)
        self.assertNotIn("install_drift", codes_of(data))
        self.assertNotIn("install-demo-skill-not-found", unchecked_of(data))
        # The comparison ran, so the surfaces it leaves out are named.
        self.assertIn("install-package-surfaces-outside-skills", unchecked_of(data))

    def test_a_copy_under_a_home_variable_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            home = Path(tmp) / "home"
            home.mkdir()
            zeta = Path(tmp) / "zeta"
            install_copy(zeta, plugin, stale=True)
            completed, data = run_plugin_check(plugin, home=home, env={"ZETA_HOME": str(zeta)})

        self.assertEqual(completed.returncode, 0)
        self.assertIn("install_drift", codes_of(data))
        self.assertNotIn("install", unchecked_of(data))

    def test_one_cache_reached_by_a_hidden_directory_and_a_home_variable_is_one_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            home = Path(tmp) / "home"
            install_copy(home / ".agentx", plugin, stale=True)
            alias = Path(tmp) / "alias"
            alias.symlink_to(home / ".agentx", target_is_directory=True)
            for spelling in (home / ".agentx", alias):
                with self.subTest(spelling=spelling.name):
                    completed, data = run_plugin_check(plugin, home=home, env={"AGENTX_HOME": str(spelling)})

                    self.assertEqual(completed.returncode, 0)
                    self.assertIn("install_drift", codes_of(data))
                    self.assertNotIn("install-multiple-host-caches-use---installed", unchecked_of(data))

    def test_two_candidate_caches_are_not_guessed_between_and_installed_resolves_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            home = Path(tmp) / "home"
            install_copy(home / ".agentx", plugin, stale=True)
            zeta = Path(tmp) / "zeta"
            chosen = install_copy(zeta, plugin, stale=True)
            env = {"ZETA_HOME": str(zeta)}
            completed, data = run_plugin_check(plugin, home=home, env=env)
            named_completed, named = run_plugin_check(plugin, "--installed", str(chosen), home=home, env=env)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("install-multiple-host-caches-use---installed", unchecked_of(data))
        self.assertNotIn("install_drift", codes_of(data))
        self.assertEqual(named_completed.returncode, 0)
        self.assertIn("install_drift", codes_of(named))
        self.assertNotIn("install-multiple-host-caches-use---installed", unchecked_of(named))

    def test_only_hidden_home_directories_and_home_variables_are_searched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            home = Path(tmp) / "home"
            install_copy(home / "visible", plugin, stale=True)
            other = Path(tmp) / "other"
            install_copy(other, plugin, stale=True)
            bare = Path(tmp) / "bare"
            bare.mkdir()
            completed, data = run_plugin_check(
                plugin, home=home, env={"OTHER_DIR": str(other), "BARE_HOME": str(bare)}
            )

        self.assertEqual(completed.returncode, 0)
        self.assertNotIn("install_drift", codes_of(data))
        self.assertIn("install", unchecked_of(data))

    def test_a_home_directory_that_does_not_exist_is_no_candidate_not_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin = make_plugin(tmp)
            completed, data = run_plugin_check(plugin, home=Path(tmp) / "no-such-home")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("install", unchecked_of(data))


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
        self.assertIn("install_drift", codes_of(data))


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
