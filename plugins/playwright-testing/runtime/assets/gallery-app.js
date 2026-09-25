(() => {
  'use strict';
  const data = globalThis.__evidence;
  const el = id => document.getElementById(id);
  const node = (tag, text, className) => { const value = document.createElement(tag); if (text !== undefined) value.textContent = text; if (className) value.className = className; return value; };
  const viewport = record => { const value = record.state?.viewport; return value ? `${value.width} × ${value.height}` : 'Unspecified'; };
  const pageName = record => record.state?.url || record.state?.report || record.state?.view || 'Other observations';
  const scheme = record => record.state?.observedPreferences?.colorScheme || record.state?.scheme || record.state?.colorScheme || 'Unspecified';
  const populate = (id, values) => { for (const value of [...new Set(values)].sort()) { const option = node('option', value); option.value = value; el(id).append(option); } };
  populate('type', data.records.map(record => record.type));
  populate('viewport', data.records.map(viewport));
  populate('scheme', data.records.map(scheme));
  el('summary').textContent = `${data.records.length.toLocaleString()} observations · ${data.summary.imageReferences.toLocaleString()} image references · ${data.summary.uniqueImages.toLocaleString()} distinct image${data.summary.uniqueImages === 1 ? '' : 's'}`;
  if (data.pendingTasks.length) { el('pending').hidden = false; el('pending-title').textContent = `${data.pendingTasks.length} pending task${data.pendingTasks.length === 1 ? '' : 's'}`; el('pending-context').textContent = JSON.stringify(data.pendingTasks, null, 2); }
  const pageSize = 24;
  let page = 0;
  function imageCard(record) {
    const card = node('article', undefined, 'card');
    const heading = node('header');
    heading.append(node('p', `${record.type}${record.status ? ` · ${record.status}` : ''}`, 'eyebrow'));
    const title = node('h3'); const detail = node('a', record.label); detail.href = record.detail; title.append(detail); heading.append(title);
    heading.append(node('p', `${viewport(record)} · ${scheme(record)}`, 'muted'));
    card.append(heading);
    const images = record.images.filter(ref => ref.displayable);
    const preview = node('div', undefined, 'image-strip');
    for (const [index, ref] of images.slice(0, 4).entries()) {
      const link = node('a'); link.href = record.detail;
      const image = node('img'); image.src = `../${ref.path}`; image.alt = `${record.label} — ${ref.side || `image ${index + 1}`}`; image.loading = 'lazy'; image.decoding = 'async'; link.append(image);
      if (ref.side) link.append(node('span', ref.side, 'image-label'));
      preview.append(link);
    }
    if (images.length) card.append(preview);
    const footer = node('footer'); const context = node('a', images.length > 4 ? `All ${images.length} images and context` : 'Reproduction and full context'); context.href = record.detail; footer.append(context);
    footer.append(node('span', record.id, 'identity')); card.append(footer);
    return card;
  }
  function render() {
    const query = el('search').value.toLocaleLowerCase().trim();
    const type = el('type').value, width = el('viewport').value, appearance = el('scheme').value, group = el('group').value;
    const filtered = data.records.filter(record => (!query || record.search.toLocaleLowerCase().includes(query)) && (!type || record.type === type) && (!width || viewport(record) === width) && (!appearance || scheme(record) === appearance));
    const groupKey = record => group === 'page' ? pageName(record) : group === 'viewport' ? viewport(record) : group === 'type' ? record.type : 'Observations';
    const ordered = group === 'none' ? filtered : [...filtered].sort((a, b) => groupKey(a).localeCompare(groupKey(b)));
    const pages = Math.max(1, Math.ceil(ordered.length / pageSize)); page = Math.max(0, Math.min(page, pages - 1));
    el('previous').disabled = page === 0; el('next').disabled = page === pages - 1; el('page-number').textContent = `${page + 1} / ${pages}`;
    el('result-count').textContent = `${filtered.length.toLocaleString()} matching observation${filtered.length === 1 ? '' : 's'}`;
    el('empty').hidden = !!filtered.length;
    const fragment = document.createDocumentFragment();
    let previous, grid;
    for (const record of ordered.slice(page * pageSize, (page + 1) * pageSize)) {
      const groupName = groupKey(record);
      if (groupName !== previous) { const section = node('section', undefined, 'group'); section.append(node('h2', groupName)); grid = node('div', undefined, 'grid'); section.append(grid); fragment.append(section); previous = groupName; }
      grid.append(imageCard(record));
    }
    el('results').replaceChildren(fragment);
  }
  for (const id of ['search', 'type', 'viewport', 'scheme', 'group']) el(id).addEventListener(id === 'search' ? 'input' : 'change', () => { page = 0; render(); });
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
  render();
})();
