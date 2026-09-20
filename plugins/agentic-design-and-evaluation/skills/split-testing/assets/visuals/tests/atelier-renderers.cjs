/* Fixtures exercise the actual renderer/runtime hook boundary without a browser. */
const assert = require('node:assert/strict');
const path = require('node:path');
const V = require(path.join(process.argv[2], 'src/index.js'));
const E = require(path.join(process.argv[2], 'src/explorers.js'));

const evidence = [{ label: 'Retained <source>', href: '#evidence', note: 'Scope of the native record' }];
const matrix = { id: 'matrix-anchor', title: 'Explicit requirements', alternatives: [{ id: 'first', label: 'Repeated label', note: 'First identity', evidence }, { id: 'second', label: 'Repeated label', note: 'Second identity' }], dimensions: [{ id: 'must', label: 'Required', note: 'Actual requirement', evidence }, { id: 'other-must', label: 'Required', note: 'Different requirement' }], findings: [{ alternative: 'first', dimension: 'must', value: 'Only in the stated condition', status: 'conditional', note: 'Conditional finding', evidence }, { alternative: 'second', dimension: 'other-must', value: null, status: 'missing', note: 'Unobserved outcome' }], limitations: ['No results outside the retained case'] };
const graph = { title: 'Retained relationships', nodes: [{ id: 'prior', label: 'Output', kind: 'observation', detail: 'Earlier run', evidence }, { id: 'later', label: 'Output', kind: 'observation', detail: 'Later run' }, { id: 'claim', label: 'Claim', kind: 'claim' }], edges: [{ from: 'prior', to: 'claim', relation: 'supports', note: 'Within supplied scope' }, { from: 'later', to: 'prior', relation: 'revises', evidence }] };
const scatter = { title: 'Tradeoff', xAxis: 'Execution', xUnit: 's', yAxis: 'Handling', yUnit: 'min', points: [{ id: 'complete', label: 'Output', x: -3, y: 0, note: 'Signed supplied observation', evidence }, { id: 'missing', label: 'Output', x: 4, y: null, note: 'Handling was not observed' }], limitations: ['Coordinates do not determine preference'] };
const unknowns = { id: 'unknowns-anchor', title: 'Unanswered questions', alternatives: matrix.alternatives, issues: [{ label: 'Operating boundary', relevance: 'Material for offline use', affected: [{ alternative: 'first', consequence: 'Retain the conditional decision', evidence }], note: 'An unresolved dependency' }] };
const artifacts = { title: 'Native output', artifacts: [{ label: 'Source <one>', mediaType: 'text/plain', text: '<script>remains text</script>', evidence }, { label: 'Source two', mediaType: 'text/plain', text: 'Second native output', note: 'Contradicting excerpt' }] };
const fixtures = {
  comparisonMatrix: V.comparisonMatrix(matrix),
  coverageMatrix: V.coverageMatrix(matrix),
  constraintSatisfaction: V.constraintSatisfaction(matrix),
  annotatedTable: V.annotatedTable({ title: 'Annotated observations', columns: ['Case', 'Observed'], rows: [[{ value: 'Case A' }, { value: 0, note: 'Zero is observed', evidence }]] }),
  conditionalRecommendations: V.conditionalRecommendations({ title: 'Conditions', items: [{ condition: 'Offline use', implication: 'Prefer the supplied option under this condition', status: 'conditional', evidence }] }),
  heatmap: V.heatmap({ title: 'Signed cells', rows: [{ id: 'r', label: 'R' }], columns: [{ id: 'c', label: 'C' }], cells: [{ row: 'r', column: 'c', value: -1, evidence }] }),
  pairedComparison: V.pairedComparison({ title: 'Paired', axis: 'Time', unit: 's', leftLabel: 'Before', rightLabel: 'After', pairs: [{ label: 'Case', left: 0, right: 1, evidence }] }),
  intervalPlot: V.intervalPlot({ title: 'Bounds', axis: 'Time', intervalLabel: 'Supplied interval', items: [{ label: 'A', low: 0, high: 1, evidence }] }),
  distribution: V.distribution({ title: 'Observed variation', axis: 'Value', groups: [{ label: 'A', observations: [{ label: 'Run 1', value: 0, evidence }, { label: 'Run 2', value: null, status: 'failed', note: 'Missing after failure' }] }] }),
  trajectory: V.trajectory({ title: 'Change', xAxis: 'Round', yAxis: 'Measure', series: [{ label: 'A', points: [{ label: 'First', x: 1, y: 0, evidence }, { label: 'Later', x: 2, y: 2 }] }] }),
  scatterPlot: V.scatterPlot(scatter),
  evidenceExcerpts: V.evidenceExcerpts({ title: 'Excerpts', items: [{ label: 'First', text: '<script>untrusted text</script>', evidence }, { label: 'Second', text: 'Other perspective', status: 'uncertain' }] }),
  disagreementMap: V.disagreementMap({ title: 'Disagreement', topics: [{ topic: 'Claim boundary', positions: [{ contributor: 'Reviewer A', position: 'Supported for one case', evidence }, { contributor: 'Reviewer B', position: 'The broader claim is unsupported' }], disposition: 'Retain the narrow finding' }] }),
  uncertaintyPanel: V.uncertaintyPanel({ title: 'Limits', items: [{ label: 'Boundary', reason: 'Missing cases', status: 'missing', evidence }] }),
  evidenceLineage: V.evidenceLineage(graph),
  failureTaxonomy: V.failureTaxonomy({ title: 'Failures', categories: [{ label: 'Missing dependency', definition: 'Unavailable resource', alternative: 'A', frequency: '1 of 4 retained runs', conditions: 'Offline', cases: [{ label: 'Run 1', outcome: 'Did not complete', evidence }] }] }),
  scenarioExplorer: V.scenarioExplorer({ title: 'Grounded scenarios', scenarios: [{ label: 'Offline', condition: 'No network', outcomes: [{ alternative: 'A', outcome: 'Retain manual prerequisite', status: 'conditional', evidence }], tradeoff: scatter }, { label: 'Online', condition: 'Network available', outcomes: [] }] }),
  nativeArtifactViewer: V.nativeArtifactViewer(artifacts),
  effortTable: V.effortTable({ title: 'Effort', items: [{ label: 'Run 1', stage: 'Execution', measure: 'Elapsed', value: 3, unit: 's', scope: 'Single run', evidence }] }),
  renderExtension: V.renderExtension({ title: 'Task-specific', purpose: 'Retain distinctions', blocks: [{ kind: 'narrative', text: 'Supplied context' }] }),
  evidenceFreshness: V.evidenceFreshness({ title: 'Dates', events: [{ label: 'Observed', source: 'Run 1', date: '2026-09-17', event: 'Observed', evidence }, { label: 'Imported', source: 'Prior record', date: null, event: 'Date not retained' }] }),
  unknownsMap: V.unknownsMap(unknowns),
  confidenceProvenance: V.confidenceProvenance({ title: 'Grounds', claims: [{ claim: 'Narrow claim', judgment: '0.8 as supplied; no calibration asserted', basis: [{ dimension: 'Directness', observation: 'Native record', evidence }] }] }),
  reliabilityProfile: V.reliabilityProfile({ title: 'Operating conditions', conditions: [{ id: 'offline', label: 'Offline' }], behaviors: [{ id: 'complete', label: 'Completion' }], observations: [{ condition: 'offline', behavior: 'complete', value: 'Failed in this case', status: 'failed', evidence }] }),
  constraintMap: V.constraintMap(matrix),
  decisionHistory: V.decisionHistory({ title: 'Decisions', decisions: [{ label: 'First decision', when: 'Round 1', decision: 'Approve with boundary', availableThen: 'One native case', changesSince: 'Scope questioned', evidence }] }),
  argumentMap: V.argumentMap(graph),
  comparisonJourney: E.comparisonJourney(matrix),
  uncertaintyObservatory: E.uncertaintyObservatory(unknowns),
};

