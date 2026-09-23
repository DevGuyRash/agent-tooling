#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');

if (process.argv.length !== 5) {
  console.error('usage: node render_corpus.cjs <compiled-root> <fixture-root> <body-output>');
  process.exit(2);
}

const [compiledRoot, fixtureRoot, outputRoot] = process.argv.slice(2).map(value => path.resolve(value));
const modulePath = (...parts) => path.join(compiledRoot, ...parts);
const V = require(modulePath('src', 'index.js'));
const demo = require(modulePath('examples', 'demo.js'));
const cases = require(modulePath('examples', 'reader-cases.js'));
const snippets = require(modulePath('examples', 'snippets.js'));
const fixtures = JSON.parse(fs.readFileSync(path.join(fixtureRoot, 'index.json'), 'utf8'));

fs.mkdirSync(outputRoot, { recursive: true });
const fixtureBodies = path.join(outputRoot, 'fixtures');
fs.mkdirSync(fixtureBodies, { recursive: true });

const escape = value => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
const safe = value => String(value).replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
const sourceOf = fixture => fs.readFileSync(path.join(fixtureRoot, fixture.file), 'utf8');
const expected = fixture => {
  if (!['ready', 'error'].includes(fixture.expectedState)) throw Error('Missing expected state: ' + fixture.file);
  return fixture.expectedState;
};

function fixtureMarkup(fixture, index) {
  const source = sourceOf(fixture);
  const key = safe(fixture.file);
  const metadata = '<p class="av-note" data-round2-fixture-meta>Expected renderer state: <strong>' + escape(expected(fixture)) + '</strong>. Coverage: ' + escape(fixture.kind) + '. Family: <code>' + escape(fixture.family) + '</code>.</p>'
    + (fixture.visualLimitation ? '<p class="av-note" data-round2-visual-limitation><strong>Known visual limitation:</strong> ' + escape(fixture.visualLimitation) + '</p>' : '')
    + (fixture.note ? '<p class="av-note">' + escape(fixture.note) + '</p>' : '')
    + (fixture.failureKind ? '<p class="av-note">Diagnostic category: ' + escape(fixture.failureKind) + '. Expected message: <code>' + escape(fixture.expectedDiagnostic) + '</code>.</p>' : '')
    + '<p class="av-muted">Pinned syntax/reference: <code>' + escape(fixture.reference || 'Bundled detector/layout registry') + '</code></p>';
  return '<section data-round2-fixture="' + escape(fixture.file) + '" data-round2-family="' + escape(fixture.family) + '" data-round2-expected="' + escape(expected(fixture)) + '" data-round2-index="' + index + '">'
    + V.reportSection({
      id: 'fixture-' + key,
      title: fixture.family + ' · ' + fixture.file,
      body: metadata + V.mermaidDiagram({
        id: 'diagram-' + key,
        title: fixture.family + ' compatibility fixture',
        caption: 'Exact source retained · expected ' + expected(fixture)
          + (fixture.visualLimitation ? '. Known visual limitation: ' + fixture.visualLimitation : ''),
        source,
      }),
    })
    + '</section>';
}

function write(name, body) {
  fs.writeFileSync(path.join(outputRoot, name + '.html'), body, 'utf8');
}

write('field-study', demo.renderDemo());
write('compact', cases.renderCompact());
write('embedded', cases.renderEmbedded());
write('stress', cases.renderStress());
write('snippets', snippets.renderSnippets());

fixtures.forEach((fixture, index) => {
  const body = V.reportSurface({
    id: 'fixture-report-' + safe(fixture.file),
    theme: 'light',
    palette: 'graphite',
    canvas: 'plain',
    spacing: 'comfortable',
    sections: 'multiple',
    body: fixtureMarkup(fixture, index),
  });
  fs.writeFileSync(path.join(fixtureBodies, fixture.file.replace(/\.mmd$/, '.html')), body, 'utf8');
});

