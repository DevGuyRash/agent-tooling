/* Test the source renderer without a browser, DOM emulator or generated bundle. */
const assert = require('node:assert/strict');
const path = require('node:path');
const S = require(path.join(process.argv[2], 'src/story.js'));
const core = require(path.join(process.argv[2], 'src/core.js'));

let checks = 0;
function check(label, run) {
  try { run(); checks++; }
  catch (error) { throw new Error(`${label}: ${error.message}`, { cause: error }); }
}
function laneBodies(html) {
  return html.split('<section class="av-lane"').slice(1).map(lane => {
    let depth = 1;
    for (const tag of lane.matchAll(/<\/?section\b[^>]*>/g)) {
      depth += tag[0].startsWith('</') ? -1 : 1;
      if (depth === 0) return lane.slice(0, tag.index);
    }
    throw new Error('Lane did not close as an independent section');
  });
}

check('inline text escapes hostile strings and preserves exact authored content', () => {
  const hostile = '<img src=x onerror="alert(1)"> & </strong>\' 差異 👩🏽‍🔬\n\t  stays';
  assert.equal(S.inlineText(hostile), core.escapeText(hostile));
  assert.equal(S.inlineText([{ text: hostile, tone: 'caution', strong: true }]), `<span class="av-tone-caution"><strong>${core.escapeText(hostile)}</strong></span>`);
  assert.equal(S.inlineText([{ text: '\n\t  ' }, { text: -0 }, { text: ' → ' }, { text: 0.10000000000000002 }, { text: '\u00a0≠\u00a0' }, { text: Number.MIN_VALUE }]), '\n\t  -0 → 0.10000000000000002\u00a0≠\u00a05e-324');
  assert.equal(S.inlineText(Object.freeze([{ text: 'retained', strong: false }, { text: '  ' }, { text: 1e308 }])) , 'retained  1e+308');
  assert.equal(S.inlineText(''), '');
  assert.equal(S.inlineText([]), '');
  assert.equal(S.inlineText([{ text: 'Failed in one case; only the author chose this tone.', tone: 'positive' }]), '<span class="av-tone-positive">Failed in one case; only the author chose this tone.</span>');
  for (const tone of ['plain', 'accent', 'positive', 'caution', 'negative', 'muted']) assert(S.inlineText([{ text: 'Same content', tone }]).includes(`class="av-tone-${tone}"`));
});

check('invalid inline payloads cannot introduce executable markup or invalid numbers', () => {
  for (const value of [undefined, null, 1, {}, [null], ['not a segment'], [{ text: null }], [{ text: {} }], [{ text: NaN }], [{ text: Infinity }], [{ text: -Infinity }]]) assert.throws(() => S.inlineText(value), TypeError);
  for (const tone of ['ranked-best', 'accent" onclick="alert(1)', null, false, 1]) assert.throws(() => S.inlineText([{ text: 'X', tone }]), /Use plain, accent, positive, caution, negative, or muted/);
  for (const strong of ['true', 1, null]) assert.throws(() => S.inlineText([{ text: 'X', strong }]), /true or false/);
});