assert.equal(Object.keys(fixtures).length, 29);
for (const [name, html] of Object.entries(fixtures)) {
  assert(html.includes('class="av-card av-frame '), `${name}: missing shared frame`);
  assert(html.includes('data-av-focus'), `${name}: missing focus hook`);
  assert(!html.includes('<script>'), `${name}: executable untrusted text`);
  assert(!/\son(?:click|change|mouseover)=/.test(html), `${name}: inline event handler`);
}
assert(fixtures.scatterPlot.includes('data-av-object="point-1"'));
const partialMark = fixtures.scatterPlot.match(/<g\b[^>]*data-av-inspect="point-1"[^>]*>/g) || [];
assert.equal(partialMark.length, 1, 'One known coordinate needs one explicit missing-coordinate-band mark');
assert(partialMark[0].includes('data-av-partial-coordinate="x"'), 'A missing y coordinate must not become a complete point');
assert(!/<g\b[^>]*class="av-terrain-point"[^>]*data-av-inspect="point-1"/.test(fixtures.scatterPlot), 'The paired cloud cannot invent a missing coordinate');
assert(fixtures.scatterPlot.includes('Y not observed'));
assert(fixtures.scatterPlot.includes('Handling was not observed'));
assert(fixtures.evidenceLineage.includes('data-av-from="node-0" data-av-to="node-2"'));
assert(fixtures.evidenceLineage.includes('<code class="av-id">prior</code>'));
assert(fixtures.evidenceLineage.includes('<code class="av-id">later</code>'));
for (let i = 0; i < graph.edges.length; i++) {
  assert(fixtures.evidenceLineage.includes(`data-av-inspect="edge-${i}"`));
  assert(fixtures.evidenceLineage.includes(`data-av-object="edge-${i}"`));
  assert(fixtures.evidenceLineage.includes(graph.edges[i].relation));
}
assert(fixtures.evidenceLineage.includes('Relationship ID / occurrence'));
assert(fixtures.comparisonJourney.includes('No results outside the retained case'));
assert(fixtures.comparisonJourney.includes('Not supplied'));
assert(fixtures.uncertaintyObservatory.includes('No relationship supplied'));
assert(fixtures.nativeArtifactViewer.includes('&lt;script&gt;remains text&lt;/script&gt;'));
assert(fixtures.confidenceProvenance.includes('0.8 as supplied; no calibration asserted'));
assert(fixtures.scenarioExplorer.includes('Retain manual prerequisite'));

