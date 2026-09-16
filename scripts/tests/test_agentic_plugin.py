"""Adopted package and delivery contracts; no semantic skill-quality grading."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

from scripts import plugin_port

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / 'plugins' / 'agentic-design-and-evaluation'
SLUGS = {'prompt-context-design', 'skill-auditor', 'split-testing', 'foundational-knowledge'}
RETIRED = {'skill-auditor', 'split-testing'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


class AgenticPackageTests(unittest.TestCase):
    def test_host_catalogs_and_manifests_deliver_one_identity(self):
        codex = read_json(PLUGIN / '.codex-plugin/plugin.json')
        claude = read_json(PLUGIN / '.claude-plugin/plugin.json')
        for key in ('name', 'version', 'description', 'author', 'license'):
            self.assertEqual(codex[key], claude[key])
        self.assertEqual(codex['name'], PLUGIN.name)
        self.assertTrue((PLUGIN / 'LICENSE').is_file())
        for host, path in [('codex', '.agents/plugins/marketplace.json'), ('claude', '.claude-plugin/marketplace.json')]:
            entries = read_json(REPO / path)['plugins']
            self.assertFalse(RETIRED & {e['name'] for e in entries})
            selected = [e for e in entries if e['name'] == PLUGIN.name]
            self.assertEqual(len(selected), 1)
            entry = selected[0]
            source = entry['source']['path'] if host == 'codex' else entry['source']
            self.assertEqual((REPO / source).resolve(), PLUGIN)
            self.assertEqual(entry['description'], codex['interface']['shortDescription'])
            if host == 'claude':
                self.assertEqual(entry['version'], claude['version'])

    def test_four_entries_have_consistent_portable_and_ui_metadata(self):
        roots = {p.parent.name: p for p in (PLUGIN / 'skills').glob('*/SKILL.md')}
        self.assertEqual(set(roots), SLUGS)
        for slug, path in roots.items():
            with self.subTest(skill=slug):
                metadata, body, present, _ = plugin_port.split_frontmatter(path)
                self.assertTrue(present)
                self.assertEqual(metadata['name'], slug)
                self.assertTrue(0 < len(metadata['description']) <= 1024)
                title = re.search(r'^# (.+)$', body, re.M).group(1)
                ui = plugin_port.load_yaml_text((path.parent / 'agents/openai.yaml').read_text(), path=path)
                self.assertEqual(ui['interface']['display_name'], title)
                self.assertTrue(25 <= len(ui['interface']['short_description']) <= 64)
                self.assertIn('$' + slug, ui['interface']['default_prompt'])
                self.assertTrue(ui.get('policy', {}).get('allow_implicit_invocation', True))

    def test_converted_packages_supply_declared_public_resources_without_source_access(self):
        # Discover the public interface from its published links, rather than
        # constructing a private foundation path for every caller. This scan
        # is independent of the bundled reference reporter.
        def local_links(doc):
            links = []
            for raw in re.findall(r'\[[^\]\n]*\]\(([^)]+)\)', doc.read_text()):
                url = urlsplit(raw)
                if not url.scheme and not url.netloc and url.path.endswith('.md'):
                    links.append((doc.parent / unquote(url.path)).resolve())
            return links

        public = [p for p in local_links(PLUGIN / 'README.md')
                  if p.name in {'foundational-knowledge.md', 'governing-architecture.md',
                                'open-standard.md', 'host-contracts.md'}]
        self.assertEqual(len(public), 4)
        public_relative = [p.relative_to(PLUGIN) for p in public]
        masters = {p.relative_to(PLUGIN): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in public if p.name in {'foundational-knowledge.md', 'governing-architecture.md'}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            shutil.copytree(PLUGIN, source)
            cwd = root / 'consumer'
            cwd.mkdir()
            artifacts = []
            for host in ('codex', 'claude'):
                staged = root / host
                proc = subprocess.run([sys.executable, str(REPO / 'scripts/plugin_port.py'),
                    'convert', str(source), '--to', host, '--out', str(staged), '--mode', 'strict',
                    '--summary', 'json'], cwd=cwd, text=True, capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                artifacts.append(staged)
            shutil.rmtree(source)
            for staged in artifacts:
                with self.subTest(host=staged.name):
                    for relative in public_relative:
                        self.assertTrue((staged / relative).is_file())
                    for relative, digest in masters.items():
                        self.assertEqual(hashlib.sha256((staged / relative).read_bytes()).hexdigest(), digest)
                    self.assertEqual((staged / 'LICENSE').read_bytes(), (PLUGIN / 'LICENSE').read_bytes())
                    reached = set()
                    pending = list((staged / 'skills').glob('*/SKILL.md'))
                    while pending:
                        doc = pending.pop().resolve()
                        if doc in reached:
                            continue
                        self.assertTrue(doc.is_relative_to(staged))
                        self.assertTrue(doc.is_file(), str(doc))
                        reached.add(doc)
                        pending.extend(local_links(doc))
                    for relative in public_relative:
                        self.assertIn((staged / relative).resolve(), reached)
                    for command in ('frontmatter_check', 'reference_check', 'script_sanity', 'plugin_check'):
                        entry = staged / 'skills/skill-auditor/scripts' / (command + '.sh')
                        self.assertTrue(entry.stat().st_mode & 0o111)
                        proc = subprocess.run(['sh', str(entry), '--help'], cwd=cwd, text=True, capture_output=True)
                        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_reporters_have_one_executable_implementation_and_clean_text(self):
        scripts = PLUGIN / 'skills/skill-auditor/scripts'
        for name in ('frontmatter_check.sh', 'reference_check.sh', 'script_sanity.sh', 'plugin_check.sh'):
            path = scripts / name
            self.assertTrue(path.stat().st_mode & 0o111)
            self.assertTrue(path.read_bytes().startswith(b'#!/usr/bin/env sh\n'))
        for path in PLUGIN.rglob('*'):
            if path.is_file() and path.suffix in {'.md', '.sh', '.py', '.json', '.yaml'}:
                self.assertNotIn(b'\r', path.read_bytes(), str(path))

    def test_repository_entry_resolves_canonical_charter(self):
        agents = (REPO / 'AGENTS.md').read_text()
        links = re.findall(r'\]\(([^)]+governing-architecture\.md)\)', agents)
        self.assertEqual(len(links), 1)
        self.assertEqual((REPO / links[0]).resolve(), PLUGIN / 'skills/foundational-knowledge/references/governing-architecture.md')


if __name__ == '__main__':
    unittest.main()
