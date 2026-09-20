"""Navigation markup remains a complete, safe document before optional hydration."""
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class WorkspacePresentationTests(unittest.TestCase):
    def test_identity_escaping_and_complete_no_script_document(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required")
        self.assertIsNotNone(tsc, "TypeScript is required")
        with tempfile.TemporaryDirectory(prefix="av-workspace-view-") as tmp:
            result = subprocess.run([tsc, "--strict", "--target", "ES2020", "--module", "commonjs", "--rootDir", str(ROOT), "--outDir", tmp, str(ROOT / "src/index.ts")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            code = r'''
const assert = require('node:assert/strict');
const {evidenceWorkspace, reportSurface, reportSection, sectionGroup, appearanceSettings, annotatedTable} = require(process.argv[1]);
const input = { id: 'inspection', title: '<img src=x onerror=run()>',
  description: 'A & B', views: [
    {id: 'a', label: 'Same label', body: '<p>Failure remains in the document.</p>'},
    {id: 'a--heading', label: 'Same label', body: '<p>Missing remains missing.</p>'},
    {id: 'search-status', label: '</a><script>run()</script>', body: '<p>Third observation.</p>'}
  ]};
const result = evidenceWorkspace(input);
assert(!result.includes('<script>'));
assert(result.includes('&lt;img src=x onerror=run()&gt;'));
assert(result.includes('&lt;/a&gt;&lt;script&gt;run()&lt;/script&gt;'));
assert(result.includes('A &amp; B'));
assert(result.includes('Failure remains in the document.'));
assert(result.includes('Missing remains missing.'));
assert.throws(() => evidenceWorkspace({...input, views: [input.views[0], input.views[0]]}), /unique/);
assert.throws(() => evidenceWorkspace({...input, id: 'bad" id'}), /Workspace ID/);
assert.throws(() => evidenceWorkspace({...input, views: [{...input.views[0], icon: 'toString'}]}), /Unknown workspace icon/);
assert.throws(() => evidenceWorkspace({...input, views: [{...input.views[0], label: ''}]}), /nonempty label/);
assert.throws(() => evidenceWorkspace({...input, title: ''}), /nonempty workspace title/);

assert.throws(() => evidenceWorkspace({...input, startView:'absent'}), /starting view/);
assert.throws(() => evidenceWorkspace({...input, journeys:[{id:'read',label:'Read',viewIds:['a','absent']}]}), /supplied views/);
assert.throws(() => evidenceWorkspace({...input, journeys:[{id:'read',label:'Read',viewIds:['a','a']}]}), /distinct/);
assert.throws(() => evidenceWorkspace({...input, storageKey:'collision',notebook:{revision:'v1',storageKey:'collision'}}), /different storage keys/);
const routed = evidenceWorkspace({...input, startView:'a--heading',palette:'ocean',canvas:'plain',journeys:[{id:'read',label:'Read <script>',viewIds:['a','a--heading']}],notebook:{revision:'v1'}});
assert(routed.includes('data-av-start-view="a--heading"'));
assert(routed.includes('Read &lt;script&gt;'));
assert(routed.includes('data-av-journey-steps="[&quot;a&quot;,&quot;a--heading&quot;]"'));
assert(routed.includes('data-av-notebook-scope="inspection"'));
assert(!routed.includes('data-av-notebook-storage-key'));
assert.throws(() => reportSurface({id:'safe',palette:'random',body:''}), /indigo, ocean, graphite/);
assert.throws(() => reportSurface({id:'safe',canvas:'custom',body:''}), /ambient, plain/);
const identified = reportSection({id:'original-finding',title:'Stable anchor',body:'<p>Evidence</p>'});
assert(identified.includes('id="original-finding"'));
assert.throws(() => reportSection({id:'bad id',title:'Anchor',body:''}), /presentation ID/);

const {reportBrief} = require(process.argv[1]);
const colors = {main:'#ffff00',secondary:'#008090',tertiary:'#df4488'};
const custom = reportSurface({id:'custom-colors',customColors:colors,body:'<p>Context</p>'});
assert(custom.includes('data-av-palette="custom"'));
assert(custom.includes('--av-brand-main:#ffff00'));
assert.throws(() => reportSurface({id:'unsafe-colors',body:'',customColors:{...colors,main:'red; background:url(bad)'}}), /six-digit hex/);
const opening = {question:'Which choice meets the original task? <script>',paragraphs:['A literal & original condition.'],facts:[{label:'Scope',text:'Only the supplied cases'}],finding:'Adequate with the stated condition',body:'<p>Additional authored explanation.</p>'};
const oriented = evidenceWorkspace({...input,brief:opening,journeys:[{id:'read',label:'Read',viewIds:['a']}]});
assert(oriented.indexOf('Which choice') < oriented.indexOf('Where would you like'));
assert(oriented.indexOf('Which choice') < oriented.indexOf('av-workspace-layout'));
assert(oriented.indexOf('av-workspace-bar') < oriented.indexOf('av-report-brief'), 'Report utilities remain reachable above the introduction');
assert(oriented.includes('&lt;script&gt;')); assert(!oriented.includes('<script>'));
assert(oriented.includes('Additional authored explanation.'));
assert.throws(() => reportBrief({question:'   '}), /actual question/);
assert.throws(() => reportBrief({question:'An actual question', id:''}), /presentation ID/);
assert.throws(() => reportSurface({id:'bad-palette',palette:'',body:''}), /Unknown palette/);
assert.throws(() => reportBrief({question:[{text:'',strong:true}]}), /actual question/);
assert(!reportBrief({question:'A narrow question'}).includes('What the evidence supports'));

const section = reportSection({ title: '<svg/onload=bad()>', open: false, body: '<p>Original finding</p>' });
assert(section.startsWith('<details'));
assert(section.includes('data-av-section'));
assert(!section.match(/^<details[^>]*\sopen[ >]/));
assert(section.includes('&lt;svg/onload=bad()&gt;'));
assert(section.includes('<p>Original finding</p>'));
const plain = annotatedTable({ title: 'Plain fragment', collapsible: false, columns: ['Value'], rows: [[{value: 0}], [{value: null}]] });
assert(plain.startsWith('<section')); assert(!plain.includes('data-av-section')); assert(plain.includes('Missing'));
const group = sectionGroup({ mode: 'solo', body: section + plain });
const left = reportSurface({ id: 'left', theme: 'dark', spacing: 'compact', sections: 'solo', body: appearanceSettings({id:'left-settings'}) + group });
const right = reportSurface({ id: 'right', theme: 'light', body: appearanceSettings({id:'right-settings'}) + plain });
assert(left.includes('data-av-theme="dark"')); assert(left.includes('data-av-spacing="compact"')); assert(left.includes('data-av-section-mode="solo"'));
assert(right.includes('data-av-theme="light"'));
assert(!left.includes('data-av-workspace')); assert(!right.includes('data-av-workspace'));
assert(left.includes('name="left-settings-theme"')); assert(right.includes('name="right-settings-theme"'));
assert(!left.includes('left-settings-theme" value="light" data-av-setting="theme" onclick'));
assert.throws(() => reportSurface({id:'invalid id', body:''}), /presentation ID/);
assert.throws(() => reportSurface({id:'valid', theme:'blue', body:''}), /system, light, dark/);
assert.throws(() => reportSurface({id:'valid', spacing:'tiny', body:''}), /comfortable, compact/);
assert.throws(() => sectionGroup({body:'', mode:'forced'}), /multiple or solo/);
assert.throws(() => appearanceSettings({id:'bad id'}), /presentation ID/);
assert.throws(() => reportSection({title:'x', body:null}), /body/);
process.stdout.write(JSON.stringify(result + left + right));
'''
            result = subprocess.run([node, "-e", code, str(Path(tmp) / "src/index.js")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            document = Document(json.loads(result.stdout))
        ids = [attrs["id"] for _, attrs in document.tags if "id" in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        panels = [attrs for _, attrs in document.tags if "data-av-panel" in attrs]
        self.assertEqual(len(panels), 3)
        self.assertTrue(all("hidden" not in attrs for attrs in panels))
        for tag, attrs in document.tags:
            if "data-av-view" in attrs:
                self.assertEqual(tag, "a")
                self.assertIn(attrs["href"][1:], ids)
            if "data-av-script-only" in attrs:
                self.assertIn("hidden", attrs)
            if "aria-labelledby" in attrs:
                self.assertIn(attrs["aria-labelledby"], ids)


if __name__ == "__main__":
    unittest.main()
