(() => {
  'use strict';
  const data = globalThis.__evidence;
  const el = id => document.getElementById(id);
  const node = (tag, text, className) => { const value = document.createElement(tag); if (text !== undefined) value.textContent = text; if (className) value.className = className; return value; };
  const viewport = record => { const value = record.state?.viewport; return value && Number.isFinite(value.width) && Number.isFinite(value.height) ? `${value.width} × ${value.height}` : ''; };
  const pageName = record => record.state?.url || record.state?.report || record.state?.view || 'Other observations';
  const scheme = record => record.state?.observedPreferences?.colorScheme || record.state?.scheme || record.state?.colorScheme || '';
  const typeName = value => value.replace(/[-_]+/g, ' ').replace(/^./u, character => character.toLocaleUpperCase());
  const imagesOf = record => record.images.filter(ref => ref.displayable);
  const isCapture = record => ['capture', 'capture-progress'].includes(record.type) || imagesOf(record).length > 0;
  const captureCount = data.records.filter(isCapture).length;
  const supportingCount = data.records.length - captureCount;
  let view = captureCount ? 'captures' : 'records', page = 0;
  const layoutKey = `browser-evidence:layout:${data.run.id}`;
  let captureLayout = 'flow';
  try { const saved = localStorage.getItem(layoutKey); if (['flow', 'contact'].includes(saved)) captureLayout = saved; } catch { /* The current page still has a working layout choice. */ }
  el('layout').value = captureLayout;
  let layoutFrame;
  const observedWidths = new WeakMap();
  const flowObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(entries => {
    if (entries.some(entry => {
      if (!entry.target.classList.contains('grid')) return true;
      const width = entry.contentRect.width, changed = observedWidths.get(entry.target) !== width;
      observedWidths.set(entry.target, width); return changed;
    })) scheduleFlow();
  }) : null;
  function scheduleFlow() {
    if (layoutFrame) return;
    layoutFrame = requestAnimationFrame(() => { layoutFrame = null; arrangeFlow(); });
  }
  function arrangeFlow() {
    for (const grid of document.querySelectorAll('.grid[data-layout="flow"]')) {
      const width = grid.getBoundingClientRect().width;
      const style = getComputedStyle(grid), columns = Number(style.getPropertyValue('--columns')) || 1, gap = Number.parseFloat(style.columnGap) || 22;
      if (!width) continue;
      const columnWidth = (width - gap * (columns - 1)) / columns;
      grid.style.setProperty('--flow-width', `${columnWidth}px`);
      const heights = Array(columns).fill(0);
      const positions = [...grid.children].map(card => {
        const column = heights.indexOf(Math.min(...heights));
        const point = { card, left: column * (columnWidth + gap), top: heights[column] };
        heights[column] += card.getBoundingClientRect().height + gap;
        return point;
      });
      for (const { card, left, top } of positions) { card.style.left = `${left}px`; card.style.top = `${top}px`; }
      grid.style.height = `${Math.max(0, ...heights) - (positions.length ? gap : 0)}px`;
    }
  }
  function updateLayout() {
    flowObserver?.disconnect();
    for (const grid of document.querySelectorAll('.grid')) {
      grid.dataset.layout = captureLayout;
      if (captureLayout === 'flow') { flowObserver?.observe(grid); for (const card of grid.children) flowObserver?.observe(card); }
      else { grid.style.height = ''; for (const card of grid.children) { card.style.left = ''; card.style.top = ''; } }
    }
    arrangeFlow();
  }
  window.addEventListener('resize', scheduleFlow);
  const pageSize = 24;
  el('view-captures').textContent = `Captures (${captureCount.toLocaleString()})`;
  el('view-records').textContent = `Supporting records (${supportingCount.toLocaleString()})`;
  el('summary').textContent = `${captureCount.toLocaleString()} captures · ${supportingCount.toLocaleString()} supporting records · ${data.summary.imageReferences.toLocaleString()} image references · ${data.summary.uniqueImages.toLocaleString()} distinct image${data.summary.uniqueImages === 1 ? '' : 's'}`;
  if (data.pendingTasks.length) { el('pending').hidden = false; el('pending-title').textContent = `${data.pendingTasks.length} pending task${data.pendingTasks.length === 1 ? '' : 's'}`; el('pending-context').textContent = JSON.stringify(data.pendingTasks, null, 2); }
  const inView = record => isCapture(record) === (view === 'captures');
  function populate(id, values) {
    const select = el(id), previous = select.value;
    while (select.options.length > 1) select.remove(1);
    for (const value of [...new Set(values.filter(Boolean))].sort()) { const option = node('option', id === 'type' ? typeName(value) : value); option.value = value; select.append(option); }
    select.value = [...select.options].some(option => option.value === previous) ? previous : '';
  }
  function metadata(record) { return [viewport(record), scheme(record)].filter(Boolean).join(' · '); }
  function imageCard(record) {
    const card = node('article', undefined, 'card');
    const heading = node('header');
    heading.append(node('p', `${typeName(record.type)}${record.status ? ` · ${record.status}` : ''}`, 'eyebrow'));
    const title = node('h3'); const detail = node('a', record.label); detail.href = record.detail; title.append(detail); heading.append(title);
    const context = metadata(record); if (context) heading.append(node('p', context, 'muted'));
    card.append(heading);
    const images = imagesOf(record);
    let imageIndex = 0, previewLink, image;
    if (images.length) {
      previewLink = node('a', undefined, 'image-preview'); previewLink.href = record.detail;
      const shapes = images.map(ref => ref.dimensions).filter(shape => shape?.width > 0 && shape?.height > 0);
      if (shapes.length === images.length) previewLink.style.setProperty('--capture-ratio', String(1 / shapes.reduce((largest, shape) => Math.max(largest, shape.height / shape.width), 0)));
      image = node('img'); image.loading = 'lazy'; image.decoding = 'async'; previewLink.append(image); card.append(previewLink);
      image.addEventListener('load', () => {
        if (images.length === 1 && shapes.length === 0 && image.naturalWidth && image.naturalHeight) previewLink.style.setProperty('--capture-ratio', String(image.naturalWidth / image.naturalHeight));
        scheduleFlow();
      });
    } else card.append(node('p', 'No image was retained. Open the context for the capture result.', 'capture-empty'));
    const footer = node('footer');
    const original = node('a', images.length > 1 ? `All ${images.length} images and context` : 'Reproduction and full context'); original.href = record.detail; footer.append(original);
    let previous, next, position;
    if (images.length > 1) {
      const navigation = node('div', undefined, 'frame-navigation');
      navigation.setAttribute('role', 'group'); navigation.setAttribute('aria-label', `Images for ${record.label}`);
      previous = node('button', '←'); previous.type = 'button'; previous.setAttribute('aria-label', `Previous image for ${record.label}`);
      next = node('button', '→'); next.type = 'button'; next.setAttribute('aria-label', `Next image for ${record.label}`);
      position = node('span'); position.setAttribute('aria-live', 'polite');
      previous.addEventListener('click', () => { imageIndex = Math.max(0, imageIndex - 1); updateImage(); });
      next.addEventListener('click', () => { imageIndex = Math.min(images.length - 1, imageIndex + 1); updateImage(); });
      navigation.append(previous, position, next); footer.append(navigation);
    }
    function updateImage() {
      const ref = images[imageIndex]; image.src = `../${ref.path}`;
      image.alt = `${record.label} — ${ref.side || `image ${imageIndex + 1} of ${images.length}`}`;
      previewLink.setAttribute('aria-label', `Open ${record.label}, ${ref.side || `image ${imageIndex + 1} of ${images.length}`}`);
      previewLink.href = `${record.detail}#image-${record.images.indexOf(ref) + 1}`;
      if (position) { position.textContent = `${imageIndex + 1} / ${images.length}`; previous.disabled = imageIndex === 0; next.disabled = imageIndex === images.length - 1; }
    }
    if (images.length) updateImage();
    card.append(footer); return card;
  }
  function supportingRecord(record) {
    const row = node('article', undefined, 'observation-row');
    const content = node('div');
    content.append(node('p', `${typeName(record.type)}${record.status ? ` · ${record.status}` : ''}`, 'eyebrow'));
    const heading = node('h3'), link = node('a', record.label); link.href = record.detail; heading.append(link); content.append(heading);
    if (record.summary) content.append(node('p', record.summary, 'record-summary'));
    const context = metadata(record); if (context) content.append(node('p', context, 'muted'));
    const original = node('a', 'Open record', 'record-link'); original.href = record.detail; original.setAttribute('aria-label', `Open record: ${record.label}`);
    row.append(content, original); return row;
  }
  function setView(nextView) {
    view = nextView; page = 0;
    const records = data.records.filter(inView);
    populate('type', records.map(record => record.type)); populate('viewport', records.map(viewport)); populate('scheme', records.map(scheme));
    el('view-captures').setAttribute('aria-pressed', String(view === 'captures'));
    el('view-records').setAttribute('aria-pressed', String(view === 'records'));
    el('layout-control').hidden = view !== 'captures';
    render();
  }
  function render() {
    const query = el('search').value.toLocaleLowerCase().trim();
    const type = el('type').value, width = el('viewport').value, appearance = el('scheme').value, group = el('group').value;
    const matching = record => (!query || record.search.toLocaleLowerCase().includes(query)) && (!type || record.type === type) && (!width || viewport(record) === width) && (!appearance || scheme(record) === appearance);
    const filtered = data.records.filter(record => inView(record) && matching(record));
    const opposite = query ? data.records.filter(record => !inView(record) && record.search.toLocaleLowerCase().includes(query)).length : 0;
    el('other-matches').hidden = opposite === 0;
    el('show-other-matches').textContent = `Search ${view === 'captures' ? 'supporting records' : 'captures'} (${opposite.toLocaleString()} match${opposite === 1 ? '' : 'es'})`;
    const groupKey = record => group === 'page' ? pageName(record) : group === 'viewport' ? viewport(record) || 'Without viewport metadata' : group === 'type' ? typeName(record.type) : view === 'captures' ? 'Captures' : 'Supporting records';
    const ordered = group === 'none' ? filtered : [...filtered].sort((a, b) => groupKey(a).localeCompare(groupKey(b)));
    const pages = Math.max(1, Math.ceil(ordered.length / pageSize)); page = Math.max(0, Math.min(page, pages - 1));
    el('previous').disabled = page === 0; el('next').disabled = page === pages - 1; el('page-number').textContent = `${page + 1} / ${pages}`;
    el('result-count').textContent = `${filtered.length.toLocaleString()} matching ${view === 'captures' ? 'capture' : 'record'}${filtered.length === 1 ? '' : 's'}`;
    el('empty').hidden = !!filtered.length;
    const fragment = document.createDocumentFragment();
    let previous, grid;
    for (const record of ordered.slice(page * pageSize, (page + 1) * pageSize)) {
      const groupName = groupKey(record);
      if (groupName !== previous) { const section = node('section', undefined, 'group'); section.append(node('h2', groupName)); grid = node('div', undefined, view === 'captures' ? 'grid' : 'record-list'); section.append(grid); fragment.append(section); previous = groupName; }
      grid.append(view === 'captures' ? imageCard(record) : supportingRecord(record));
    }
    el('results').replaceChildren(fragment);
    updateLayout();
  }
  for (const id of ['search', 'type', 'viewport', 'scheme', 'group']) el(id).addEventListener(id === 'search' ? 'input' : 'change', () => { page = 0; render(); });
  el('view-captures').addEventListener('click', () => setView('captures'));
  el('view-records').addEventListener('click', () => setView('records'));
  el('layout').addEventListener('change', () => {
    captureLayout = el('layout').value;
    try { localStorage.setItem(layoutKey, captureLayout); } catch { /* Saving preferences is optional. */ }
    updateLayout();
  });
  el('show-other-matches').addEventListener('click', () => { for (const id of ['type', 'viewport', 'scheme']) el(id).value = ''; setView(view === 'captures' ? 'records' : 'captures'); el('results').focus(); });
  el('previous').addEventListener('click', () => { page -= 1; render(); el('results').focus(); });
  el('next').addEventListener('click', () => { page += 1; render(); el('results').focus(); });
  let appearance = 0;
  el('appearance').addEventListener('click', () => { appearance = (appearance + 1) % 3; const value = ['system', 'light', 'dark'][appearance]; document.documentElement.dataset.appearance = value; el('appearance').textContent = `Appearance: ${value}`; });
  if (data.transitions.length) {
    el('map').hidden = false;
    const labels = new Map(data.records.map(record => [record.id, record.label]));
    const descriptions = data.transitions.map(transition => ({ ...transition, fromLabel: labels.get(transition.from) || String(transition.from ?? 'Unknown state'), toLabel: labels.get(transition.to) || String(transition.to ?? 'Unknown state') }));
    for (const transition of descriptions) { const li = node('li'); li.append(node('span', `${transition.fromLabel} → ${transition.toLabel}: `)); const a = node('a', typeof transition.action === 'string' ? transition.action : JSON.stringify(transition.action)); a.href = transition.detail; li.append(a); el('transition-list').append(li); }
    // A compact observed map stays legible; the full transition list is always retained.
    if (descriptions.length <= 30) {
      const identity = value => typeof value === 'string' ? value : JSON.stringify(value ?? 'Unknown state');
      const states = [...new Set(descriptions.flatMap(transition => [identity(transition.from), identity(transition.to)]))];
      const glyphs = value => globalThis.Intl?.Segmenter ? [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(value)].map(part => part.segment) : Array.from(value);
      const wrap = value => { const characters = glyphs(value), lines = []; for (let i = 0; i < characters.length; i += 35) lines.push(characters.slice(i, i + 35).join('')); return lines.length ? lines : ['Unknown state']; };
      let bottom = 12;
      const positions = new Map(states.map((state, i) => { const lines = wrap(labels.get(state) || state); const position = { x: i % 2 ? 430 : 20, y: bottom, lines, height: lines.length * 18 + 20 }; bottom += position.height + 24; return [state, position]; }));
      const svgNS = 'http://www.w3.org/2000/svg'; const svg = document.createElementNS(svgNS, 'svg');
      svg.setAttribute('viewBox', `0 0 760 ${Math.max(100, bottom)}`); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'Observed state transitions; complete descriptions follow');
      const defs = document.createElementNS(svgNS, 'defs'); const marker = document.createElementNS(svgNS, 'marker'); marker.setAttribute('id', 'observed-arrow'); marker.setAttribute('viewBox', '0 0 10 10'); marker.setAttribute('refX', '9'); marker.setAttribute('refY', '5'); marker.setAttribute('markerWidth', '7'); marker.setAttribute('markerHeight', '7'); marker.setAttribute('orient', 'auto'); const arrow = document.createElementNS(svgNS, 'path'); arrow.setAttribute('d', 'M0,0 L10,5 L0,10 z'); arrow.setAttribute('class', 'arrow'); marker.append(arrow); defs.append(marker); svg.append(defs);
      for (const transition of descriptions) { const a = positions.get(identity(transition.from)), b = positions.get(identity(transition.to)); const line = document.createElementNS(svgNS, 'path'); line.setAttribute('d', `M${a.x + 150},${a.y + a.height} C380,${a.y + a.height + 20} 380,${b.y - 20} ${b.x + 150},${b.y}`); line.setAttribute('class', 'edge'); line.setAttribute('marker-end', 'url(#observed-arrow)'); svg.append(line); }
      for (const [state, position] of positions) { const g = document.createElementNS(svgNS, 'g'); const rect = document.createElementNS(svgNS, 'rect'); rect.setAttribute('x', position.x); rect.setAttribute('y', position.y); rect.setAttribute('width', 300); rect.setAttribute('height', position.height); rect.setAttribute('rx', 8); const text = document.createElementNS(svgNS, 'text'); for (const [i, line] of position.lines.entries()) { const span = document.createElementNS(svgNS, 'tspan'); span.setAttribute('x', position.x + 12); span.setAttribute('y', position.y + 23 + i * 18); span.textContent = line; text.append(span); } const title = document.createElementNS(svgNS, 'title'); title.textContent = `${labels.get(state) || state} (${state})`; g.append(rect, text, title); svg.append(g); }
      el('transition-map').append(svg);
    }
  }
  setView(view);
})();
