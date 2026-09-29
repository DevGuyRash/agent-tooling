from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parents[1]
SKILLS_ROOT = PLUGIN_ROOT / "skills"

WEB_URL_PATTERN = re.compile(r"\bhttps?://[^\s<>()\[\]{}]+", re.IGNORECASE)
CONCRETE_USER_HOME_PATTERN = re.compile(
    r"/(?:home|Users)/[A-Za-z0-9._-]+"
    r"(?=/|[\s`\"'<>),;:\]}]|$)"
    r"|\b[A-Za-z]:(?:\\){1,2}Users(?:\\){1,2}[A-Za-z0-9._-]+"
    r"(?=(?:\\){1,2}|[\s`\"'<>),;:\]}]|$)",
    re.IGNORECASE,
)

EXPECTED_SKILLS = {
    "rust-development",
    "python-development",
    "javascript-development",
    "typescript-development",
    "go-development",
    "java-development",
    "kotlin-development",
    "csharp-development",
    "c-development",
    "cpp-development",
    "swift-development",
    "ruby-development",
    "php-development",
    "shell-development",
    "sql-development",
    "test-driven-development",
    "systematic-debugging",
    "refactoring",
    "performance-engineering",
    "trunk-based-development",
    "behavior-preserving-migration",
    "concurrency-engineering",
    "nodejs-development",
    "async-rust",
    "unsafe-rust",
    "rust-panic-audit",
}

EXPECTED_LANGUAGE_SKILLS = {
    "rust-development",
    "python-development",
    "javascript-development",
    "typescript-development",
    "go-development",
    "java-development",
    "kotlin-development",
    "csharp-development",
    "c-development",
    "cpp-development",
    "swift-development",
    "ruby-development",
    "php-development",
    "shell-development",
    "sql-development",
}

LANGUAGE_EVAL_FIXTURES = {
    "rust-development": ("eval-panic-resistant-boundary", "evals/files/panic_boundary.rs", ("parse()", "unwrap()")),
    "python-development": (
        "eval-async-bounded-lifecycle",
        "evals/files/async_worker.py",
        ("client_factory()", "asyncio.create_task", "await asyncio.Event().wait()"),
    ),
    "javascript-development": ("eval-falsy-default", "evals/files/settings-loader.js", ("raw.enabled || true", "raw.retries || 3")),
    "typescript-development": ("eval-runtime-boundary", "evals/files/api-client.ts", ("as User", "user.profile.name")),
    "go-development": ("eval-error-identity", "evals/files/errors.go", ("ErrNotFound", "%v")),
    "java-development": ("eval-equality-contract", "evals/files/AccountKey.java", ("equalsIgnoreCase", "hashCode")),
    "kotlin-development": ("eval-data-class-copy", "evals/files/Batch.kt", ("MutableList", "batch.copy()")),
    "csharp-development": ("eval-rethrow-stack", "evals/files/Worker.cs", ("log(ex)", "throw ex;")),
    "c-development": ("eval-overflow-before-allocation", "evals/files/packet_items.c", ("size_t count", "count * sizeof")),
    "cpp-development": ("eval-dangling-view", "evals/files/dangling_view.cpp", ("std::string name", "return name")),
    "swift-development": ("eval-force-unwrap-boundary", "evals/files/JSONNameDecoder.swift", ("try!", "as! String")),
    "ruby-development": ("eval-queue-worker-lifetime", "evals/files/worker.rb", ("Thread::Queue", "workers.map(&:join)")),
    "php-development": ("eval-worker-resource-lifetime", "evals/files/Worker.php", ("beginTransaction", "__destruct")),
    "shell-development": ("eval-posix-routing", "evals/files/deploy.sh", ("#!/bin/sh", "targets=(")),
    "sql-development": ("eval-nullable-not-in", "evals/files/exclusion.sql", ("NOT IN", "blocked_customers")),
}