const registered = fixtures.filter(fixture => fixture.kind === 'diagram');
const special = fixtures.filter(fixture => fixture.kind !== 'diagram');
write('mermaid-gallery', V.evidenceWorkspace({
  id: 'mermaid-round2-gallery',
  label: 'Maintainer compatibility corpus',
  title: 'Pinned Mermaid family and failure gallery',
  description: 'Every bundled registered family is represented by exact deterministic source. Layout alternatives and intentional failures remain separate from ordinary family coverage.',
  theme: 'light',
  notebook: { revision: 'round2-mermaid-1' },
  brief: {
    question: 'Does the pinned Mermaid runtime retain every registered family and useful failure path in the visual library?',
    paragraphs: ['Each fixture keeps its original source, expected state and pinned upstream reference visible. Ready means the renderer completed; known visual limitations are identified separately. The fictional content does not support conclusions about a real system.'],
    finding: registered.length + ' registered diagram families are exercised; layout and failure candidates remain explicit rather than silently normalized.',
  },
  views: [
    {
      id: 'families',
      label: 'Registered families (' + registered.length + ')',
      description: 'One substantial deterministic source for every family reported by the bundled registry.',
      body: registered.map(fixture => fixtureMarkup(fixture, fixtures.indexOf(fixture))).join(''),
    },
    {
      id: 'special',
      label: 'Layouts and retained failures (' + special.length + ')',
      description: 'Layout loaders, long/repeated labels, author configuration and intentionally failing sources.',
      body: special.map(fixture => fixtureMarkup(fixture, fixtures.indexOf(fixture))).join(''),
    },
  ],
  footer: '<p>Maintainer corpus only. No live network data, dates, random IDs or inferred findings are used.</p>',
}));

const layouts = fixtures.filter(fixture => fixture.kind === 'layout candidate');
const edges = fixtures.filter(fixture => fixture.kind !== 'diagram' && fixture.kind !== 'layout candidate');
write('mermaid-layouts', V.evidenceWorkspace({
  id: 'mermaid-layout-gallery',
  label: 'Maintainer layout corpus',
  title: 'Mermaid layout alternatives and retained error sources',
  description: 'Graph layouts share a richer flow topology. CoSE-Bilkent is also demonstrated with its supported mindmap family; the incompatible flowchart request retains its explicit diagnostic.',
  theme: 'light',
  views: [
    { id: 'layouts', label: 'Layout alternatives (' + layouts.length + ')', body: layouts.map(fixture => fixtureMarkup(fixture, fixtures.indexOf(fixture))).join('') },
    { id: 'edges', label: 'Edge and error cases (' + edges.length + ')', body: edges.map(fixture => fixtureMarkup(fixture, fixtures.indexOf(fixture))).join('') },
  ],
}));