check('story retains qualifications, precise values, annotations and constraints', () => {
  const html = S.storyPanel({
    title: 'What the retained cases show', description: 'Evidence is limited to supplied observations.', collapsible: false,
    lead: [{ text: 'A completed ' }, { text: '3 of 4', tone: 'accent', strong: true }, { text: ' retained offline cases; the fourth required manual recovery.' }],
    paragraphs: ['A’s faster recovery did not establish a general preference.', [{ text: 'Observed difference: ' }, { text: -0, tone: 'plain' }, { text: ' s. The unrounded later observation was ' }, { text: 0.30000000000000004 }, { text: ' s.' }]],
    takeaways: [
      { label: 'For offline work', text: [{ text: 'Use A only when manual recovery is acceptable.', tone: 'caution' }], status: 'conditional', note: 'One retained failure still needs handling.', evidence: [{ label: 'Exact failure record', href: '#failure-record', note: 'Case 4, not an aggregate score' }] },
      { label: 'Other conditions', text: 'Online outcomes were not measured.', status: 'missing', evidence: [{ label: 'Study scope', href: 'https://example.com/scope?a=1&b=2' }] },
    ],
    note: 'Author judgment remains conditional.', evidence: [{ label: 'Native observations', href: '#native-observations' }],
    limitations: ['Only four retained cases; no broader claim.', 'No supplied confidence estimate.'],
  });
  assert(html.startsWith('<section class="av-card av-frame av-frame-interpretation"'));
  assert(html.includes('data-av-focus'));
  for (const text of ['3 of 4', 'the fourth required manual recovery.', 'did not establish a general preference.', '0.30000000000000004', '>−0<'.replace('−', '-'), 'One retained failure still needs handling.', 'Case 4, not an aggregate score', 'Online outcomes were not measured.', 'Author judgment remains conditional.', 'Only four retained cases; no broader claim.', 'No supplied confidence estimate.']) assert(html.includes(text), `lost authored meaning: ${text}`);
  assert.equal((html.match(/class="av-story-takeaway"/g) || []).length, 2);
  assert(html.includes('class="av-status av-status-conditional">conditional</span>'));
  assert(html.includes('class="av-status av-status-missing">missing</span>'));
  for (const href of ['#failure-record', '#native-observations', 'https://example.com/scope?a=1&amp;b=2']) assert(html.includes(`href="${href}"`));
  assert(html.indexOf('Use A only when') < html.indexOf('Online outcomes were not measured.'));
  assert(html.indexOf('av-frame-footer') < html.indexOf('Author judgment remains conditional.'));
});

check('story supports several legitimate compositions without inventing a sequence or verdict', () => {
  const empty = S.storyPanel({ title: 'Evidence still being collected' });
  assert(empty.includes('<div class="av-story"></div>'));
  assert(!empty.includes('av-story-lead'));
  assert(!empty.includes('av-story-paragraph'));
  assert(!empty.includes('av-story-takeaways'));
  assert(!empty.includes('av-status'));
  const leadOnly = S.storyPanel({ title: 'Retained scope', lead: 'Only the supplied cases are in scope.', open: false });
  assert(leadOnly.startsWith('<details '));
  assert(!leadOnly.slice(0, leadOnly.indexOf('>')).includes(' open'));
  assert.equal((leadOnly.match(/class="av-story-lead"/g) || []).length, 1);
  assert(!leadOnly.includes('av-story-paragraph'));
  const paragraphs = S.storyPanel({ title: 'Reading the evidence', paragraphs: ['Start with exceptions.', 'Then inspect the relevant cases.'] });
  assert.equal((paragraphs.match(/class="av-story-paragraph"/g) || []).length, 2);
  assert(paragraphs.indexOf('Start with exceptions.') < paragraphs.indexOf('Then inspect the relevant cases.'));
  const findingOnly = S.storyPanel({ title: 'Unresolved', takeaways: [{ label: 'Still unknown', text: 'No supported generalization yet.' }] });
  assert(!findingOnly.includes('av-story-lead'));
  assert(!findingOnly.includes('av-status'));
  const literalEmpty = S.storyPanel({ title: 'Draft', lead: '', paragraphs: ['', []], takeaways: [] });
  assert(literalEmpty.includes('<p class="av-story-lead"></p>'));
  assert.equal((literalEmpty.match(/<p class="av-story-paragraph"><\/p>/g) || []).length, 2);
  for (const input of [{ paragraphs: 'paragraph' }, { takeaways: {} }]) assert.throws(() => S.storyPanel({ title: 'Invalid', ...input }), TypeError);
});

check('story escapes every authored text surface while retaining shared unsafe-reference behavior', () => {
  const attack = key => `<script>alert("${key}")</script>`;
  const fields = ['title', 'description', 'lead', 'paragraph', 'finding-label', 'finding-text', 'finding-note', 'finding-evidence', 'reference-note', 'note', 'limitation', 'evidence'];
  const html = S.storyPanel({ title: attack('title'), description: attack('description'), lead: attack('lead'), paragraphs: [[{ text: attack('paragraph'), tone: 'negative' }]], takeaways: [{ label: attack('finding-label'), text: attack('finding-text'), note: attack('finding-note'), evidence: [{ label: attack('finding-evidence'), href: 'javascript:alert(1)', note: attack('reference-note') }] }], note: attack('note'), limitations: [attack('limitation')], evidence: [{ label: attack('evidence'), href: '#safe' }] });
  assert(!html.includes('<script>'));
  for (const field of fields) assert(html.includes(core.escapeText(attack(field))), `text missing or unescaped: ${field}`);
  assert(!html.includes('href="javascript:'));
  assert(html.includes('link omitted: javascript:alert(1)'));
  assert.throws(() => S.storyPanel({ title: 'Invalid', takeaways: [{ label: 'X', text: 'Y', status: 'winner' }] }), /Unknown status/);
});

