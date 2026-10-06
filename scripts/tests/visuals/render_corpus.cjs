#!/usr/bin/env node
// Build the maintainer corpus's report specifications and render their static
// markup with the shipped browser bundle. Nothing is compiled or fetched: the
// bundle runs in a local VM without a DOM, which is enough for renderReport.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

if (process.argv.length !== 6) {
  console.error('usage: node render_corpus.cjs <agentic-visuals.js> <fixture-root> <examples-root> <output-root>');
  process.exit(2);
}

const [bundle, fixtureRoot, examplesRoot, outputRoot] = process.argv.slice(2).map(value => path.resolve(value));
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(bundle, 'utf8'), context, { filename: bundle, timeout: 10000 });
const V = context.AgenticVisuals;
if (!V || typeof V.renderReport !== 'function' || typeof V.trialReport !== 'function') throw new Error('The bundle does not expose AgenticVisuals.renderReport and trialReport.');

const fixtures = JSON.parse(fs.readFileSync(path.join(fixtureRoot, 'index.json'), 'utf8'));
const readJson = name => JSON.parse(fs.readFileSync(path.join(examplesRoot, name), 'utf8'));
const specRoot = path.join(outputRoot, 'specs'), bodyRoot = path.join(outputRoot, 'bodies'), fixtureBodies = path.join(bodyRoot, 'fixtures');
for (const directory of [specRoot, fixtureBodies]) fs.mkdirSync(directory, { recursive: true });

// The same key native_runner.py and test_corpus.py derive from a fixture file.
const safe = value => String(value).replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
const sourceOf = fixture => fs.readFileSync(path.join(fixtureRoot, fixture.file), 'utf8');
const expected = fixture => {
  if (!['ready', 'error'].includes(fixture.expectedState)) throw Error('Missing expected state: ' + fixture.file);
  return fixture.expectedState;
};

/** One diagram block per fixture: its id names the fixture, its heading states
 * what the renderer should do and why, and its source is the exact file text. */
function fixtureBlock(fixture) {
  const state = expected(fixture);
  const description = [`Expected renderer state: ${state}. Coverage: ${fixture.kind}. Family: ${fixture.family}.`];
  if (fixture.visualLimitation) description.push('Known visual limitation: ' + fixture.visualLimitation);
  if (fixture.note) description.push(fixture.note);
  if (fixture.failureKind) description.push(`Diagnostic category: ${fixture.failureKind}. Expected message: “${fixture.expectedDiagnostic}”.`);
  return {
    type: 'diagram',
    id: 'fixture-' + safe(fixture.file),
    title: fixture.family + ' · ' + fixture.file,
    description,
    caption: 'Exact source retained · expected ' + state + (fixture.visualLimitation ? '. Known visual limitation: ' + fixture.visualLimitation : ''),
    note: 'Pinned syntax/reference: ' + (fixture.reference || 'Bundled detector/layout registry'),
    source: sourceOf(fixture),
  };
}

const registered = fixtures.filter(fixture => fixture.kind === 'diagram');
const special = fixtures.filter(fixture => fixture.kind !== 'diagram');
const layouts = fixtures.filter(fixture => fixture.kind === 'layout candidate');
const edges = fixtures.filter(fixture => fixture.kind !== 'diagram' && fixture.kind !== 'layout candidate');
const byFile = new Map(fixtures.map(fixture => [fixture.file, fixture]));
const diagram = filename => fixtureBlock(byFile.get(filename));
const footer = 'Maintainer corpus only. No live network data, dates, random IDs or inferred findings are used; nothing here is evidence about a real system.';

