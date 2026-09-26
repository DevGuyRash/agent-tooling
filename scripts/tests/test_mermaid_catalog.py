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
from urllib.error import HTTPError, URLError

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

    def test_documented_examples_follow_valid_markdown_fence_variations(self):
        source = '~~~~ mermaid-example {title="New"}\nfuture-v7\n~~~~~\n\n````text\n```mermaid\nnot-an-example\n```\n````\n\n``` mermaid\n---\nconfig: {}\n---\nsecond-v9\n```\n'
        examples = list(catalog.documented_examples(source))
        self.assertEqual([catalog.fixture_starter(x, '') for x in examples], ['future-v7', 'second-v9'])

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
        pages = {"a.md": "# A\n\nA definition.", "nested/b.mdx": "# B\n\n> A different definition."}
        docs_path, homepage = "new/docs/syntax", "https://docs.example/mermaid/"
        calls = []
        def fetch(url):
            calls.append(url)
            if url == catalog.UPSTREAM_API:
                return json.dumps({"default_branch": "new/default", "homepage": homepage}).encode()
            if url.endswith("/commits/new%2Fdefault"):
                return json.dumps({"sha": commit}).encode()
            if "/git/trees/" in url:
                self.assertIn(commit, url)
                return json.dumps({"truncated": False, "tree": [{"path": docs_path + "/" + name, "type": "blob"} for name in pages]}).encode()
            if url == homepage:
                return b'<a href="start/">Docs</a>'
            if url == homepage + "start/":
                return b'<a href="../syntax/a.html">A</a>'
            if url.startswith(homepage + "syntax/"):
                return f'<link rel="canonical" href="{url}"><h1>Documented topic</h1>'.encode()
            self.assertIn(commit, url)
            return pages[url.split(docs_path + "/", 1)[1]].encode()
        with patch.object(catalog, "fetch", side_effect=fetch):
            code, _, error = self.call("--snapshot-only", "--fetch", "--save-upstream", str(self.fixture))
            self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(self.fixture.read_text())["pages"], pages)
        saved = json.loads(self.fixture.read_text())
        self.assertEqual(saved["source"]["docs_path"], docs_path)
        self.assertEqual(saved["source"]["default_branch"], "new/default")
        self.assertEqual(saved["published_links"]["nested/b.mdx"], homepage + "syntax/nested/b.html")
        with patch.object(catalog, "fetch", side_effect=AssertionError("offline calls network")):
            self.assertEqual(self.call("--write", "--profile", "upstream", "--upstream-fixture", str(self.fixture), "--output", str(self.output))[0], 0)
            self.assertEqual(self.call("--check", "--profile", "upstream", "--upstream-fixture", str(self.fixture), "--output", str(self.output))[0], 0)
        self.assertIn(homepage + "syntax/nested/b.html", self.output.read_text())
        self.assertIn("/tree/HEAD/new/docs/syntax", self.output.read_text())
        self.assertIn(f"/blob/{commit}/new/docs/syntax/nested/b.mdx", self.output.read_text())

    def test_notices_after_or_adjacent_to_intro_stay_separate(self):
        for gap in ("\n", "\n\n"):
            body = "# Example\n\nA diagram explains the event." + gap + "> **Warning**\n> Syntax may change.\n\n## Syntax\n"
            description, notes = catalog.page_introduction(body)
            self.assertEqual(description, "A diagram explains the event.")
            self.assertEqual(notes, ["**Warning** Syntax may change."])
            result = catalog.build_markdown(payload({"example.md": body}), "upstream")
            row = next(line for line in result.splitlines() if line.startswith("| Example |"))
            self.assertNotIn("Warning", row)
            self.assertIn("**Warning** Syntax may change.", result)
        description, notes = catalog.page_introduction('# Topic\n\n> An explanatory description.\n>\n> **Warning**\n> Syntax may change.\n')
        self.assertEqual(description, 'An explanatory description.')
        self.assertEqual(notes, ['**Warning** Syntax may change.'])

    def test_nested_fences_do_not_turn_code_into_prose(self):
        body = "# Example\n\n````text\n```\nmisleading description\n````\n\nActual description.\n"
        self.assertEqual(catalog.page_description(body), "Actual description.")

    def test_description_excerpt_keeps_complete_sentence_and_identifier(self):
        body = "# Example\n\nA diagram describes an a_b relationship. Additional background with [a relative link](../other.md).\n"
        self.assertEqual(catalog.description_excerpt(body), "A diagram describes an a_b relationship.")
        self.assertEqual(catalog.description_excerpt('# Topic\n\n"A full sentence. More source prose follows." Attribution'), '"A full sentence."')
        self.assertEqual(catalog.page_description('# Topic\n\n![Banner](image.svg)\n\nA useful explanation.'), 'A useful explanation.')

    def test_relative_notice_links_travel_with_the_generated_reference(self):
        snapshot=payload({'nested/future.md':'# Future\n\nA description.\n\n> **Warning**\n> Read [the contract](../contract.md).\n'})
        result=catalog.build_markdown(snapshot,'upstream')
        self.assertNotIn('](../contract.md)',result)
        self.assertIn('/blob/'+('1'*40)+'/'+catalog.DOCS_PATH+'/contract.md',result)

    def test_published_links_reject_soft_404s_and_external_canonicals(self):
        docs = ["new.md", "missing.md", "moved.md", "external.md"]
        routes = ["https://docs.example/syntax/new.html"]
        def fetch(url):
            if url.endswith('/missing.html'):
                raise catalog.MissingResource('HTTP 404')
            if url.endswith('/moved.html'):
                return b'<link rel="canonical" href="/index.html"><h1>Welcome</h1>'
            if url.endswith('/external.html'):
                return b'<link rel="canonical" href="https://elsewhere.example/syntax/external.html"><h1>External</h1>'
            return b'<link rel="canonical" href="/syntax/new.html"><h1>New diagram</h1>'
        with patch.object(catalog, "fetch", side_effect=fetch):
            links = catalog.discover_published_links(docs, {name: '# Topic' for name in docs}, 'https://docs.example/', routes)
        self.assertEqual(links, {'new.md': routes[0], 'missing.md': None, 'moved.md': None, 'external.md': None})

    def test_truncated_upstream_tree_preserves_accepted_output(self):
        responses = [json.dumps({'default_branch': 'main', 'homepage': 'https://docs.example/'}).encode(),
                     json.dumps({'sha': 'a'*40}).encode(), json.dumps({'truncated': True, 'tree': []}).encode()]
        self.output.write_text('accepted')
        with patch.object(catalog, 'fetch', side_effect=responses):
            code, _, error = self.call('--write', '--fetch', '--output', str(self.output))
        self.assertEqual(code, 2)
        self.assertIn('incomplete', error)
        self.assertEqual(self.output.read_text(), 'accepted')

    def test_empty_document_and_registry_are_rejected(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_pages({'empty.md':'  '}, ['empty.md'])
        with patch.object(catalog, 'run_node', return_value=[]), self.assertRaises(catalog.CatalogError):
            catalog.bundled_registry()

    def test_output_and_snapshot_symlinks_are_refused_before_fetch(self):
        self.output.write_text('accepted')
        link = self.root/'link';link.symlink_to(self.output)
        with patch.object(catalog, 'fetch', side_effect=AssertionError('network before refusal')):
            self.assertEqual(self.call('--write','--fetch','--output',str(link))[0], 2)
            self.assertEqual(self.call('--snapshot-only','--fetch','--save-upstream',str(link))[0], 2)
        self.assertEqual(self.output.read_text(), 'accepted')

    def test_retry_is_bounded_and_honors_backoff(self):
        response = io.BytesIO(b'complete')
        busy = HTTPError('https://example.test', 429, 'busy', {'Retry-After':'2'}, None)
        with patch.object(catalog, 'urlopen', side_effect=[busy, response]) as request, patch.object(catalog.time, 'sleep') as sleep:
            self.assertEqual(catalog.fetch('https://example.test'), b'complete')
            self.assertEqual(request.call_count, 2)
            sleep.assert_called_once_with(2)
        with patch.object(catalog, 'urlopen', side_effect=URLError('unavailable')) as request, patch.object(catalog.time, 'sleep'):
            with self.assertRaises(catalog.CatalogError):catalog.fetch('https://example.test')
            self.assertEqual(request.call_count, 3)
        long_wait = HTTPError('https://example.test', 429, 'busy', {'Retry-After':'90'}, None)
        with patch.object(catalog, 'urlopen', side_effect=long_wait) as request, patch.object(catalog.time, 'sleep') as sleep:
            with self.assertRaises(catalog.CatalogError):catalog.fetch('https://example.test')
            self.assertEqual(request.call_count, 1);sleep.assert_not_called()

    def test_large_response_is_refused_without_retry(self):
        with patch.object(catalog, 'MAX_RESPONSE_BYTES', 8), patch.object(catalog, 'urlopen', return_value=io.BytesIO(b'123456789')) as request:
            with self.assertRaises(catalog.CatalogError):catalog.fetch('https://example.test')
            self.assertEqual(request.call_count, 1)

    def test_document_source_is_selected_by_its_site_config(self):
        paths = ['docs/syntax/generated.md', 'moved/docs/syntax/source.md', 'moved/docs/.vitepress/config.mts']
        def fetch(url):
            if url == catalog.UPSTREAM_API:return json.dumps({'default_branch':'next', 'homepage':'https://docs.example/'}).encode()
            if '/commits/' in url:return json.dumps({'sha':'b'*40}).encode()
            if '/git/trees/' in url:return json.dumps({'truncated':False,'tree':[{'path':path,'type':'blob'} for path in paths]}).encode()
            if url.endswith('config.mts'):return b'export default {}'
            self.assertTrue(url.endswith('moved/docs/syntax/source.md'))
            return b'# Source\n\nThe maintained source.'
        with patch.object(catalog,'fetch',side_effect=fetch), patch.object(catalog,'published_navigation',return_value=('https://docs.example/','<nav/>',[])), patch.object(catalog,'discover_published_links',return_value={'source.md':None}):
            actual=catalog.load_live_upstream()
        self.assertEqual(actual['docs'],['source.md'])
        rendered=catalog.build_markdown(actual,'upstream')
        self.assertIn('/blob/HEAD/moved/docs/syntax/source.md',rendered)
        self.assertIn('/blob/'+('b'*40)+'/moved/docs/syntax/source.md',rendered)

    def test_published_fetch_failure_does_not_downgrade_the_reference(self):
        with patch.object(catalog,'fetch',side_effect=catalog.CatalogError('service unavailable')):
            with self.assertRaises(catalog.CatalogError):
                catalog.discover_published_links(['new.md'],{'new.md':'# New'},'https://docs.example/',['https://docs.example/syntax/new.html'])

    def test_registry_diagnostics_do_not_dump_minified_source_or_stack(self):
        response=subprocess.CompletedProcess([],1,'','long minified source\nTypeError: registry interface changed\n    at function.js:1:20\n')
        with patch.object(catalog.subprocess,'run',return_value=response), patch.object(catalog.shutil,'which',return_value='/node'):
            with self.assertRaises(catalog.CatalogError) as raised:catalog.run_node('source')
        self.assertIn('registry interface changed',str(raised.exception))
        self.assertNotIn('minified',str(raised.exception))
        self.assertNotIn('function.js',str(raised.exception))

    def test_offline_cli_runs_from_an_unrelated_working_directory(self):
        self.fixture.write_text(json.dumps(payload()))
        cmd = [sys.executable, str(REPO/'scripts/update_mermaid_catalog.py'), '--write', '--profile', 'upstream', '--upstream-fixture', str(self.fixture), '--output', str(self.output)]
        process = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('newFamily-v4', self.output.read_text())
        before = self.output.read_bytes()
        process = subprocess.run([*cmd[:2], '--check', *cmd[3:]], cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.output.read_bytes(), before)

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