check('lanes preserve repeated-label identity, attribution and independent disclosure groups', () => {
  const first = { id: 'earlier', label: 'Same name', note: 'Earlier scope', evidence: [{ label: 'Earlier record', href: '#earlier-record' }], body: S.storyPanel({ title: 'Earlier outcome', lead: 'A retained conditional result.', open: false }) + S.storyPanel({ title: 'Earlier exception', lead: 'Keep its exception visible.', collapsible: false }) };
  const second = { id: 'later', label: 'Same name', note: 'Later scope', body: S.storyPanel({ title: 'Later outcome', lead: 'The later case has different grounds.', open: true }) };
  const html = S.comparisonLanes({ title: 'Two supplied records', description: 'Order does not establish preference.', lanes: [first, second], sectionMode: 'solo' });
  assert(html.startsWith('<section class="av-comparison-lanes"><header>'));
  assert.equal((html.match(/data-av-section-group/g) || []).length, 2);
  assert.equal((html.match(/data-av-section-mode="solo"/g) || []).length, 2);
  assert(!html.slice(0, html.indexOf('<section class="av-lane"')).includes('data-av-section-group'));
  const lanes = laneBodies(html);
  assert.equal(lanes.length, 2);
  assert(lanes[0].includes('data-av-lane="earlier"'));
  assert(lanes[1].includes('data-av-lane="later"'));
  assert(lanes[0].includes('Same name · <code class="av-id">earlier</code>'));
  assert(lanes[1].includes('Same name · <code class="av-id">later</code>'));
  assert(lanes[0].includes(first.body));
  assert(!lanes[0].includes('Later outcome'));
  assert(lanes[1].includes(second.body));
  assert(!lanes[1].includes('Earlier outcome'));
  assert(lanes[0].includes('href="#earlier-record"'));
  assert(lanes[1].includes('Later scope'));
  assert(!/\sid="(?:earlier|later)"/.test(html));
  const reordered = laneBodies(S.comparisonLanes({ lanes: [second, first], sectionMode: 'solo' }));
  assert.equal(reordered[0], lanes[1]);
  assert.equal(reordered[1], lanes[0]);
  const spaced = S.comparisonLanes({ lanes: [{ ...first, label: 'Same  name' }, { ...second, label: '\nSame\tname ' }] });
  assert(spaced.includes('<code class="av-id">earlier</code>'));
  assert(spaced.includes('<code class="av-id">later</code>'));
  const unique = S.comparisonLanes({ lanes: [{ ...first, label: 'Earlier record' }, { ...second, label: 'Later record' }] });
  assert(!unique.includes('<code class="av-id">'));
  assert(!unique.includes('data-av-section-mode='));
  assert(S.comparisonLanes({ lanes: [first], sectionMode: 'multiple' }).includes('data-av-section-mode="multiple"'));
  assert.equal(S.comparisonLanes({ lanes: [] }), '<section class="av-comparison-lanes"></section>');
});

check('lanes escape metadata, preserve trusted composition and reject invalid identities or modes', () => {
  const id = '"><script>lane</script>', attack = '<img src=x onerror=alert(1)>';
  const body = '<article data-authored="retained"><p>Trusted author composition</p></article>';
  const html = S.comparisonLanes({ title: attack, description: attack, lanes: [{ id, label: attack, note: attack, body }] });
  assert(html.includes(`data-av-lane="${core.escapeText(id)}"`));
  assert(html.includes(body));
  assert(!html.includes('<script>'));
  assert(!html.includes('<img '));
  assert(!/\sid=/.test(html));
  for (const lanes of [[{ id: '', label: 'Empty', body }], [{ id: 'x', label: 'One', body }, { id: 'x', label: 'Two', body }]]) assert.throws(() => S.comparisonLanes({ lanes }), /nonempty and unique/);
  assert.throws(() => S.comparisonLanes({ lanes: [{ id: 'x', label: 'X', body: {} }] }), /trusted HTML/);
  assert.throws(() => S.comparisonLanes({ lanes: [], sectionMode: 'solo" onclick="x' }), /Use multiple or solo/);
});