function focusedFindings(html, kind) {
  const objects = [...html.matchAll(new RegExp(`<details\\b[^>]*data-av-object="${kind}-\\d+"[^>]*>([\\s\\S]*?)<\\/details>`, 'g'))];
  assert.equal(objects.length, 2);
  return objects.flatMap(object => {
    const identity = object[1].match(/<code class="av-id">([^<]*)<\/code>/)[1];
    return [...object[1].matchAll(/<th scope="row">[^<]*<code class="av-id">([^<]*)<\/code>[\s\S]*?<\/th><td>([\s\S]*?)<\/td>/g)].map(row => [JSON.stringify(kind === 'alternative' ? [identity, row[1]] : [row[1], identity]), row[2]]);
  }).sort(([left], [right]) => left.localeCompare(right));
}
const represented = focusedFindings(fixtures.comparisonJourney, 'alternative');
assert.equal(represented.length, 4);
assert(new Map(represented).get('["first","must"]').includes('Conditional finding'));
assert(new Map(represented).get('["second","other-must"]').includes('Unobserved outcome'));
assert(new Map(represented).get('["first","other-must"]').includes('Not supplied'));
assert.deepEqual(focusedFindings(fixtures.constraintMap, 'requirement'), represented);
const reordered = { ...matrix, alternatives: [...matrix.alternatives].reverse(), dimensions: [...matrix.dimensions].reverse(), findings: [...matrix.findings].reverse() };
for (const [render, kind] of [[V.constraintMap, 'requirement'], [E.comparisonJourney, 'alternative']]) {
  assert.deepEqual(focusedFindings(render(reordered), kind), represented, 'Focused views retain the same attribution after harmless reordering');
  for (const [declarations, reference] of [['alternatives', 'alternative'], ['dimensions', 'dimension']]) {
    const reassigned = structuredClone(matrix), ids = matrix[declarations].map(item => item.id);
    reassigned[declarations].forEach((item, i) => { item.id = ids[1 - i]; });
    reassigned.findings.forEach(finding => { finding[reference] = ids[1 - ids.indexOf(finding[reference])]; });
    assert.notDeepEqual(focusedFindings(render(reassigned), kind), represented, 'Focused views must show when stable identity is reassigned');
  }
  for (const item of [...matrix.alternatives, ...matrix.dimensions]) assert(render(matrix).includes(item.note));
}
assert(fixtures.constraintMap.includes('<option value="requirement-0">Required · must</option>'));
assert(fixtures.constraintMap.includes('<option value="requirement-1">Required · other-must</option>'));
assert(fixtures.constraintMap.includes('<summary>Required · <code class="av-id">must</code></summary>'));
assert(fixtures.constraintMap.includes('<summary>Required · <code class="av-id">other-must</code></summary>'));
assert(fixtures.comparisonJourney.includes('<th scope="row">Required · <code class="av-id">must</code><p class="av-note">Actual requirement</p>'));
for (const name of ['comparisonMatrix', 'coverageMatrix', 'constraintSatisfaction', 'constraintMap', 'comparisonJourney']) {
  for (const item of [...matrix.alternatives, ...matrix.dimensions]) assert(fixtures[name].includes(`<code class="av-id">${item.id}</code>`), `${name} lost ${item.id}`);
}
for (const name of ['unknownsMap', 'uncertaintyObservatory']) for (const alternative of matrix.alternatives) assert(fixtures[name].includes(`<code class="av-id">${alternative.id}</code>`));

