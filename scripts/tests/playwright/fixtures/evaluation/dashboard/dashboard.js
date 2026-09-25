(async () => {
  const pageId = crypto.randomUUID();
  const event = (action, data = {}) => fetch('/api/events', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ action, pageId, ...data }) }).catch(() => {});
  const database = await new Promise((resolve, reject) => {
    const request = indexedDB.open('fielddesk-auth', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('sessions');
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
  });
  const readSession = () => new Promise((resolve, reject) => { const request = database.transaction('sessions').objectStore('sessions').get('active'); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
  const saveSession = value => new Promise((resolve, reject) => { const transaction = database.transaction('sessions', 'readwrite'); const store = transaction.objectStore('sessions'); if (value) store.put(value, 'active'); else store.delete('active'); transaction.oncomplete = resolve; transaction.onerror = () => reject(transaction.error); });
  let session = await readSession(), assets = [], filtered = [], selected, pulseTimer;
  const api = async (path, options = {}) => {
    const response = await fetch(path, { ...options, headers: { 'content-type': 'application/json', 'x-demo-session': session?.token ?? '', ...options.headers } });
    const result = await response.json(); if (!response.ok) throw new Error(result.error); return result;
  };
  const team = document.querySelector('#team'), search = document.querySelector('#filter'), scroller = document.querySelector('#asset-scroll'), list = document.querySelector('#asset-list');
  const teamName = () => team.selectedOptions[0].textContent;
  function renderRows() {
    list.style.height = `${filtered.length * 58}px`; list.replaceChildren();
    const start = Math.max(0, Math.floor(scroller.scrollTop / 58) - 1), end = Math.min(filtered.length, start + Math.ceil(scroller.clientHeight / 58) + 2);
    for (let i = start; i < end; i += 1) {
      const asset = filtered[i], row = document.createElement('div'); row.className = 'asset-row'; row.dataset.assetId = asset.id; row.style.top = `${i * 58}px`;
      for (const [text, className] of [[asset.name, 'name'], [asset.id, 'asset-id'], [asset.site, 'site'], [asset.status, 'pill']]) { const span = document.createElement('span'); span.className = className; span.textContent = text; row.append(span); }
      const details = document.createElement('button'); details.textContent = 'Details'; details.addEventListener('click', () => openDetails(asset.id)); row.append(details); list.append(row);
    }
  }
  function applyFilter() {
    const query = search.value.trim().toLocaleLowerCase();
    filtered = assets.filter(asset => [asset.name, asset.id, asset.site].some(value => value.toLocaleLowerCase().includes(query)));
    scroller.scrollTop = 0; document.querySelector('#count').textContent = `${filtered.length} devices`; renderRows();
  }
  async function loadTeam() {
    scroller.setAttribute('aria-busy', 'true'); assets = await api(`/api/assets?team=${team.value}`); applyFilter(); scroller.setAttribute('aria-busy', 'false');
  }
  async function openDetails(id) {
    const asset = await api(`/api/assets/${id}`); selected = asset;
    document.querySelector('#detail-title').textContent = asset.name;
    document.querySelector('#detail-context').textContent = `${teamName()} · ${asset.id}`;
    const fields = [['Asset ID', asset.id], ['Team', teamName()], ['Owner', asset.owner], ['Management address', asset.address]];
    if (asset.retentionDays) fields.push(['Retention days', String(asset.retentionDays)]);
    const content = document.querySelector('#detail-fields'); content.replaceChildren();
    for (const [label, value] of fields) { const term = document.createElement('dt'), detail = document.createElement('dd'); term.textContent = label; detail.textContent = value; content.append(term, detail); }
    document.querySelector('#asset-detail').showModal(); event('detail-open', { id, team: team.value });
  }
  document.querySelector('#close-detail').addEventListener('click', () => { document.querySelector('#asset-detail').close(); event('detail-close', { id: selected.id }); });
  document.querySelector('#archive').addEventListener('click', async () => {
    if (confirm(`Archive ${selected.name} (${selected.id})?`)) { await api(`/api/assets/${selected.id}/archive`, { method: 'POST' }); document.querySelector('#asset-detail').close(); await loadTeam(); }
  });
  scroller.addEventListener('scroll', renderRows);
  search.addEventListener('input', () => { applyFilter(); event('filter-change', { team: team.value, value: search.value }); });
  team.addEventListener('change', async () => { event('team-change', { team: team.value }); await loadTeam(); });
  async function showWorkspace(restored) {
    const identity = await api('/api/me'); document.querySelector('#account').textContent = identity.displayName;
    document.querySelector('#login').hidden = true; document.querySelector('#workspace').hidden = false; document.querySelector('#sign-out').hidden = false;
    if (restored) event('session-restored');
    await loadTeam();
    pulseTimer = setInterval(() => api('/api/pulse').then(result => { document.querySelector('#pulse').textContent = `${result.message} · update ${result.tick}`; }).catch(() => {}), 220);
  }
  document.querySelector('#login-form').addEventListener('submit', async submit => {
    submit.preventDefault();
    try { session = await api('/api/session', { method: 'POST', body: JSON.stringify({ email: document.querySelector('#email').value }) }); await saveSession(session); await showWorkspace(false); }
    catch (error) { document.querySelector('#login-error').textContent = error.message; }
  });
  document.querySelector('#sign-out').addEventListener('click', async () => { clearInterval(pulseTimer); await saveSession(null); event('signed-out'); location.reload(); });
  window.addEventListener('pagehide', () => { clearInterval(pulseTimer); database.close(); });
  if (session) try { await showWorkspace(true); } catch { await saveSession(null); session = null; }
})();
