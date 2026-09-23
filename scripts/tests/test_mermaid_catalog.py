"""Catalog discovery follows captured sources; fixtures do not prescribe a roster."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("update_mermaid_catalog", REPO / "scripts/update_mermaid_catalog.py")
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


def payload(pages=None, **changes):
    pages = pages or {"novel.md": "# Novel diagram\n\nA novel diagram explains an unfamiliar relationship.\n\n```mermaid\nnewFamily-v4\n  a -> b\n```\n"}
    return {"commit": "1" * 40, "docs": sorted(pages), "sidebar": "", "pages": pages, **changes}


class MermaidCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mermaid-catalog-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / "upstream.json"
        self.output = self.root / "reference.md"

    def call(self, *flags):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = catalog.main(list(flags))
        return code, output.getvalue(), error.getvalue()

    def test_descriptions_prefer_metadata_then_intro_and_keep_notice_separate(self):
        source = "---\ndescription: >-\n  Metadata explains\n  the purpose.\n---\n# Title\n\nOther prose."
        self.assertEqual(catalog.page_description(source), "Metadata explains the purpose.")
        self.assertEqual(catalog.page_description("# Title\n\n> Sets show overlap.\n"), "Sets show overlap.")
        notice = "> An unfamiliar topic: This is an experimental diagram for now."
        source = "# Unfamiliar\n\n" + notice + "\n\nIt arranges events by time.\n"
        description, qualifiers = catalog.page_introduction(source)
        self.assertEqual(description, "It arranges events by time.")
        self.assertEqual(qualifiers, [notice.removeprefix("> ")])
        result = catalog.build_markdown(payload({"unfamiliar.md": source}), "upstream")
        self.assertIn("| Unfamiliar | It arranges events by time.", result)
        self.assertIn("## Source qualifications", result)
        self.assertIn("experimental diagram for now", result)

    def test_structural_blocks_are_not_descriptions(self):
        source = "# Heading\n\n<!-- hidden -->\n\n```text\nnot prose\n```\n\n## Explanation\n\nUseful introductory paragraph.\n"
        self.assertEqual(catalog.page_description(source), "Useful introductory paragraph.")
        self.assertIsNone(catalog.page_description("# Heading\n\n```mermaid\nunknown\n```\n"))

    def test_real_functional_descriptions_follow_status_notices(self):
        upstream = catalog.load_offline_upstream(REPO / "packaging/sources/mermaid/upstream.json")
        for name, phrase in [("mindmap.md", "organize information"), ("timeline.md", "chronological")]:
            self.assertIn(phrase, catalog.page_description(upstream["pages"][name]))
        self.assertIn("overlapping circles", catalog.page_description(upstream["pages"]["venn.md"]))

    def test_document_paths_links_and_descriptions_follow_added_and_removed_sources(self):
        pages = {"nested/future.md": '---\ntitle: Future family\npermalink: /new/location.html\n---\n\nAn unfamiliar representation.\n\n```mermaid\nfutureStart-v19\n```\n',
                 "old.md": "# Old\n\nOld description."}
        result = catalog.build_markdown(payload(pages), "upstream")
        self.assertIn("https://mermaid.js.org/new/location.html", result)
        self.assertIn("`futureStart-v19`", result)
        self.assertIn("An unfamiliar representation.", result)
        del pages["old.md"]
        pages["nested/future.md"] = pages["nested/future.md"].replace("/new/location.html", "/changed.html")
        changed = catalog.build_markdown(payload(pages), "upstream")
        self.assertNotIn("Old description", changed)
        self.assertNotIn("/new/location.html", changed)
        self.assertIn("/changed.html", changed)

    def test_sidebar_links_are_discovered_and_unpublished_pages_get_pinned_sources(self):
        revision = "a" * 40
        self.assertEqual(catalog.page_link("nest/Topic.md", "", "{link: '/syntax/nest/Topic.html'}", revision), "https://mermaid.js.org/syntax/nest/Topic.html")
        self.assertEqual(catalog.page_link("nest/new.md", "", "", revision), f"https://github.com/mermaid-js/mermaid/blob/{revision}/{catalog.DOCS_PATH}/nest/new.md")
        self.assertNotIn("evil.example", catalog.page_link("new.md", "---\nurl: https://evil.example\n---", "", revision))

    def test_registry_and_ambiguity_are_visible_without_hints(self):
        pages = {"a.md": "# A\n\nDescription A.\n\n```mermaid\nnewA\n```\n", "b.md": "# B\n\nDescription B.\n\n```mermaid\nnewB\n```\n"}
        with patch.object(catalog, "bundled_registry", return_value=["future", "unmatched"]), patch.object(catalog, "run_node", return_value={"newA": "future", "newB": "future"}):
            result = catalog.build_markdown(payload(pages))
            self.assertIn("Several documentation topics", result)
            self.assertIn("| `unmatched` | No matching", result)
            self.assertIn("a.md", result)
            self.assertIn("b.md", result)
            enriched = catalog.build_markdown(payload(pages), hints={"future": "a.md"})
            self.assertIn("| `future` | Description A.", enriched)
            self.assertIn("## Additional upstream documentation", enriched)

    def test_actual_registry_entries_remain_recoverable_without_fixed_count(self):
        upstream = catalog.load_offline_upstream(REPO / "packaging/sources/mermaid/upstream.json")
        registry = catalog.bundled_registry()
        self.assertTrue(registry)
        result = catalog.build_markdown(upstream)
        for entry in registry:
            self.assertIn("| " + catalog.markdown_code(catalog.md_cell(entry)) + " |", result)
        self.assertIn("Packaged renderer: **Mermaid", result)
        self.assertIn("Starter observations", result)
        self.assertNotIn("Packaged renderer:", catalog.build_markdown(upstream, "upstream"))
        self.assertEqual(result, catalog.build_markdown(upstream))

    def test_frontmatter_and_comments_do_not_replace_documented_starters(self):
        source = "---\nconfig: {}\n---\n%% comment\nnewFuture type\n"
        self.assertEqual(catalog.fixture_starter(source, ""), "newFuture")

    def test_missing_descriptions_are_explicit(self):
        result = catalog.build_markdown(payload({"empty.md": "# Empty\n\n```mermaid\nfresh\n```\n"}), "upstream")
        self.assertIn("Description unavailable", result)
        self.assertIn("`fresh`", result)

    def test_incomplete_and_empty_captures_preserve_the_reference(self):
        good = payload({"a.md": "# A\n\nA description.", "b.md": "# B\n\nB description."})
        for pages in [{}, {"a.md": good["pages"]["a.md"]}, None]:
            self.fixture.write_text(json.dumps({**good, "pages": pages}))
            self.output.write_text("accepted reference")
            code, _, error = self.call("--write", "--profile", "upstream", "--upstream-fixture", str(self.fixture), "--output", str(self.output))
            self.assertEqual(code, 2)
            self.assertIn("error:", error)
            self.assertEqual(self.output.read_text(), "accepted reference")

    def test_upstream_failure_and_registry_timeout_preserve_accepted_bytes(self):
        self.output.write_text("accepted")
        with patch.object(catalog, "fetch", side_effect=catalog.CatalogError("upstream unavailable")):
            self.assertEqual(self.call("--write", "--fetch", "--output", str(self.output))[0], 2)
        self.fixture.write_text(json.dumps(payload()))
        with patch.object(catalog, "bundled_registry", side_effect=subprocess.TimeoutExpired("node", 30)):
            code, _, error = self.call("--write", "--upstream-fixture", str(self.fixture), "--output", str(self.output))
            self.assertEqual(code, 2)
            self.assertIn("timed out", error)
            self.assertNotIn("Traceback", error)
        self.assertEqual(self.output.read_text(), "accepted")

    def test_live_nested_capture_can_replay_offline(self):
        commit = "2" * 40
        pages = {"a.md": "# A\n\nA definition.", "nested/b.md": "# B\n\n> A different definition."}
        calls = []
        def fetch(url):
            calls.append(url)
            if url.endswith("/commits/" + catalog.UPSTREAM_BRANCH):
                return json.dumps({"sha": commit}).encode()
            if "/contents/" in url:
                entries = [{"name": "b.md", "type": "file"}] if "/nested?" in url else [{"name": "a.md", "type": "file"}, {"name": "nested", "type": "dir"}]
                self.assertIn("ref=" + commit, url)
                return json.dumps(entries).encode()
            self.assertIn(commit, url)
            if url.endswith(catalog.SIDEBAR_PATH):
                return b"{link: '/syntax/a'}"
            return pages[url.split(catalog.DOCS_PATH + "/", 1)[1]].encode()
        with patch.object(catalog, "fetch", side_effect=fetch):
            code, _, error = self.call("--snapshot-only", "--fetch", "--save-upstream", str(self.fixture))
            self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(self.fixture.read_text())["pages"], pages)
        with patch.object(catalog, "fetch", side_effect=AssertionError("offline calls network")):
            self.assertEqual(self.call("--write", "--profile", "upstream", "--upstream-fixture", str(self.fixture), "--output", str(self.output))[0], 0)
            self.assertEqual(self.call("--check", "--profile", "upstream", "--upstream-fixture", str(self.fixture), "--output", str(self.output))[0], 0)

    def test_capture_and_input_collision_protect_original_bytes(self):
        self.fixture.write_text(json.dumps(payload()))
        before = self.fixture.read_bytes()
        with patch.object(catalog, "fetch", side_effect=AssertionError("network before refusal")):
            self.assertEqual(self.call("--snapshot-only", "--fetch", "--save-upstream", str(self.fixture))[0], 2)
        self.assertEqual(self.call("--write", "--upstream-fixture", str(self.fixture), "--output", str(self.fixture))[0], 2)
        self.assertEqual(self.fixture.read_bytes(), before)

    def test_broken_paths_metadata_and_registry_are_rejected(self):
        for names in [["../escape.md"], ["same.md", "same.md"], []]:
            with self.assertRaises(catalog.CatalogError):
                catalog.validate_docs(names)
        with patch.object(catalog, "run_node", return_value=["duplicate", "duplicate"]):
            with self.assertRaises(catalog.CatalogError):
                catalog.bundled_registry()

    def test_unsafe_text_cannot_inject_table_markup(self):
        result = catalog.build_markdown(payload({"hostile.md": "---\ntitle: 'A | B <script>'\ndescription: '<img src=x onerror=y> | evidence'\n---\n"}), "upstream")
        self.assertNotIn("<script>", result)
        self.assertNotIn("<img", result)
        self.assertIn(r"\| evidence", result)


if __name__ == "__main__":
    unittest.main()
