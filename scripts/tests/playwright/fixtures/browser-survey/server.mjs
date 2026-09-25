import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

/** Owned ephemeral fixture server; callers must close it. */
export async function serveSurveyFixture({ host = '127.0.0.1', port = 0 } = {}) {
  const sockets = new Set(), timers = new Set();
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://fixture.test');
    if (url.pathname === '/tick') { response.writeHead(200, { 'content-type': 'application/json' }); response.end('{"observed":true}'); return; }
    if (url.pathname === '/expected-failure') { response.writeHead(503, { 'content-type': 'text/plain' }); response.end('Synthetic expected response'); return; }
    if (url.pathname === '/slow-image.svg') {
      const timer = setTimeout(() => { timers.delete(timer); response.writeHead(200, { 'content-type': 'image/svg+xml' }); response.end('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="110"><rect width="240" height="110" fill="#448486"/><text x="15" y="60" fill="white">Delayed illustration ready</text></svg>'); }, 450);
      timers.add(timer); return;
    }
    const file = ({ '/': 'index.html', '/next': 'next.html', '/frame': 'frame.html' })[url.pathname];
    if (!file) { response.writeHead(404); response.end('Synthetic missing resource'); return; }
    try { response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); response.end(await readFile(new URL(file, import.meta.url))); }
    catch { response.writeHead(500); response.end('Fixture unavailable'); }
  });
  server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, host, resolve); });
  const address = server.address();
  return { url: `http://${host}:${address.port}`, server, close: async () => { for (const timer of timers) clearTimeout(timer); for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)); } };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const fixture = await serveSurveyFixture({ port: Number(process.env.PORT || 0) });
  process.stdout.write(`${fixture.url}\n`);
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => { await fixture.close(); process.exit(0); });
}
