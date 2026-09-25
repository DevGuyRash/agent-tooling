const SECRET_KEY = /(?:password|passphrase|secret|token|credential|authorization|cookie|api[-_]?key)/i;
const BOX = /[\u2500-\u257f]/g;
const ANSI = /\u001b\[[0-?]*[ -/]*[@-~]/g;

function redactionValues(configuration = {}) {
  const values = new Set();
  const add = (value, short = false) => { if (typeof value === 'string' && value && (short || value.length >= 4)) values.add(value); };
  for (const environment of [configuration.env, configuration.launchOptions?.env]) {
    if (environment) for (const [key, value] of Object.entries(environment)) add(value, SECRET_KEY.test(key));
  }
  const visited = new Set();
  const collect = (value, sensitive = false) => {
    if (typeof value === 'string') { if (sensitive) add(value, true); return; }
    if (!value || typeof value !== 'object' || Buffer.isBuffer(value) || visited.has(value)) return;
    visited.add(value);
    if (Array.isArray(value)) { if (sensitive) for (const item of value) collect(item, true); return; }
    for (const [key, item] of Object.entries(value)) collect(item, sensitive || SECRET_KEY.test(key) || /^(?:headers|extraHTTPHeaders|storageState|proxy|httpCredentials|clientCertificates)$/i.test(key));
  };
  collect(configuration);
  return [...values].sort((a, b) => b.length - a.length);
}

function sanitizedText(value, secrets) {
  let text = String(value ?? '').slice(0, 32768).replace(ANSI, '').replace(BOX, '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '');
  for (const secret of secrets) {
    if (secret.length >= 4) text = text.split(secret).join('[redacted]');
    else text = text.replace(new RegExp(`(?<![\\w])${secret.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\w])`, 'g'), '[redacted]');
  }
  // Keep hosts and path context while removing URL credentials, queries,
  // fragments and credential-bearing assignments from retained error text.
  text = text.replace(/\b(?:https?|wss?):\/\/[^\s<>"']+/gi, value => {
    try { const url = new URL(value); url.username = ''; url.password = ''; url.search = ''; url.hash = ''; return url.href; } catch { return '[url]'; }
  });
  text = text.replace(/\b(?:authorization|proxy-authorization|cookie|set-cookie)["']?\s*[:=]\s*[^\r\n]+/gi, '[authentication redacted]');
  text = text.replace(/\b(?:bearer|basic)\s+[A-Za-z0-9+/_=.-]+/gi, '[authentication redacted]');
  text = text.replace(/((?:--)?[\w.-]*(?:password|passphrase|secret|token|credential|api[-_]?key)[\w.-]*["']?\s*(?:=|:|\s)\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, '$1[redacted]');
  return text;
}

function shortLine(value, limit) {
  const clean = value.replace(/\s+/g, ' ').trim();
  return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean;
}

function safeCause(text) {
  const candidates = text.split(/\r?\n/).filter(line => {
    const trimmed = line.trim();
    return trimmed && !/^at\s|^Call log:|^Browser logs:|^[-=]{3,}/.test(trimmed)
      && !/<launching>|<launched>|\b(?:command|arguments|environment|env)\s*[:=]|^\s*(?:--|[A-Z_][A-Z0-9_]*=)/i.test(trimmed);
  }).map(line => line.replace(/^\s*(?:\[[^\]]*\]\s*)+/, '').replace(/^browserType\.(?:launchServer|launch):\s*/, '').trim()).filter(Boolean);
  const detail = candidates.find(line => /\b(?:FATAL|ERROR)\b|error while|permission denied|access denied|ECONNREFUSED|EACCES|ENOENT|invalid |unsupported |failed to /i.test(line) && !/Target page, context or browser has been closed/.test(line));
  return shortLine(detail ?? candidates[0] ?? 'The browser process stopped without a usable launcher message.', 360);
}

/** Return a compact public error; raw launcher logs, environment and stacks stay out. */
export function executionDiagnostic(error, configuration = {}) {
  const secrets = redactionValues(configuration);
  const text = sanitizedText(error?.message ?? error, secrets);
  const browser = /^[a-z][a-z0-9-]{0,30}$/.test(configuration.browser ?? '') ? configuration.browser : null;
  const browserSuffix = browser ? ` ${browser}` : '';
  const candidateCode = sanitizedText(error?.code ?? '', secrets);
  let code = /^[A-Z][A-Z0-9_]{1,79}$/.test(candidateCode) ? candidateCode : 'SESSION_START_FAILED';
  let message, hint;
  if (/Host system is missing dependencies|Missing libraries:|error while loading shared libraries|cannot open shared object file|Library not loaded:/i.test(text)) {
    const dependencies = [...new Set(text.match(/\blib[a-z0-9][a-z0-9+_.:-]*\b|\b[a-z0-9_.-]+\.(?:dll|dylib)\b/gi) ?? [])].filter(name => !/^(?:library|libraries)$/i.test(name)).slice(0, 12);
    const names = shortLine(dependencies.join(', '), 240);
    code = 'BROWSER_DEPENDENCIES_MISSING';
    message = `Browser system dependencies are missing${names ? `: ${names}` : ''}.`;
    hint = `Install the listed host packages, or use "playwright install-deps${browserSuffix}" from the selected Playwright installation, then retry.`;
  } else if (/Executable doesn't exist|executable does not exist|download new browsers|executable[^\n]*not found/i.test(text)) {
    code = 'BROWSER_EXECUTABLE_MISSING';
    message = 'The selected Playwright browser executable is missing.';
    hint = `Use "playwright install${browserSuffix}" from the selected Playwright installation, or supply an existing executable/channel.`;
  } else if (/socket path too long|SingletonSocket.{0,80}too long/i.test(text)) {
    code = 'BROWSER_SOCKET_PATH_TOO_LONG';
    message = 'The browser could not create its local socket because its temporary path is too long.';
    hint = 'Choose a shorter temporaryRoot, such as /tmp; resourceRoot and artifactDir can remain unchanged.';
  } else if (/No usable sandbox|running as root without --no-sandbox|Failed to move to new namespace|sandbox initialization failed|setuid sandbox.*(?:failed|not configured)/i.test(text)) {
    code = 'BROWSER_SANDBOX_UNAVAILABLE';
    message = `Browser sandbox setup failed: ${safeCause(text)}`;
    hint = 'Check the host’s sandbox and user-namespace support for the requested browser configuration.';
  } else {
    message = safeCause(text);
    hint = error?.hint ? shortLine(sanitizedText(error.hint, secrets), 280) : 'Check this launcher cause against the selected browser, launch options, and host prerequisites.';
  }
  return { code, message: shortLine(message, 400), hint: shortLine(hint, 280) };
}