const many = V.evidenceLineage({ title: 'Unbounded node set', nodes: Array.from({ length: 137 }, (_, i) => ({ id: `node-${i}`, label: `Artifact ${i}`, kind: 'record' })), edges: [] });
assert.equal((many.match(/data-av-object="node-\d+"/g) || []).length, 137);
assert(many.includes('Artifact 136'));
const hostile = E.comparisonJourney({ title: '<iframe>', alternatives: [{ id: '<script>', label: '<button>' }], dimensions: [{ id: 'd', label: 'D' }], findings: [{ alternative: '<script>', dimension: 'd', value: 'literal', evidence: [{ label: 'Unsafe link', href: 'javascript:alert(1)' }] }] });
assert(!hostile.includes('<iframe>') && !hostile.includes('<script>'));
assert(!hostile.includes('href="javascript:'));
assert(hostile.includes('data-av-object="alternative-0"'));
assert(hostile.includes('<code class="av-id">&lt;script&gt;</code>'));
const hostileMatrix = { title: 'Hostile identities', alternatives: [{ id: '<script>', label: '<button>' }, { id: 'safe', label: '<button>' }], dimensions: [{ id: '<iframe>', label: '<input>' }, { id: 'other', label: '<input>' }], findings: [{ alternative: '<script>', dimension: '<iframe>', value: 'Literal finding' }] };
for (const render of [V.comparisonMatrix, V.constraintMap, E.comparisonJourney, input => V.heatmap({ title: input.title, rows: input.alternatives, columns: input.dimensions, cells: [] }), input => V.unknownsMap({ title: input.title, alternatives: input.alternatives, issues: [] })]) {
  const html = render(hostileMatrix);
  assert(!/<(?:script|iframe|input|button)>/.test(html), 'Disambiguating identities and labels must remain escaped');
  assert(html.includes('<code class="av-id">&lt;script&gt;</code>'));
}
process.stdout.write(JSON.stringify(fixtures));
