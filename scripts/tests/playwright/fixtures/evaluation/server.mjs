#!/usr/bin/env node
import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { mkdir, open, readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const scenarios = ['site-survey', 'dashboard', 'quiet-checkout'];

const routerData = {
  north: [
    { number: 7, site: 'Main office', owner: 'Mira Santos', address: '192.0.2.17', retentionDays: 14 },
    { number: 39, site: 'Harbor annex', owner: 'Jon Chen', address: '192.0.2.39', retentionDays: 30 },
  ],
  south: [
    { number: 9, site: 'Research floor', owner: 'Ari Shah', address: '198.51.100.9', retentionDays: 7 },
    { number: 42, site: 'Field laboratory', owner: 'Lena Okafor', address: '198.51.100.42', retentionDays: 0 },
  ],
};

function assetsFor(team) {
  return Array.from({ length: 56 }, (_, index) => {
    const number = index + 1;
    const special = routerData[team].find(row => row.number === number);
    return {
      id: `${team === 'north' ? 'N' : 'S'}-${String(number).padStart(3, '0')}`,
      team, name: special ? 'Router' : `Sensor ${String(number).padStart(2, '0')}`,
      site: special?.site ?? `Bay ${1 + index % 6}`, status: 'Online',
      owner: special?.owner ?? 'Demo Operations', address: special?.address ?? `203.0.113.${number}`,
      retentionDays: special?.retentionDays ?? 14,
    };
  });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
}

async function readJson(request) {
  let size = 0;
  const chunks = [];
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 16_384) throw new Error('Request exceeds the fixture limit');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

/** Each instance owns its listener, synthetic application state, log, and timers. */
export async function startEvaluationServer({ scenario, logPath, host = '127.0.0.1', port = 0 } = {}) {
  if (!scenarios.includes(scenario)) throw new Error(`Unknown scenario. Valid scenarios: ${scenarios.join(', ')}`);
  if (host !== '127.0.0.1') throw new Error('Evaluation fixtures bind to 127.0.0.1');
  if (!Number.isInteger(port) || port < 0 || port > 65_535) throw new Error('Port must be an integer from 0 through 65535');
  let log;
  if (logPath) {
    await mkdir(dirname(resolve(logPath)), { recursive: true });
    log = await open(logPath, 'wx', 0o600);
  }
  const events = [], sockets = new Set(), timers = new Set(), sessions = new Set(), archived = new Set(), receipts = new Map();
  const assets = [...assetsFor('north'), ...assetsFor('south')];
  const instanceId = randomUUID();
  let writeQueue = Promise.resolve(), logError, closing, tick = 0, sequence = 0;
  const record = (type, data = {}) => {
    const event = { sequence: ++sequence, type, ...data };
    events.push(event);
    if (log) writeQueue = writeQueue.then(() => log.write(`${JSON.stringify(event)}\n`)).catch(error => { logError ??= error; });
  };
  const json = (response, code, value) => {
    response.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
    response.end(JSON.stringify(value));
  };
  const file = async (response, relative, type = 'text/html; charset=utf-8') => {
    const content = await readFile(new URL(relative, import.meta.url));
    response.writeHead(200, { 'content-type': type, 'cache-control': 'no-store' });
    response.end(content);
  };
  const authorize = (request, response) => {
    if (sessions.has(request.headers['x-demo-session'])) return true;
    json(response, 401, { error: 'Open a demo session to view this workspace.' });
    return false;
  };
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://fixture.invalid');
    const safeQuery = Object.fromEntries(['day', 'team'].flatMap(key => url.searchParams.has(key) ? [[key, url.searchParams.get(key).slice(0, 30)]] : []));
    record('request', { method: request.method, path: url.pathname.slice(0, 240), query: safeQuery });
    try {
      if (url.pathname === '/favicon.ico') { response.writeHead(204); response.end(); return; }
      if (url.pathname === '/shared.css') return await file(response, './shared.css', 'text/css; charset=utf-8');
      if (url.pathname === '/api/events' && request.method === 'POST') {
        const input = await readJson(request);
        const allowed = ['menu-open', 'program-day', 'session-open', 'schedule-scroll', 'venue-view', 'team-change', 'filter-change', 'detail-open', 'detail-close', 'session-restored', 'signed-out'];
        if (!allowed.includes(input.action)) return json(response, 400, { error: 'Unknown fixture action' });
        const data = { action: input.action };
        for (const key of ['team', 'id', 'day', 'value', 'pageId']) if (typeof input[key] === 'string') data[key] = input[key].slice(0, 80);
        record('action', data);
        return json(response, 200, { recorded: true });
      }
      if (scenario === 'site-survey') {
        if (url.pathname === '/') return await file(response, './site-survey/index.html');
        if (url.pathname === '/program') return await file(response, './site-survey/program.html');
        if (url.pathname === '/venue') return await file(response, './site-survey/venue.html');
        if (url.pathname === '/site.js') return await file(response, './site-survey/site.js', 'text/javascript; charset=utf-8');
        if (url.pathname === '/sessions') {
          const one = url.searchParams.get('day') !== 'two';
          return json(response, 200, Array.from({ length: 9 }, (_, index) => ({
            id: `${one ? 'one' : 'two'}-${index + 1}`, time: `${String(9 + index).padStart(2, '0')}:00`,
            title: (one ? ['Opening: Shared city', 'Listening in public', 'Tools for participation', 'Lunch and exhibits', 'Evidence workshop', 'Mapping connections', 'Planning with neighbors', 'Open studio', 'Day-one reflection'] : ['Designing resilient places', 'Learning from trials', 'Measuring progress', 'Lunch and exhibits', 'Data and dignity', 'Systems in practice', 'Access for everyone', 'Closing commitments', 'Day-two reflection'])[index],
            room: index % 2 ? 'Harbor room' : 'Garden room', speaker: (one ? ['Amal Duarte', 'Chen Wu', 'Mina Berg'] : ['Inez Rivera', 'Noah Kim', 'Samira Ali'])[index % 3],
          })));
        }
        if (url.pathname === '/late-poster.svg') {
          const timer = setTimeout(() => {
            timers.delete(timer);
            if (response.destroyed) return;
            response.writeHead(200, { 'content-type': 'image/svg+xml', 'cache-control': 'no-store' });
            response.end('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="210" viewBox="0 0 800 210"><rect width="800" height="210" rx="14" fill="#285d5c"/><circle cx="690" cy="58" r="120" fill="#80c6b8"/><text x="30" y="110" font-size="32" fill="white" font-family="sans-serif">City Exchange · Riverside Hall</text><text x="32" y="156" font-size="22" fill="white" font-family="sans-serif">Two days of ideas, 14–15 October</text></svg>');
          }, 550);
          timers.add(timer); return;
        }
      }
      if (scenario === 'dashboard') {
        if (url.pathname === '/' || url.pathname === '/workspace') return await file(response, './dashboard/index.html');
        if (url.pathname === '/dashboard.js') return await file(response, './dashboard/dashboard.js', 'text/javascript; charset=utf-8');
        if (url.pathname === '/api/session' && request.method === 'POST') {
          const value = await readJson(request);
          if (value.email !== 'reviewer@example.test') return json(response, 400, { error: 'Use the supplied demo reviewer address.' });
          const token = randomUUID(); sessions.add(token); record('action', { action: 'session-created' });
          return json(response, 200, { token, displayName: 'Demo Reviewer' });
        }
        if (url.pathname.startsWith('/api/')) {
          if (!authorize(request, response)) return;
          if (url.pathname === '/api/me') return json(response, 200, { displayName: 'Demo Reviewer' });
          if (url.pathname === '/api/pulse') return json(response, 200, { tick: ++tick, message: 'Status feed connected' });
          if (url.pathname === '/api/assets') {
            const team = url.searchParams.get('team');
            if (!Object.hasOwn(routerData, team)) return json(response, 400, { error: 'Select north or south.' });
            return json(response, 200, assets.filter(row => row.team === team && !archived.has(row.id)).map(({ id, name, team, site, status }) => ({ id, name, team, site, status })));
          }
          const match = /^\/api\/assets\/([NS]-\d{3})(\/archive)?$/.exec(url.pathname);
          if (match) {
            const asset = assets.find(row => row.id === match[1]);
            if (!asset) return json(response, 404, { error: 'Unknown asset' });
            if (match[2] && request.method === 'POST') {
              archived.add(asset.id); record('action', { action: 'asset-archived', id: asset.id });
              return json(response, 200, { archived: asset.id });
            }
            if (!match[2] && request.method === 'GET') return json(response, 200, asset);
          }
        }
      }
      if (scenario === 'quiet-checkout') {
        if (url.pathname === '/') return await file(response, './quiet-checkout/index.html');
        if (url.pathname === '/api/orders' && request.method === 'POST') {
          const input = await readJson(request);
          if (!Number.isInteger(input.quantity) || input.quantity < 1 || input.quantity > 10) return json(response, 400, { error: 'Quantity must be from 1 through 10.' });
          const receipt = { id: `R-${String(receipts.size + 1).padStart(4, '0')}`, quantity: input.quantity, item: 'Field notebook', unitPrice: 42, total: input.quantity * 42 };
          receipts.set(receipt.id, receipt); record('action', { action: 'order-created', ...receipt });
          return json(response, 201, { url: `/receipt/${receipt.id}` });
        }
        const match = /^\/receipt\/(R-\d{4})$/.exec(url.pathname);
        if (match && request.method === 'GET') {
          const receipt = receipts.get(match[1]);
          if (!receipt) return json(response, 404, { error: 'Receipt not found' });
          record('action', { action: 'receipt-read', id: receipt.id });
          const html = (await readFile(new URL('./quiet-checkout/receipt.html', import.meta.url), 'utf8'))
            .replaceAll('RECEIPT_ID', escapeHtml(receipt.id)).replaceAll('QUANTITY_VALUE', String(receipt.quantity))
            .replaceAll('TOTAL_VALUE', `$${receipt.total.toFixed(2)}`);
          response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' }); response.end(html); return;
        }
      }
      json(response, 404, { error: 'No fixture route at this address.' });
    } catch (error) {
      record('server-error', { message: error instanceof SyntaxError ? 'Malformed request JSON' : error.message });
      if (!response.headersSent) json(response, 400, { error: 'Fixture request could not be completed.' });
      else response.destroy();
    }
  });
  server.on('connection', socket => { sockets.add(socket); socket.once('close', () => sockets.delete(socket)); });
  try {
    await new Promise((resolveListen, reject) => {
      server.once('error', reject);
      server.listen(port, host, () => { server.off('error', reject); resolveListen(); });
    });
  } catch (error) { if (log) await log.close(); throw error; }
  const origin = `http://${host}:${server.address().port}`;
  record('server-start', { instanceId, scenario, origin });
  return {
    origin,
    snapshot() { return structuredClone({ instanceId, scenario, origin, events, archivedIds: [...archived], receipts: [...receipts.values()] }); },
    close() {
      closing ??= (async () => {
        for (const timer of timers) clearTimeout(timer);
        timers.clear();
        const stopped = new Promise((resolveClose, reject) => server.close(error => error ? reject(error) : resolveClose()));
        for (const socket of sockets) socket.destroy();
        await stopped;
        record('server-stop', { instanceId });
        await writeQueue;
        if (log) await log.close();
        if (logError) throw new Error(`Evaluation log could not be saved: ${logError.code ?? logError.message}`);
      })();
      return closing;
    },
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [scenario, ...args] = process.argv.slice(2);
  if (scenario === '--help' || !scenario) {
    process.stdout.write(`Usage: node server.mjs <${scenarios.join('|')}> [--log PATH] [--port NUMBER]\n`);
  } else {
    try {
      const options = { scenario };
      while (args.length) {
        const arg = args.shift(), value = args.shift();
        if (!value || !['--log', '--port'].includes(arg)) throw new Error('Use --log PATH or --port NUMBER');
        options[arg === '--log' ? 'logPath' : 'port'] = arg === '--log' ? value : Number(value);
      }
      const fixture = await startEvaluationServer(options);
      process.stdout.write(`${fixture.origin}\n`);
      for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => {
        try { await fixture.close(); } catch (error) { process.stderr.write(`error: ${error.message}\n`); process.exitCode = 1; }
      });
    } catch (error) { process.stderr.write(`error: ${error.message}\n`); process.exitCode = 1; }
  }
}