const fixtureByFile = new Map(fixtures.map(fixture => [fixture.file, fixture]));
const diagram = filename => {
  const fixture = fixtureByFile.get(filename);
  return fixtureMarkup(fixture, fixtures.indexOf(fixture));
};
const evidence = [{ label: 'Pinned maintainer fixture', note: 'Synthetic evidence used only to exercise the visual system.' }];
const lineageLongNote = [
  'Qualification scope — synthetic maintainer evidence only.',
  'This relationship preserves the complete context needed to read the first Condition α observation without turning it into a score or a general result. The observation belongs to alpha-record-1: execution was recorded as 4 s and handoff as 11 min for one retained run. The source record identifies the run separately from alpha-record-2 even though both use the visible label “Repeated sample”. The repeated label is intentional: a reader must use the stable IDs and attached context instead of assuming the two rows are duplicates or silently merging them.',
  'The qualification is also bounded by conditions that are part of the record. This fixture treats the room and operator as retained context, and it makes no claim that the same measurement would hold with a different operator, a different room, a longer session, a larger payload, or an interrupted handoff. Condition β has no observed after measurement, so that missing value cannot be borrowed from either Condition α run. Condition γ was recorded under a different room and operator and remains a separate conditional observation. None of those records supplies a basis for ranking the conditions or imputing the missing handoff value.',
  'Two parallel relationships connect alpha-record-1 to review-scope on purpose. One records the positive support carried by the observation; this relationship records the qualification that must travel with that support. They are separate relationship identities because a reviewer may need to inspect, annotate, or return to either statement independently. The downstream bounded-summary node can use the scoped review only as a summary of retained observations. It must continue to expose the original IDs, the unresolved interrupted run, the different Condition γ context, and the units attached to each numeric value.',
  'This long note is deliberately retained in the inspector so qualification checks can exercise scrolling, relationship selection, origin and destination navigation, and exact text recovery without mutating live evidence. END OF RETAINED QUALIFICATION.',
].join('\n\n');
write('mixed-components', V.evidenceWorkspace({
  id: 'round2-mixed-report',
  label: 'Mixed maintainer composition',
  title: 'Relationships, measurements and records in one deterministic report',
  description: 'A deliberately mixed report combines Mermaid with quantitative, structured, narrative and native-record components.',
  theme: 'light',
  notebook: { revision: 'round2-mixed-1' },
  brief: {
    question: 'Can multiple visual components coexist without erasing missingness, repeated labels or exact source context?',
    paragraphs: ['Values are fixed synthetic observations. Repeated labels and one missing measurement are intentional.'],
    finding: 'The report is a compatibility composition, not a recommendation or ranking.',
    evidence,
  },
  views: [
    {
      id: 'overview',
      label: 'Overview and process',
      body: V.storyPanel({
        id: 'mixed-story',
        title: 'Repeated labels belong to different retained records',
        lead: [{ text: 'Condition α', tone: 'accent', strong: true }, { text: ' appears in several components with stable IDs and explicit context.' }],
        paragraphs: ['The source, review and export stages are modeled separately. A missing result stays missing rather than being imputed.'],
      }) + V.pairedComparison({
        id: 'mixed-pairs',
        title: 'Observed handling measurements',
        axis: 'Elapsed time',
        unit: 'min',
        leftLabel: 'Recorded before',
        rightLabel: 'Recorded after',
        pairs: [
          { label: 'Condition α · run 1', left: 12, right: 9, evidence },
          { label: 'Condition α · run 2', left: 15, right: 11, evidence },
          { label: 'Condition β · interrupted', left: 14, right: null, note: 'The after measurement was not observed.', evidence },
          { label: 'Long retained qualification · different room and operator', left: 18, right: 13, evidence },
        ],
      }) + diagram('flowchart-v2.mmd'),
    },
    {
      id: 'relationships',
      label: 'Relationships and partial measurements',
      body: V.scatterPlot({
        id: 'mixed-scatter',
        title: 'Known coordinates and missing counterparts',
        xAxis: 'Execution',
        xUnit: 's',
        yAxis: 'Handoff',
        yUnit: 'min',
        points: [
          { id: 'alpha-1', label: 'Repeated sample', groupId: 'alpha', group: 'Condition α', x: 4, y: 11, evidence },
          { id: 'alpha-2', label: 'Repeated sample', groupId: 'alpha', group: 'Condition α', x: 6, y: 9, evidence },
          { id: 'beta-1', label: 'Partial sample', groupId: 'beta', group: 'Condition β', x: 8, y: null, note: 'Handoff time missing.', evidence },
          { id: 'gamma-1', label: 'Long qualification sample', groupId: 'gamma', group: 'Condition γ', x: 10, y: 7, note: 'Observed under a different retained condition.', evidence },
        ],
      }) + V.annotatedTable({
        id: 'mixed-table',
        title: 'Retained record status',
        columns: ['Record', 'Result', 'Scope'],
        rows: [
          [{ value: 'Condition α / run 1' }, { value: 11, status: 'supported' }, { value: 'Observed handoff minutes' }],
          [{ value: 'Condition α / run 2' }, { value: 9, status: 'supported' }, { value: 'Observed handoff minutes' }],
          [{ value: 'Condition β / interrupted' }, { value: null, status: 'missing', note: 'No handoff measurement.' }, { value: 'Missing remains explicit' }],
          [{ value: 'Condition γ / long context' }, { value: 7, status: 'conditional' }, { value: 'Different retained condition' }],
        ],
      }) + V.evidenceLineage({
        id: 'mixed-lineage',
        title: 'Retained observation lineage and qualifications',
        description: 'Repeated labels keep distinct IDs, while parallel relationships preserve support and its scope as separate reviewable records.',
        nodes: [
          { id: 'alpha-record-1', label: 'Repeated sample', kind: 'retained observation', detail: 'Condition α run 1: execution 4 s; handoff 11 min.', evidence },
          { id: 'alpha-record-2', label: 'Repeated sample', kind: 'retained observation', detail: 'Condition α run 2: execution 6 s; handoff 9 min.', evidence },
          { id: 'review-scope', label: 'Scoped review', kind: 'qualification', detail: 'Keeps the two retained runs distinct and preserves the limits that travel with each observation.' },
          { id: 'handoff-gap', label: 'Interrupted handoff', kind: 'missing observation', detail: 'Condition β has execution 8 s and no observed handoff measurement.' },
          { id: 'bounded-summary', label: 'Bounded summary', kind: 'synthesis', detail: 'Summarizes only the supplied observations; it does not rank conditions or impute missing values.' },
        ],
        edges: [
          { id: 'alpha1-support', from: 'alpha-record-1', to: 'review-scope', relation: 'supports within the recorded room and operator', evidence },
          { id: 'alpha1-scope', from: 'alpha-record-1', to: 'review-scope', relation: 'carries a separate retained scope qualification', note: lineageLongNote, evidence },
          { id: 'alpha2-support', from: 'alpha-record-2', to: 'review-scope', relation: 'supports under its separately retained run', evidence },
          { id: 'gap-limits', from: 'handoff-gap', to: 'review-scope', relation: 'keeps the interrupted handoff unresolved', note: 'No after measurement was observed for Condition β.' },
          { id: 'scope-bounds-summary', from: 'review-scope', to: 'bounded-summary', relation: 'bounds the synthesized statement to supplied observations', evidence },
        ],
      }) + diagram('sequence.mmd'),
    },
    {
      id: 'records',
      label: 'Original records and state',
      body: V.nativeArtifactViewer({
        id: 'mixed-records',
        title: 'Exact synthetic records',
        artifacts: [
          { label: 'Condition α record', mediaType: 'text/plain', text: 'record: alpha-1\nexecution: 4 s\nhandoff: 11 min\nlabel: Repeated sample\nUnicode: 日本語 / é / 👩🏽‍🚀', evidence },
          { label: 'Condition β interrupted record', mediaType: 'text/plain', text: 'record: beta-1\nexecution: 8 s\nhandoff: unavailable\nreason: observation stopped before handoff measurement', evidence },
          { label: 'Long qualification record', mediaType: 'text/plain', text: 'record: gamma-1\ncondition: different room and operator\nThe retained qualification remains attached to this exact record rather than becoming a score.', evidence },
        ],
      }) + diagram('stateDiagram.mmd'),
    },
  ],
  footer: '<p>All records and values are deterministic maintainer fixtures. They are not evaluation evidence about a real system.</p>',
}));

console.log(JSON.stringify({
  bodies: fs.readdirSync(outputRoot).filter(name => name.endsWith('.html')).sort(),
  fixtureBodies: fs.readdirSync(fixtureBodies).filter(name => name.endsWith('.html')).length,
  registeredFamilies: registered.map(fixture => fixture.family),
  specialFixtures: special.map(fixture => fixture.file),
}));
