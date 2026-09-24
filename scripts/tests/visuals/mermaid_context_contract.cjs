// Inheritance/lifecycle model only. No native renderer or browser is invoked.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const vm = require('node:vm');
const compiled = process.argv[2];
const { attachMermaid } = require(path.join(compiled, 'mermaid.js'));
const { fixture, V, append } = require(path.resolve(__dirname,
  '../../../plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/tests/parsed-dom-fixture.cjs'));

(async () => {
  const { d, parse } = fixture();
  const inherited = new Set(['color', 'font-family', 'font-size', 'letter-spacing', 'direction']);
  d.defaultView.getComputedStyle = element => {
    const values = { color: '#112233', 'font-family': 'Fixture Sans', 'font-size': '16px', direction: 'ltr' };
    const lineage = [];
    for (let owner = element; owner; owner = owner.parentElement) lineage.unshift(owner);
    for (const owner of lineage) {
      for (const declaration of (owner.getAttribute('style') || '').split(';')) {
        const colon = declaration.indexOf(':');
        if (colon < 0) continue;
        const key = declaration.slice(0, colon).trim(), value = declaration.slice(colon + 1).trim();
        if (owner === element || key.startsWith('--') || inherited.has(key)) values[key] = value;
      }
    }
    const names = Object.keys(values);
    return { ...names, length: names.length, fontFamily: values['font-family'], color: values.color,
      getPropertyValue: name => values[name] || '' };
  };
  const calls = [], configurations = [];
  let sourceConfig = {};
  d.defaultView.mermaid = {
    initialize(config) { configurations.push(config); },
    async parse() { return { config: sourceConfig }; },
    async render(id, source, container) {
      assert.equal(container.parentElement, d.body, 'Hidden figures still render in a measurable host');
      const style = d.defaultView.getComputedStyle(container);
      assert.notEqual(style.getPropertyValue('display'), 'none', 'Report visibility cannot hide the staging scene');
      calls.push(Object.fromEntries(['--av-line-strong', '--author-outline', 'font-size', 'letter-spacing', 'direction']
        .map(name => [name, style.getPropertyValue(name)])));
      return { svg: `<svg id="${id}" viewBox="0 0 200 100" width="200" height="100"><text>Evidence</text></svg>` };
    },
    getRegisteredDiagramsMetadata() { return []; },
  };
  const host = append(d.body, 'section', { style: 'display:none;--av-line-strong:#123456;--author-outline:#abcdef;font-size:22px;letter-spacing:1px;direction:rtl' });
  host.appendChild(parse(V.mermaidDiagram({ id: 'themed', title: 'Scoped theme', source: 'flowchart LR\n A --> B' })).firstChild);
  const controller = attachMermaid(host, () => {});
  await controller.refresh();
  assert.deepEqual(calls[0], { '--av-line-strong': '#123456', '--author-outline': '#abcdef', 'font-size': '22px', 'letter-spacing': '1px', direction: 'rtl' },
    'Rendering receives effective report theme and typography, including arbitrary author properties');
  await controller.refresh();
  assert.equal(calls.length, 1, 'Identical inherited styles do not rerender');
  host.style.setProperty('--author-outline', '#fedcba');
  await controller.refresh();
  assert.equal(calls.length, 2, 'A theme variable outside the built-in palette invalidates the drawing');
  assert.equal(calls[1]['--author-outline'], '#fedcba');
  host.style.removeProperty('--author-outline');
  await controller.refresh();
  assert.equal(calls[2]['--author-outline'], '', 'Removed author roles do not survive in staging');

  const sibling = append(d.body, 'section', { style: '--av-line-strong:#654321;font-size:18px' });
  sibling.appendChild(parse(V.mermaidDiagram({ id: 'sibling', title: 'Independent report', source: 'flowchart LR\n A --> B' })).firstChild);
  const other = attachMermaid(sibling, () => {});
  await other.refresh();
  assert.deepEqual(calls[3], { '--av-line-strong': '#654321', '--author-outline': '', 'font-size': '18px', 'letter-spacing': '', direction: 'ltr' },
    'Independent reports retain separate inherited styles');
  assert.equal(d.querySelectorAll('[data-av-mermaid-staging]').length, 0);
  controller.cleanup(); other.cleanup();

  // Ask the pinned runtime to derive its theme variables, without parsing or
  // rendering a diagram. A report default must not change an authored palette's
  // derived secondary/edge colors or override an explicit native theme.
  const context = vm.createContext({ console: { log() {}, warn() {}, error() {} }, structuredClone, setTimeout, clearTimeout });
  vm.runInContext(fs.readFileSync(path.resolve(__dirname,
    '../../../plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js'), 'utf8'), context, { timeout: 10000 });
  const runtime = context.mermaid;
  const derived = config => {
    runtime.initialize({ startOnLoad: false, ...config });
    const theme = runtime.mermaidAPI.getConfig().themeVariables;
    return Object.fromEntries(['primaryColor', 'primaryTextColor', 'secondaryColor', 'tertiaryColor', 'edgeLabelBackground'].map(name => [name, theme[name]]));
  };
  for (const mode of ['options', 'source']) for (const author of [
    { theme: 'base', themeVariables: { primaryColor: '#123456', primaryTextColor: '#ffffff', primaryBorderColor: '#90b7d8', lineColor: '#345678' } },
    { themeVariables: { primaryColor: '#123456', primaryTextColor: '#ffffff', edgeLabelBackground: '#223344' } },
    { theme: 'dark' },
  ]) {
    sourceConfig = mode === 'source' ? author : {};
    const custom = append(d.body, 'section');
    custom.appendChild(parse(V.mermaidDiagram({ title: 'Authored palette', source: 'flowchart LR\n A --> B', ...(mode === 'options' ? { config: author } : {}) })).firstChild);
    const adapter = attachMermaid(custom, () => {});
    await adapter.refresh();
    const initialized = configurations.at(-1);
    const actual = derived({ ...initialized, ...sourceConfig,
      themeVariables: { ...initialized.themeVariables, ...sourceConfig.themeVariables } });
    assert.deepEqual(actual, derived({ theme: 'base', ...author }),
      `Report defaults must preserve native theme derivation for ${mode} overrides`);
    adapter.cleanup(); custom.remove();
  }
  sourceConfig = { themeVariables: { fontFamily: 'Author Sans' } };
  const typographyOnly = append(d.body, 'section');
  typographyOnly.appendChild(parse(V.mermaidDiagram({ title: 'Typography only', source: 'flowchart LR\n A --> B' })).firstChild);
  const typography = attachMermaid(typographyOnly, () => {});
  await typography.refresh();
  assert(configurations.at(-1).themeVariables.primaryColor, 'A font override still receives the report color palette');
  typography.cleanup(); typographyOnly.remove();
  console.log('Mermaid context contract passed: scoped theme/typography, hidden figures, cache invalidation, independent ownership and native authored palette derivation.');
})().catch(error => { console.error(error); process.exitCode = 1; });
