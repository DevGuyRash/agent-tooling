// Adapter failure/recovery model. The native parser and renderer are not invoked.
const assert = require('node:assert/strict');
const path = require('node:path');
const { attachMermaid } = require(path.join(process.argv[2], 'mermaid.js'));
const { exportFigureSvg } = require(path.join(process.argv[2], 'figure-export.js'));
const { fixture, V, append } = require(path.resolve(__dirname,
  '../../../plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/tests/parsed-dom-fixture.cjs'));

(async () => {
  const { d, parse } = fixture();
  const root = append(d.body, 'main');
  const make = (id, source) => {
    const host = append(root, 'section');
    host.appendChild(parse(V.mermaidDiagram({ id, title: id, source })).firstChild);
    return { host, element: host.querySelector('[data-av-mermaid]'), status: host.querySelector('[data-av-mermaid-status]'), output: host.querySelector('[data-av-mermaid-output]') };
  };
  const sourceFailure = make('parse-failure', 'unparseable source'), renderFailure = make('render-failure', 'renderer failure'), good = make('valid-neighbor', 'valid source');
  let release = null;
  const priorPostprocessor = async graph => graph;
  let postprocessor = priorPostprocessor;
  const priorArchitectureRouter = input => input;
  let architectureRouter = priorArchitectureRouter;
  const rendered = [];
  d.defaultView.mermaid = {
    setElkLayoutPostprocessor(next) { const prior = postprocessor; postprocessor = next; return prior; },
    setArchitectureRouter(next) { const prior = architectureRouter; architectureRouter = next; return prior; },
    initialize() {},
    async parse(source) {
      if (source === 'unparseable source') throw new Error('<b>Malformed input</b>');
      return { config: {} };
    },
    async render(id, source, staging) {
      assert.equal(typeof postprocessor, 'function');
      assert.notEqual(postprocessor, priorPostprocessor, 'Rendering owns a scoped layout repair');
      assert.equal(typeof architectureRouter, 'function');
      assert.notEqual(architectureRouter, priorArchitectureRouter, 'Rendering owns scoped architecture routing');
      rendered.push(source);
      if (source === 'renderer failure') {
        append(staging, 'div', { 'data-renderer-partial': '' }, 'Partial output');
        throw new Error('Renderer failed to route the relationship');
      }
      if (source === 'delayed source') await new Promise(resolve => { release = resolve; });
      return { svg: `<svg id="${id}" viewBox="0 0 200 100" width="200" height="100"><text>Retained diagram</text></svg>` };
    },
    getRegisteredDiagramsMetadata() { return []; },
  };
  const controller = attachMermaid(root, () => {});
  await controller.refresh();
  assert.equal(postprocessor, priorPostprocessor, 'A renderer failure or success restores the prior layout processor');
  assert.equal(architectureRouter, priorArchitectureRouter, 'A renderer failure or success restores prior architecture routing');
  for (const failed of [sourceFailure, renderFailure]) {
    assert.equal(failed.element.getAttribute('data-av-mermaid-state'), 'error');
    assert.equal(failed.element.hasAttribute('aria-busy'), false, 'A settled failure cannot remain busy');
    assert(failed.output.hidden, 'Partial/stale output cannot masquerade as a successful new scene');
    assert.match(failed.status.textContent, /Original source remains available/);
    assert.equal(failed.host.querySelector('.av-diagram-source').querySelector('code').textContent, failed.element.getAttribute('data-av-mermaid-source'), 'Failure retains exact source');
    await assert.rejects(exportFigureSvg(failed.host.querySelector('[data-av-figure]')), /not ready for image export/);
  }
  assert.match(sourceFailure.status.textContent, /<b>Malformed input<\/b>/);
  assert.equal(sourceFailure.status.querySelector('b'), null, 'Diagnostic text is not inserted as markup');
  assert.equal(good.element.getAttribute('data-av-mermaid-state'), 'ready', 'Earlier parse and renderer errors do not block a valid neighbor');
  assert.deepEqual(rendered, ['renderer failure', 'valid source']);
  assert.equal(d.querySelectorAll('[data-av-mermaid-staging],[data-renderer-partial]').length, 0, 'Failed renderer staging is removed');

  sourceFailure.element.setAttribute('data-av-mermaid-source', 'corrected source');
  renderFailure.element.setAttribute('data-av-mermaid-source', 'corrected relationship');
  await controller.refresh();
  for (const fixed of [sourceFailure, renderFailure]) {
    assert.equal(fixed.element.getAttribute('data-av-mermaid-state'), 'ready', 'Corrected input can recover without reloading the report');
    assert.equal(fixed.status.textContent, '');
    assert.equal(fixed.output.hidden, false);
  }

  good.element.setAttribute('data-av-mermaid-source', 'delayed source');
  const waiting = controller.refresh();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(good.element.getAttribute('data-av-mermaid-state'), 'pending');
  assert.equal(good.element.getAttribute('aria-busy'), 'true');
  assert.match(good.status.textContent, /Preparing diagram/);
  assert.equal(typeof release, 'function'); release(); await waiting; await controller.whenIdle();
  assert.equal(good.element.getAttribute('data-av-mermaid-state'), 'ready');
  assert.equal(good.status.textContent, '', 'Settled work clears the loading message');
  assert.equal(postprocessor, priorPostprocessor, 'An asynchronous render restores processor ownership on completion');
  assert.equal(architectureRouter, priorArchitectureRouter, 'An asynchronous render restores architecture routing ownership');

  good.element.setAttribute('data-av-mermaid-config', '{malformed');
  await controller.refresh();
  assert.equal(good.element.getAttribute('data-av-mermaid-state'), 'error');
  assert(good.output.hidden, 'An invalid changed configuration does not present the previous SVG as current');
  good.element.removeAttribute('data-av-mermaid-config');
  await controller.refresh();
  assert.equal(good.element.getAttribute('data-av-mermaid-state'), 'ready', 'Restoring an accepted configuration recovers its scene');
  assert.equal(d.querySelectorAll('[data-av-mermaid-staging]').length, 0);
  controller.cleanup();
  console.log('Mermaid failure contract passed: isolated errors, exact source, safe diagnostics, export refusal, queue continuation and corrected-input recovery.');
})().catch(error => { console.error(error); process.exitCode = 1; });