REQUIRED_QUALITY_EVALS = {
    "concurrency-engineering": {
        "eval-eager-admission",
        "eval-cancel-join-cleanup",
        "eval-failure-unblocks-submitters",
        "eval-parallel-scaling",
    },
    "refactoring": {
        "eval-large-cohesive-file",
        "eval-small-real-boundary",
        "eval-unjustified-abstractions",
    },
    "performance-engineering": {
        "eval-micro-system-disagreement",
        "eval-speculative-parallelism",
        "eval-justified-parallelism",
    },
    "c-development": {"eval-worker-shutdown-race"},
    "cpp-development": {"eval-worker-shutdown-race"},
    "typescript-development": {"eval-browser-worker-cancellation"},
}

REQUIRED_TRIGGER_PROBES = {
    "concurrency-engineering": {
        "implicit-callback-pressure",
        "composition-java-workers",
        "composition-parallel-performance",
    },
    "c-development": {"implicit-c-worker-race"},
    "cpp-development": {"implicit-cpp-worker-race"},
    "java-development": {
        "implicit-java-source",
        "composition-java-kotlin-api",
    },
    "kotlin-development": {
        "implicit-kotlin-source",
        "composition-java-kotlin-api",
    },
    "sql-development": {
        "composition-unknown-slow-query",
        "composition-defined-performance",
    },
    "typescript-development": {"implicit-browser-worker-cancellation"},
}

CANONICAL_COMPOSITION_ROUTES = {
    "python-feature-tdd": (
        frozenset({"python-development", "test-driven-development"}),
        frozenset(),
    ),
    "unknown-async-rust-hang": (
        frozenset({"rust-development", "async-rust", "systematic-debugging"}),
        frozenset({"performance-engineering"}),
    ),
    "rust-ffi-invariants": (
        frozenset({"rust-development", "unsafe-rust"}),
        frozenset({"rust-panic-audit"}),
    ),
    "high-availability-panic-audit": (
        frozenset({"rust-development", "rust-panic-audit"}),
        frozenset(),
    ),
    "sync-rust-worker-shutdown": (
        frozenset({"rust-development", "concurrency-engineering"}),
        frozenset({"async-rust", "unsafe-rust", "rust-panic-audit"}),
    ),
    "java-worker-lifecycle": (
        frozenset({"java-development", "concurrency-engineering"}),
        frozenset({"async-rust"}),
    ),
    "bounded-parallel-performance": (
        frozenset({"concurrency-engineering", "performance-engineering"}),
        frozenset({"systematic-debugging"}),
    ),
    "node-module-resolution": (
        frozenset({"nodejs-development", "javascript-development"}),
        frozenset({"typescript-development"}),
    ),
    "java-only-api": (
        frozenset({"java-development"}),
        frozenset({"kotlin-development"}),
    ),
    "kotlin-only-api": (
        frozenset({"kotlin-development"}),
        frozenset({"java-development"}),
    ),
    "mixed-java-kotlin-api": (
        frozenset({"java-development", "kotlin-development"}),
        frozenset(),
    ),
    "tsx-type-system": (
        frozenset({"typescript-development"}),
        frozenset({"javascript-development"}),
    ),
    "bash-quoting": (frozenset({"shell-development"}), frozenset()),
    "powershell-errors": (frozenset({"shell-development"}), frozenset()),
    "sql-schema-transition": (
        frozenset({"sql-development", "behavior-preserving-migration"}),
        frozenset(),
    ),
    "unknown-slow-relational-query": (
        frozenset({"sql-development", "systematic-debugging"}),
        frozenset({"performance-engineering"}),
    ),
    "slow-relational-query": (
        frozenset({"sql-development", "performance-engineering"}),
        frozenset({"systematic-debugging"}),
    ),
    "parser-split": (
        frozenset({"go-development", "refactoring"}),
        frozenset({"test-driven-development"}),
    ),
    "routine-pr": (frozenset(), frozenset({"trunk-based-development"})),
    "long-feature-integration": (
        frozenset({"trunk-based-development"}),
        frozenset(),
    ),
    "readme-typo": (
        frozenset(),
        frozenset({"rust-development", "refactoring"}),
    ),
    "conceptual-question": (frozenset(), frozenset({"rust-development"})),
}


def frontmatter(path: Path) -> dict[str, object]:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    if len(parts) != 3:
        raise AssertionError(f"missing YAML frontmatter: {path}")
    data = yaml.safe_load(parts[1])
    if not isinstance(data, dict):
        raise AssertionError(f"frontmatter is not an object: {path}")
    return data