const specs = {
  'mermaid-gallery': {
    title: 'Mermaid · complete family gallery',
    kicker: 'Maintainer corpus',
    summary: [
      'Every family the bundled Mermaid registry reports is represented by exact deterministic source. Layout alternatives and intentional failures stay separate from ordinary family coverage.',
      `${registered.length} registered families and ${special.length} layout, edge and failure cases. Ready means the renderer completed; known visual limitations are named beside the drawing rather than certified away.`,
    ],
    sections: [
      { id: 'families', title: `Registered families (${registered.length})`, label: 'Families', lead: 'One substantial deterministic source for every family the bundled registry reports.', blocks: registered.map(fixtureBlock) },
      { id: 'special', title: `Layouts and retained failures (${special.length})`, label: 'Layouts and failures', lead: 'Layout loaders, long and repeated labels, author configuration and intentionally failing sources.', blocks: special.map(fixtureBlock) },
    ],
    footer,
  },
  'mermaid-layouts': {
    title: 'Mermaid · layouts and explicit diagnostics',
    kicker: 'Maintainer corpus',
    summary: 'Graph layouts share a richer flow topology. CoSE-Bilkent is also demonstrated with its supported mindmap family; the incompatible flowchart request keeps its explicit diagnostic.',
    sections: [
      { id: 'layouts', title: `Layout alternatives (${layouts.length})`, label: 'Layouts', blocks: layouts.map(fixtureBlock) },
      { id: 'edges', title: `Edge and error cases (${edges.length})`, label: 'Edges and errors', blocks: edges.map(fixtureBlock) },
    ],
    footer,
  },
  'mixed-components': {
    title: 'Mixed evidence · diagrams, measurements and records',
    kicker: 'Maintainer corpus',
    summary: 'A deliberately mixed report: Mermaid drawings beside quantitative, tabular, requirement and record views. Repeated labels and one missing measurement are intentional.',
    meta: [{ label: 'Records', value: '4 synthetic' }, { label: 'Missing', value: '1 handoff measurement' }],
    arms: [{ id: 'alpha', label: 'Condition α' }, { id: 'beta', label: 'Condition β' }, { id: 'gamma', label: 'Condition γ', note: 'different room and operator' }],
    sections: [
      {
        id: 'overview', title: 'Overview and process', label: 'Overview',
        lead: 'Condition α appears in several views with stable identifiers and explicit context. A missing result stays missing rather than being imputed.',
        blocks: [
          { type: 'callout', tone: 'limit', title: 'Repeated labels belong to different retained records', text: 'Two runs share the visible label “Repeated sample”. Read them by their record identifiers, not by their labels.' },
          { type: 'intervals', title: 'Handoffs completed within ten minutes', rows: [
            { label: 'Condition α', arm: 'alpha', k: 1, n: 2 },
            { label: 'Condition β', arm: 'beta', k: 0, n: 1, note: 'one interrupted run; its after measurement was not observed' },
            { label: 'Condition γ', arm: 'gamma', k: 1, n: 1, note: 'different room and operator' },
          ], reference: { value: 0.5, label: 'half' } },
          diagram('flowchart-v2.mmd'),
        ],
      },
      {
        id: 'relationships', title: 'Records and requirements', label: 'Records',
        blocks: [
          { type: 'table', id: 'mixed-table', title: 'Retained record status', columns: ['Record', 'Label', 'Handoff (min)', 'Scope'], numeric: [2], rows: [
            ['alpha-record-1', 'Repeated sample', { value: 11, status: 'pass' }, 'Observed handoff minutes'],
            ['alpha-record-2', 'Repeated sample', { value: 9, status: 'pass' }, 'Observed handoff minutes'],
            ['beta-record-1', 'Partial sample', { value: null, status: 'invalid', note: 'No handoff measurement.' }, 'Missing remains explicit'],
            ['gamma-record-1', 'Long qualification sample', { value: 7, status: 'warn', note: 'Different retained condition.' }, 'Conditional observation'],
          ] },
          { type: 'matrix', title: 'Requirements each condition established', columns: [{ id: 'alpha', label: 'Condition α', arm: true }, { id: 'beta', label: 'Condition β', arm: true }, { id: 'gamma', label: 'Condition γ', arm: true }],
            rows: [{ id: 'timed', label: 'Execution timed' }, { id: 'handoff', label: 'Handoff measured', detail: 'after the run completes' }],
            cells: [
              { row: 'timed', column: 'alpha', status: 'pass', text: '4 s, 6 s' }, { row: 'timed', column: 'beta', status: 'pass', text: '8 s' }, { row: 'timed', column: 'gamma', status: 'pass', text: '10 s' },
              { row: 'handoff', column: 'alpha', status: 'pass', text: '11, 9 min' }, { row: 'handoff', column: 'beta', status: 'missing', note: 'interrupted before handoff' }, { row: 'handoff', column: 'gamma', status: 'warn', text: '7 min', note: 'different room' },
            ] },
          { type: 'callout', tone: 'note', title: 'Qualification scope — synthetic maintainer evidence only', text: [
            'This qualification preserves the complete context needed to read the first Condition α observation without turning it into a score or a general result. The observation belongs to alpha-record-1: execution was recorded as 4 s and handoff as 11 min for one retained run. The source record identifies the run separately from alpha-record-2 even though both use the visible label “Repeated sample”.',
            'It is bounded by conditions that are part of the record. It makes no claim that the same measurement would hold with a different operator, a different room, a longer session, a larger payload, or an interrupted handoff. Condition β has no observed after measurement, so that missing value cannot be borrowed from either Condition α run. Condition γ was recorded under a different room and operator and remains a separate conditional observation.',
            'This long note is deliberately retained so containment checks exercise long wrapped text beside drawings and tables. END OF RETAINED QUALIFICATION.',
          ] },
          diagram('sequence.mmd'),
        ],
      },
      {
        id: 'records', title: 'Original records and state', label: 'Originals',
        blocks: [
          { type: 'excerpts', title: 'Exact synthetic records', items: [
            { text: 'record: alpha-1\nexecution: 4 s\nhandoff: 11 min\nlabel: Repeated sample\nUnicode: 日本語 / é / 👩🏽‍🚀', arm: 'alpha', outcome: 'pass', source: 'alpha-record-1' },
            { text: 'record: beta-1\nexecution: 8 s\nhandoff: unavailable\nreason: observation stopped before handoff measurement', arm: 'beta', outcome: 'invalid', source: 'beta-record-1', note: 'interrupted' },
            { text: 'record: gamma-1\ncondition: different room and operator\nThe retained qualification remains attached to this exact record rather than becoming a score.', arm: 'gamma', source: 'gamma-record-1' },
          ] },
          { type: 'facts', title: 'Record facts', items: [{ label: 'Repeated label', value: 'Repeated sample' }, { label: 'Distinct records', value: 4 }, { label: 'Condition β handoff', value: null }, { label: 'Fixture', value: 'stateDiagram.mmd', mono: true }] },
          diagram('stateDiagram.mmd'),
        ],
      },
    ],
    footer: 'All records and values are deterministic maintainer fixtures. They are not evaluation evidence about a real system.',
  },
};

