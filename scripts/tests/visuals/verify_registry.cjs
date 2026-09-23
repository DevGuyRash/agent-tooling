#!/usr/bin/env node
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const here = __dirname;
const root = path.resolve(here, '../../..');
const visuals = path.join(root, 'plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals');
const fixtureRoot = process.env.AGENTIC_VISUAL_MERMAID_FIXTURES || path.join(here, 'mermaid-fixtures');
const vendor = fs.readFileSync(path.join(visuals, 'vendor/mermaid/mermaid.min.js'));
const integrity = JSON.parse(fs.readFileSync(path.join(visuals, 'vendor/mermaid/integrity.json'), 'utf8'));
assert.equal(crypto.createHash('sha256').update(vendor).digest('hex'), integrity.artifactSha256);

const context = vm.createContext({ console: {log(){}, warn(){}, error(){}}, structuredClone, setTimeout, clearTimeout });
vm.runInContext(vendor.toString(), context, {timeout: 10000});
const mermaid = context.mermaid;
mermaid.initialize({startOnLoad:false, securityLevel:'strict', deterministicIds:true, deterministicIDSeed:'round2-registry'});
const registry = Array.from(mermaid.getRegisteredDiagramsMetadata(), item => item.id).sort();
const sentinelFamilies = ['---', 'error'];
const actualRegistry = registry.filter(family => !sentinelFamilies.includes(family));
const fixtures = JSON.parse(fs.readFileSync(path.join(fixtureRoot, 'index.json'), 'utf8'));
const diagramFamilies = [...new Set(fixtures.filter(item => item.kind === 'diagram').map(item => item.family))].sort();
assert.deepEqual(diagramFamilies, actualRegistry, 'Fixture families must equal the pinned non-sentinel vendor registry exactly');

const sentinels = fixtures.filter(item => item.kind === 'error/sentinel');
assert.deepEqual(sentinels.map(item => item.family).sort(), ['---', 'error'], 'Retain both historical sentinel sources');
assert(sentinelFamilies.every(family => registry.includes(family)), 'Pinned vendor no longer registers both historical sentinels');
const files = new Set();
for (const fixture of fixtures) {
  assert(!files.has(fixture.file), 'Duplicate fixture filename: ' + fixture.file);
  files.add(fixture.file);
  const filename = path.join(fixtureRoot, fixture.file);
  assert(fs.existsSync(filename), 'Missing fixture file: ' + fixture.file);
  const source = fs.readFileSync(filename, 'utf8');
  assert(source.length > 0, 'Fixture must not be empty: ' + fixture.file);
  assert(['ready','error'].includes(fixture.expectedState), 'Fixture needs explicit expectedState: ' + fixture.file);
  if (fixture.expectedState === 'error') {
    assert(['malformed-source','vendor-renderer-regression','unsupported-family-layout'].includes(fixture.failureKind), 'Classify the expected diagnostic: ' + fixture.file);
    assert.equal(typeof fixture.expectedDiagnostic, 'string', 'Require the exact expected diagnostic, not any failure: ' + fixture.file);
    assert(fixture.expectedDiagnostic.length > 5);
  }
  if (fixture.kind === 'diagram' || fixture.kind === 'layout candidate' || fixture.kind === 'edge/error candidate' || fixture.kind === 'renderer regression') {
    assert.equal(mermaid.detectType(source), fixture.family, 'Exact source detector mismatch: ' + fixture.file);
  }
  if (fixture.kind === 'diagram' && fixture.file !== 'info.mmd') {
    assert(source.split(/\r?\n/).filter(Boolean).length >= 6, 'Registered family fixture is still too small: ' + fixture.file);
    assert(source.length >= 180, 'Registered family fixture needs meaningful richer content: ' + fixture.file);
  }
}
assert(fixtures.some(item => item.layout === 'cose-bilkent' && item.family === 'mindmap' && item.expectedState === 'ready'), 'Demonstrate CoSE-Bilkent on its supported mindmap family');
assert.equal(fixtures.filter(item => item.kind === 'edge/error candidate').length, 4, 'Retain every historical edge/error candidate');
assert.equal(fixtures.filter(item => item.kind === 'renderer regression').length, 1, 'Retain the pinned block-routing renderer regression');
assert.equal(fixtures.filter(item => item.expectedState === 'error').length, 4, 'Intentional native failures changed unexpectedly');
console.log(JSON.stringify({registry, actualFamilies:actualRegistry, fixtureCount: fixtures.length, sentinels: sentinels.map(item => item.file), expectedDiagnostics: fixtures.filter(item=>item.expectedState==='error').map(item=>({file:item.file,kind:item.failureKind,message:item.expectedDiagnostic}))}));