def concrete_user_home_paths(text: str) -> list[str]:
    without_web_urls = WEB_URL_PATTERN.sub("", text)
    return [match.group(0) for match in CONCRETE_USER_HOME_PATTERN.finditer(without_web_urls)]


class PluginContractTests(unittest.TestCase):
    def skill_dirs(self) -> list[Path]:
        return sorted(path for path in SKILLS_ROOT.iterdir() if path.is_dir())

    def assert_skill_routes(
        self, item: dict[str, object], field: str, context: str
    ) -> frozenset[str]:
        self.assertIn(field, item, context)
        routes = item[field]
        self.assertIsInstance(routes, list, context)
        assert isinstance(routes, list)
        self.assertTrue(
            all(isinstance(route, str) and route.strip() for route in routes), context
        )
        self.assertEqual(len(routes), len(set(routes)), context)
        route_set = frozenset(routes)
        self.assertLessEqual(route_set, EXPECTED_SKILLS, context)
        return route_set

    def test_exact_catalog_and_portable_frontmatter(self) -> None:
        directories = self.skill_dirs()
        self.assertEqual(EXPECTED_SKILLS, {path.name for path in directories})
        maintainer_notes = (PLUGIN_ROOT / "MAINTAINERS.md").read_text(encoding="utf-8")
        self.assertIn(f"all {len(EXPECTED_SKILLS)} skills remain discoverable", maintainer_notes)
        agent_contract = (PLUGIN_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(
            "The public catalog is the skill directories listed in this plugin's README and enforced by its contract test.",
            agent_contract,
        )
        self.assertNotRegex(agent_contract, r"public catalog is exactly the \d+ skill")
        for directory in directories:
            skill_file = directory / "SKILL.md"
            data = frontmatter(skill_file)
            name = data.get("name")
            description = data.get("description")
            self.assertEqual(directory.name, name)
            self.assertRegex(directory.name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
            self.assertIsInstance(description, str)
            assert isinstance(description, str)
            self.assertTrue(description.strip(), directory.name)
            self.assertLessEqual(len(description), 1024, directory.name)
            body = skill_file.read_text(encoding="utf-8")
            h1 = next(line[2:] for line in body.splitlines() if line.startswith("# "))
            self.assertNotEqual(directory.name, h1)

    def test_references_are_one_hop_reachable(self) -> None:
        link_pattern = re.compile(r"(?:<skills-file-root>/)?references/([A-Za-z0-9_.-]+)")
        for directory in self.skill_dirs():
            skill_text = (directory / "SKILL.md").read_text(encoding="utf-8")
            linked = set(link_pattern.findall(skill_text))
            references = directory / "references"
            actual = {path.name for path in references.glob("*.md")} if references.exists() else set()
            self.assertEqual(actual, linked, directory.name)
            for path in references.glob("*.md") if references.exists() else []:
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"(?:<skills-file-root>/)?references/[A-Za-z0-9_.-]+")

    def test_openai_metadata_and_eval_contracts(self) -> None:
        for directory in self.skill_dirs():
            metadata = yaml.safe_load(
                (directory / "agents" / "openai.yaml").read_text(encoding="utf-8")
            )
            interface = metadata["interface"]
            policy = metadata["policy"]
            self.assertRegex(interface["display_name"], r"^[A-Z]")
            body = (directory / "SKILL.md").read_text(encoding="utf-8")
            h1 = next(line[2:] for line in body.splitlines() if line.startswith("# "))
            self.assertEqual(h1, interface["display_name"], directory.name)
            self.assertIsInstance(interface["short_description"], str)
            self.assertTrue(interface["short_description"].strip(), directory.name)
            self.assertIn(f"${directory.name}", interface["default_prompt"])
            self.assertIs(policy["allow_implicit_invocation"], True)

            trigger_path = directory / "evals" / "trigger-prompts.json"
            task_path = directory / "evals" / "evals.json"
            trigger = json.loads(trigger_path.read_text(encoding="utf-8"))
            tasks = json.loads(task_path.read_text(encoding="utf-8"))
            self.assertEqual(directory.name, trigger["skill_name"])
            self.assertEqual(directory.name, tasks["skill_name"])
            positives = [item for item in trigger["queries"] if item["should_trigger"]]
            self.assertTrue(
                any(
                    "composition" in item["id"] or "ambiguous" in item["id"]
                    for item in trigger["queries"]
                ),
                directory.name,
            )
            self.assertTrue(
                any(
                    f"${directory.name}" in item["query"]
                    or f":{directory.name}" in item["query"]
                    or "explicit" in item["id"]
                    for item in positives
                ),
                directory.name,
            )
            self.assertTrue(tasks["evals"], directory.name)

    def test_quality_eval_and_trigger_probes_are_retained(self) -> None:
        for skill_name, required_ids in REQUIRED_QUALITY_EVALS.items():
            tasks = json.loads(
                (SKILLS_ROOT / skill_name / "evals" / "evals.json").read_text(
                    encoding="utf-8"
                )
            )
            actual_ids = {item["id"] for item in tasks["evals"]}
            self.assertLessEqual(required_ids, actual_ids, skill_name)

        for skill_name, required_ids in REQUIRED_TRIGGER_PROBES.items():
            triggers = json.loads(
                (SKILLS_ROOT / skill_name / "evals" / "trigger-prompts.json").read_text(
                    encoding="utf-8"
                )
            )
            actual_ids = {item["id"] for item in triggers["queries"]}
            self.assertLessEqual(required_ids, actual_ids, skill_name)

    def test_distributable_content_has_no_concrete_user_home_paths(self) -> None:
        allowed = "\n".join(
            (
                "/home/<user>/repo",
                "/Users/${USER}/repo",
                r"C:\Users\<username>\repo",
                r"C:\\Users\\<username>\\repo",
                "https://example.test/home/alice/guide",
                "https://example.test/Users/alice/guide",
            )
        )
        self.assertEqual([], concrete_user_home_paths(allowed))

        concrete = "\n".join(
            (
                "/home/" + "alice/repo",
                "/Users/" + "bob/repo",
                "C:\\" + "Users\\" + "carol\\repo",
                "C:\\\\" + "Users\\\\" + "dave\\\\repo",
            )
        )
        self.assertEqual(4, len(concrete_user_home_paths(concrete)))

        offenders = []
        for path in sorted(item for item in PLUGIN_ROOT.rglob("*") if item.is_file()):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for match in concrete_user_home_paths(text):
                offenders.append(f"{path.relative_to(PLUGIN_ROOT)}: {match}")
        self.assertEqual([], offenders)

    def test_language_task_evals_have_exact_maintained_fixtures(self) -> None:
        self.assertEqual(EXPECTED_LANGUAGE_SKILLS, set(LANGUAGE_EVAL_FIXTURES))
        attached_skills = set()
        expected_fixture_paths = set()
        for skill_name, (eval_id, expected_file, semantic_markers) in LANGUAGE_EVAL_FIXTURES.items():
            directory = SKILLS_ROOT / skill_name
            tasks = json.loads(
                (directory / "evals" / "evals.json").read_text(encoding="utf-8")
            )
            eval_ids = [item["id"] for item in tasks["evals"]]
            self.assertEqual(len(eval_ids), len(set(eval_ids)), skill_name)
            selected = [item for item in tasks["evals"] if item["id"] == eval_id]
            self.assertEqual(1, len(selected), skill_name)
            self.assertEqual([expected_file], selected[0]["files"], skill_name)

            for item in tasks["evals"]:
                files = item.get("files")
                self.assertIsInstance(files, list, f"{skill_name}/{item['id']}")
                assert isinstance(files, list)
                if files:
                    attached_skills.add(skill_name)
                for relative_name in files:
                    context = f"{skill_name}/{item['id']}"
                    self.assertIsInstance(relative_name, str, context)
                    assert isinstance(relative_name, str)
                    relative_path = Path(relative_name)
                    self.assertFalse(relative_path.is_absolute(), context)
                    self.assertEqual(("evals", "files"), relative_path.parts[:2], context)
                    self.assertNotIn("..", relative_path.parts, context)
                    fixture_path = directory / relative_path
                    self.assertTrue(fixture_path.is_file(), context)
                    fixture_text = fixture_path.read_text(encoding="utf-8")
                    self.assertTrue(fixture_text.strip(), context)
                    if relative_name == expected_file:
                        for marker in semantic_markers:
                            self.assertIn(marker, fixture_text, context)

            expected_fixture_paths.add(directory / expected_file)

        self.assertEqual(EXPECTED_LANGUAGE_SKILLS, attached_skills)
        actual_fixture_paths = {
            path
            for path in SKILLS_ROOT.glob("*/evals/files/**/*")
            if path.is_file()
        }
        self.assertLessEqual(expected_fixture_paths, actual_fixture_paths)

    def test_composition_trigger_routes_are_explicit(self) -> None:
        for directory in self.skill_dirs():
            trigger = json.loads(
                (directory / "evals" / "trigger-prompts.json").read_text(
                    encoding="utf-8"
                )
            )
            for item in trigger["queries"]:
                if "composition" not in item["id"] and "ambiguous" not in item["id"]:
                    continue
                context = f"{directory.name}/{item['id']}"
                self.assertIs(item["should_trigger"], True, context)
                expected = self.assert_skill_routes(item, "expected_skills", context)
                excluded = self.assert_skill_routes(item, "excluded_skills", context)
                self.assertIn(directory.name, expected, context)
                self.assertTrue(expected.isdisjoint(excluded), context)

                external = item.get("external_companion")
                if external is not None:
                    self.assertIsInstance(external, str, context)
                    assert isinstance(external, str)
                    self.assertTrue(external.strip(), context)
                internal_companions = expected - {directory.name}
                self.assertTrue(internal_companions or external, context)

    def test_only_panic_audit_ships_runtime_code(self) -> None:
        scripts = sorted(path for path in SKILLS_ROOT.glob("*/scripts/*") if path.is_file())
        self.assertEqual(
            [SKILLS_ROOT / "rust-panic-audit" / "scripts" / "panic_audit.py"], scripts
        )

    def test_manifest_and_marketplace_versions_agree(self) -> None:
        codex = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        claude = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("software-development", codex["name"])
        self.assertEqual(codex["name"], claude["name"])
        self.assertEqual("2.0.0", codex["version"])
        self.assertEqual(codex["version"], claude["version"])
        self.assertEqual(codex["description"], claude["description"])
        self.assertTrue((PLUGIN_ROOT / "LICENSE").is_file())
        readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"`software-development` v{codex['version']}", readme)

        codex_marketplace = json.loads(
            (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        claude_marketplace = json.loads(
            (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        codex_entry = next(item for item in codex_marketplace["plugins"] if item["name"] == codex["name"])
        claude_entry = next(item for item in claude_marketplace["plugins"] if item["name"] == codex["name"])
        self.assertEqual("./plugins/software-development", codex_entry["source"]["path"])
        self.assertEqual("./plugins/software-development", claude_entry["source"])
        self.assertEqual("2.0.0", claude_entry["version"])
        for marketplace in (codex_marketplace, claude_marketplace):
            names = [item["name"] for item in marketplace["plugins"]]
            self.assertEqual(len(names), len(set(names)))
            self.assertNotIn("rust-development", names)
            self.assertNotIn("gitops-workflow", names)

    def test_composition_corpus_covers_required_boundaries(self) -> None:
        corpus = json.loads(
            (PLUGIN_ROOT / "evals" / "composition-corpus.json").read_text(encoding="utf-8")
        )
        self.assertEqual("1.0", corpus["schema_version"])
        case_ids = [item["id"] for item in corpus["cases"]]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        cases = {item["id"]: item for item in corpus["cases"]}
        self.assertEqual(set(CANONICAL_COMPOSITION_ROUTES), set(cases))
        for case_id, (expected_routes, excluded_routes) in (
            CANONICAL_COMPOSITION_ROUTES.items()
        ):
            item = cases[case_id]
            expected = self.assert_skill_routes(item, "expected_skills", case_id)
            excluded = self.assert_skill_routes(item, "excluded_skills", case_id)
            self.assertEqual(expected_routes, expected, case_id)
            self.assertEqual(excluded_routes, excluded, case_id)
            self.assertTrue(expected.isdisjoint(excluded), case_id)
            self.assertTrue(item["prompt"].strip(), case_id)


if __name__ == "__main__":
    unittest.main()
