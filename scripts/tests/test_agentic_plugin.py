"""Adopted package and delivery contracts; no semantic skill-quality grading."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

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

    def test_staged_package_preserves_current_master_without_source_access(self):
        originals = PLUGIN / 'skills/foundational-knowledge/references'
        expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals.glob('*.md')}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            staged = root / 'installed'
            shutil.copytree(PLUGIN, source)
            shutil.copytree(source, staged)
            shutil.rmtree(source)
            cwd = root / 'consumer'
            cwd.mkdir()
            reporter = staged / 'skills/skill-auditor/scripts/reference_check.sh'
            for slug in sorted(SLUGS):
                entry = staged / 'skills' / slug
                for name, digest in expected.items():
                    relative = Path('references') / name if slug == 'foundational-knowledge' else Path('../foundational-knowledge/references') / name
                    target = (entry / relative).resolve()
                    self.assertTrue(target.is_relative_to(staged))
                    self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest)
                proc = subprocess.run(['sh', str(reporter), str(entry), '--format', 'json'], cwd=cwd, text=True, capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(json.loads(proc.stdout)['error_count'], 0)

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