const writeText = (file, text) => fs.writeFileSync(file, text.endsWith('\n') ? text : text + '\n', 'utf8');
for (const [name, spec] of Object.entries(specs)) {
  writeText(path.join(specRoot, name + '.json'), JSON.stringify(spec, null, 2));
  writeText(path.join(bodyRoot, name + '.html'), V.renderReport(spec));
}

// The maintained examples, rendered the way report.py's pages render them.
const trial = readJson('fictional-trial.json');
writeText(path.join(bodyRoot, 'fictional-trial.html'), V.renderReport(V.trialReport(trial, readJson('fictional-narrative.json'))));
writeText(path.join(bodyRoot, 'fictional-trial-bare.html'), V.renderReport(V.trialReport(trial, {})));
writeText(path.join(bodyRoot, 'showcase.html'), V.renderReport(readJson('showcase-spec.json')));

for (const fixture of fixtures) {
  writeText(path.join(fixtureBodies, fixture.file.replace(/\.mmd$/, '.html')), V.renderReport({
    title: fixture.family + ' · ' + fixture.file, kicker: 'Maintainer fixture',
    sections: [{ id: 'fixture', title: fixture.family + ' compatibility fixture', blocks: [fixtureBlock(fixture)] }],
    footer,
  }));
}

console.log(JSON.stringify({
  specs: fs.readdirSync(specRoot).filter(name => name.endsWith('.json')).sort(),
  bodies: fs.readdirSync(bodyRoot).filter(name => name.endsWith('.html')).sort(),
  fixtureBodies: fs.readdirSync(fixtureBodies).filter(name => name.endsWith('.html')).length,
  registeredFamilies: registered.map(fixture => fixture.family),
  specialFixtures: special.map(fixture => fixture.file),
}));
