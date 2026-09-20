"""Adopted package and delivery contracts; no semantic skill-quality grading."""
from __future__ import annotations

import base64
import hashlib
from html.parser import HTMLParser
import json
import os
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


class VisualConsumerHTML(HTMLParser):
    """Inspect delivered content and embedded bytes, without a browser DOM."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.scripts = []
        self.rows = []
        self._script = None
        self._row = None
        self._cell = None
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.tags.append((tag, attrs))
        if tag == 'script':
            self._script = {'attributes': attrs, 'text': ''}
            self.scripts.append(self._script)
        elif tag == 'tr':
            self._row = []
        elif tag in {'th', 'td'} and self._row is not None:
            self._cell = []

    def handle_data(self, value):
        if self._script is not None:
            self._script['text'] += value
        if self._cell is not None:
            self._cell.append(value)

    def handle_endtag(self, tag):
        if tag == 'script':
            self._script = None
        elif tag in {'th', 'td'} and self._cell is not None:
            self._row.append(''.join(self._cell).strip())
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            self.rows.append(self._row)
            self._row = None


class AgenticPackageTests(unittest.TestCase):
    def exercise_converted_visual_consumer(self, staged, cwd, expected_assets):
        """Use the converted runtime/exporter; no compilation or source imports."""
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for converted visual consumer checks')
        visuals = staged / 'skills/split-testing/assets/visuals'
        self.assertFalse(cwd.is_relative_to(staged))
        for relative, expected in expected_assets.items():
            self.assertEqual((visuals / relative).read_bytes(), expected, f'{staged.name}: {relative}')
        work = cwd / ('visual-consumer-' + staged.name)
        work.mkdir()
        hostile = '</script><img data-injected="yes" src="https://invalid.example/" onerror="bad()"><script>globalThis.corrupted=true</script> & λ'
        evidence = {
            'title': 'Converted consumer evidence',
            'columns': ['Observation', 'Zero', 'Decimal', 'Missing', 'Exact identifier'],
            'rows': [[{'value': hostile}, {'value': 0}, {'value': -12.375},
                      {'value': None}, {'value': '9007199254740993'}]],
        }
        data = work / 'evidence.json'
        data.write_text(json.dumps(evidence, ensure_ascii=False), encoding='utf-8')
        render = work / 'render.cjs'
        render.write_text('''const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const [bundle, data, output] = process.argv.slice(2);
const context = vm.createContext({});
context.window = context;
vm.runInContext(fs.readFileSync(bundle, 'utf8'), context, {timeout: 5000});
assert.equal(typeof context.AgenticVisuals.annotatedTable, 'function');
const markup = context.AgenticVisuals.annotatedTable(JSON.parse(fs.readFileSync(data, 'utf8'))) + context.AgenticVisuals.mermaidDiagram({id:'packaged-diagram',title:'Source to outcome',source:'flowchart LR\\n  A[Original α] --> B[Observed outcome]'});
assert.equal(typeof markup, 'string');
assert.equal(context.corrupted, undefined);
fs.writeFileSync(output, markup);
''', encoding='utf-8')
        markup_file = work / 'rendered.html'
        proc = subprocess.run([node, str(render), str(visuals / 'dist/agentic-visuals.js'),
                               str(data), str(markup_file)], cwd=cwd, text=True,
                              capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        markup = markup_file.read_text(encoding='utf-8')
        body = work / 'body.html'
        body.write_text('<main class="av-report"><div id="consumer-report">' + markup +
                        '</div><img id="consumer-mark" alt="Embedded marker" '
                        'src="{{asset:marker}}"></main>', encoding='utf-8')
        marker_bytes = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1"/></svg>'
        marker = work / 'marker.svg'
        marker.write_bytes(marker_bytes)
        composition = work / 'compose.js'
        composition.write_text('''const evidence = JSON.parse(document.getElementById('report-data').textContent);
document.getElementById('consumer-report').innerHTML = AgenticVisuals.annotatedTable(evidence);
''', encoding='utf-8')
        output = work / 'standalone.html'
        proc = subprocess.run([sys.executable, str(visuals / 'assemble.py'),
            '--body', str(body), '--style', str(visuals / 'styles/agentic-visuals.css'),
            '--script', str(visuals / 'dist/agentic-visuals.js'), '--data', 'report-data=' + str(data),
            '--script', str(composition), '--asset', 'marker=' + str(marker), '--output', str(output)],
            cwd=cwd, text=True, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        document = VisualConsumerHTML(output.read_text(encoding='utf-8'))

        def embedded(value):
            header, separator, payload = value.partition(',')
            self.assertTrue(separator and header.startswith('data:') and header.endswith(';base64'), header)
            return base64.b64decode(payload, validate=True)

        data_blocks = [script for script in document.scripts
                       if script['attributes'].get('type') == 'application/json']
        by_id = {block['attributes']['id']: block for block in data_blocks}
        self.assertEqual(set(by_id), {'report-data', 'av-report-recipe', 'av-mermaid-notices'})
        data_blocks = [by_id['report-data']]
        self.assertEqual(json.loads(by_id['av-report-recipe']['text'])['scripts'], ['av-script-0', 'av-script-1', 'av-script-2'])
        self.assertEqual(json.loads(data_blocks[0]['text']), evidence)
        scripts = [embedded(script['attributes']['src']) for script in document.scripts
                   if script['attributes'].get('type') != 'application/json']
        self.assertEqual(scripts, [expected_assets['vendor/mermaid/mermaid.min.js'], expected_assets['dist/agentic-visuals.js'], composition.read_bytes()])
        styles = [embedded(attrs['href']) for tag, attrs in document.tags
                  if tag == 'link' and attrs.get('rel') == 'stylesheet']
        self.assertEqual(styles, [expected_assets['styles/agentic-visuals.css']])
        images = [attrs for tag, attrs in document.tags if tag == 'img']
        self.assertEqual(len(images), 1, 'untrusted text must not introduce an image element')
        self.assertEqual(images[0].get('id'), 'consumer-mark')
        self.assertEqual(embedded(images[0]['src']), marker_bytes)
        for _, attrs in document.tags:
            self.assertNotIn('data-injected', attrs)
            self.assertFalse(any(name.startswith('on') for name in attrs))
            for name in ('src', 'href', 'poster'):
                if name in attrs:
                    self.assertTrue(attrs[name].startswith(('data:', '#')), attrs[name])
        policy = [attrs['content'] for tag, attrs in document.tags
                  if tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy']
        self.assertEqual(len(policy), 1)
        self.assertIn("connect-src 'none'", policy[0])

        expected_row = [hostile, '0', '-12.375', 'Missing', '9007199254740993']
        self.assertIn(expected_row, document.rows)
        # Replay only bytes recovered from the final HTML, supplying the tiny
        # data/target interface the composition uses. This is not a browser DOM.
        replay_input = work / 'replay.json'
        replay_input.write_text(json.dumps({'scripts': [script.decode('utf-8') for script in scripts],
                                           'data': data_blocks[0]['text']}), encoding='utf-8')
        replay = work / 'replay.cjs'
        replay.write_text('''const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const report = {innerHTML: ''};
const context = vm.createContext({document: {getElementById(id) {
  if (id === 'report-data') return {textContent: input.data};
  if (id === 'consumer-report') return report;
  throw new Error('unexpected document lookup: ' + id);
}}});
// Registering load handlers does not invoke rendering in this source replay.
context.window = {addEventListener() {}};
context.structuredClone = structuredClone;
for (const script of input.scripts) vm.runInContext(script, context, {timeout: 5000});
assert.equal(context.corrupted, undefined);
process.stdout.write(report.innerHTML);
''', encoding='utf-8')
        proc = subprocess.run([node, str(replay), str(replay_input)], cwd=cwd,
                              text=True, capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        replayed = VisualConsumerHTML(proc.stdout)
        self.assertIn(expected_row, replayed.rows)
        self.assertFalse(any(tag == 'script' or 'data-injected' in attrs for tag, attrs in replayed.tags))

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
        visual_root = PLUGIN / 'skills/split-testing/assets/visuals'
        visual_assets = {relative: (visual_root / relative).read_bytes()
                         for relative in ('dist/agentic-visuals.js', 'styles/agentic-visuals.css', 'assemble.py', 'vendor/mermaid/mermaid.min.js', 'vendor/mermaid/integrity.json', 'vendor/mermaid/LICENSE', 'vendor/mermaid/NOTICE.md')}
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
            self.assertFalse(source.exists())
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

                    # Exercise the optional helper from the converted package,
                    # with neither the source copy nor the repository cwd.
                    native_tmp = root / ('participant-temp-' + staged.name)
                    native_tmp.mkdir()
                    spec = cwd / ('batch-' + staged.name + '.json')
                    spec.write_text(json.dumps({
                        'inputs': {'package': {'source': str(staged), 'destination': 'package'}},
                        'groups': [{'id': 'consumer', 'count': 1, 'inputs': ['package'],
                                    'outputs': ['findings.md']}],
                    }))
                    helper = staged / 'skills/split-testing/scripts/prepare_workspaces.py'
                    proc = subprocess.run([sys.executable, str(helper), '--run-root',
                        str(root / ('batch-' + staged.name)), '--spec', str(spec)],
                        cwd=cwd, text=True, capture_output=True,
                        env={**os.environ, 'TMPDIR': str(native_tmp), 'TEMP': str(native_tmp),
                             'TMP': str(native_tmp), 'PYTHONDONTWRITEBYTECODE': '1'})
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    result = json.loads(proc.stdout)
                    self.assertEqual(result['preparation_status'], 'ready')
                    self.assertEqual(len(result['participants']), 1)
                    participant = result['participants'][0]
                    copied = Path(participant['inputs']['package'])
                    for relative, digest in masters.items():
                        self.assertEqual(hashlib.sha256((copied / relative).read_bytes()).hexdigest(), digest)
                    self.assertFalse(Path(participant['expected_outputs'][0]).exists())
                    self.assertTrue(Path(result['manifest']).is_file())
                    self.exercise_converted_visual_consumer(staged, cwd, visual_assets)

    def test_reporters_have_one_executable_implementation_and_clean_text(self):
        scripts = PLUGIN / 'skills/skill-auditor/scripts'
        for name in ('frontmatter_check.sh', 'reference_check.sh', 'script_sanity.sh', 'plugin_check.sh'):
            path = scripts / name
            self.assertTrue(path.stat().st_mode & 0o111)
            self.assertTrue(path.read_bytes().startswith(b'#!/usr/bin/env sh\n'))
        for path in PLUGIN.rglob('*'):
            if path.is_file() and path.suffix in {'.md', '.sh', '.py', '.json', '.yaml', '.yml', '.ts', '.js', '.mjs', '.css', '.html'}:
                self.assertNotIn(b'\r', path.read_bytes(), str(path))

    def test_repository_entry_resolves_canonical_charter(self):
        agents = (REPO / 'AGENTS.md').read_text()
        links = re.findall(r'\]\(([^)]+governing-architecture\.md)\)', agents)
        self.assertEqual(len(links), 1)
        self.assertEqual((REPO / links[0]).resolve(), PLUGIN / 'skills/foundational-knowledge/references/governing-architecture.md')


if __name__ == '__main__':
    unittest.main()