check('reading choices retain author order, exact fragments and native navigation', () => {
  const routes = [
    { id: 'exceptions', label: 'Begin with limitations', description: 'See where a conclusion would fail.', href: '#report--view-unknowns' },
    { id: 'records', label: 'Inspect the retained cases', href: '#report--view-evidence.v2:retained_1' },
    { id: 'overview', label: 'Read the overall account', description: 'Then choose relevant evidence.', href: '#report--view-overview' },
  ];
  const html = S.readingGuide({ title: 'Choose where to begin', description: 'Different questions can start in different places.', routes });
  assert(html.startsWith('<nav class="av-reading-guide" aria-label="Choose where to begin">'));
  assert(html.includes('<ul><li><a class="av-route-choice"'));
  assert.equal((html.match(/<a /g) || []).length, 3);
  assert(!html.includes('<button'));
  assert(!html.includes('hidden'));
  assert(!html.includes('<ol>'));
  for (const route of routes) assert(html.includes(`data-av-start-journey="${route.id}" href="${route.href}"`));
  assert(html.indexOf('Begin with limitations') < html.indexOf('Inspect the retained cases'));
  assert(html.indexOf('Inspect the retained cases') < html.indexOf('Read the overall account'));
  assert(html.includes('See where a conclusion would fail.'));
  assert(!html.includes('Step 1'));
  assert.equal(S.readingGuide({ routes: [] }), '<nav class="av-reading-guide" aria-label="Reading guide"><ul></ul></nav>');
  assert(!S.readingGuide({ routes: [routes[1]] }).includes('av-route-description'));
});

check('reading choices escape hostile metadata and reject unsafe or ambiguous navigation', () => {
  const attack = key => `<svg onload="alert('${key}')">`, route = { id: 'review', label: 'Review', href: '#report--view-review' };
  const html = S.readingGuide({ title: attack('title'), description: attack('description'), routes: [{ ...route, id: attack('id'), label: attack('label'), description: attack('route-description') }] });
  assert(html.includes(`data-av-start-journey="${core.escapeText(attack('id'))}"`));
  assert(!html.includes('<svg'));
  for (const field of ['title', 'description', 'id', 'label', 'route-description']) assert(html.includes(core.escapeText(attack(field))), `text missing or unescaped: ${field}`);
  for (const href of ['', '#', 'javascript:alert(1)', 'https://example.com/#view', '//example.com/#view', '/#view', '#two words', '#view\n', '#view\r', '#view\u2028', '#view\u2029', '#view" onclick="alert(1)', '#view?x=1', '#view#child', '#%76iew', '#view%ZZ', '#1-view', '#視点', '#/view']) assert.throws(() => S.readingGuide({ routes: [{ ...route, href }] }), /same-document fragments/);
  for (const id of ['', ' \n\t', null, 1]) assert.throws(() => S.readingGuide({ routes: [{ ...route, id }] }), /IDs must be nonempty and unique/);
  for (const label of ['', ' \n\t', null, 1]) assert.throws(() => S.readingGuide({ routes: [{ ...route, label }] }), /labels must be nonempty and unique/);
  assert.throws(() => S.readingGuide({ routes: [route, { ...route, label: 'Different' }] }), /IDs must be nonempty and unique/);
  assert.throws(() => S.readingGuide({ routes: [route, { ...route, id: 'different' }] }), /labels must be nonempty and unique/);
  assert.throws(() => S.readingGuide({ routes: [{ ...route, label: 'Read the case' }, { ...route, id: 'other', label: '\nRead  the\tcase ' }] }), /labels must be nonempty and unique/);
});

console.log(`${checks} story contracts passed`);
