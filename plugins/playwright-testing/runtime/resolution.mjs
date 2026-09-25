import { createRequire } from 'node:module';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function runtimeError(code, message, hint, cause) {
  const error = new Error(message, cause ? { cause } : undefined);
  error.code = code;
  if (hint) error.hint = hint;
  return error;
}

export async function resolvePlaywright({ projectDir = process.cwd(), playwrightPath } = {}) {
  const base = resolve(projectDir);
  try { if (!statSync(base).isDirectory()) throw new Error('Not a directory.'); }
  catch (error) { throw runtimeError('PROJECT_DIRECTORY', 'The selected project directory is unavailable.', 'Pass an existing projectDir.', error); }
  const require = createRequire(join(base, '__playwright_survey_resolver.cjs'));
  const requests = playwrightPath
    ? [isAbsolute(playwrightPath) ? playwrightPath : resolve(base, playwrightPath)]
    : ['playwright', '@playwright/test', 'playwright-core'];
  let modulePath;
  for (let request of requests) {
    try {
      if (existsSync(request) && statSync(request).isDirectory()) {
        const manifest = JSON.parse(readFileSync(join(request, 'package.json'), 'utf8'));
        request = resolve(request, manifest.main || 'index.js');
      }
      modulePath = require.resolve(request);
      break;
    } catch (error) {
      if (playwrightPath) throw runtimeError('PLAYWRIGHT_NOT_FOUND', 'Cannot resolve the supplied Playwright installation.', 'Pass the installed package directory or entry file with playwrightPath.', error);
    }
  }
  if (!modulePath) throw runtimeError('PLAYWRIGHT_NOT_FOUND', 'Playwright is not installed in the selected project.', 'Use the project’s Playwright installation, or supply playwrightPath after installing the pinned standalone runtime.');
  let imported;
  try { imported = await import(pathToFileURL(modulePath).href); }
  catch (error) { throw runtimeError('PLAYWRIGHT_LOAD_FAILED', 'The selected Playwright installation could not be loaded.', 'Check its Node.js requirements and installation integrity.', error); }
  const playwright = imported.default?.chromium ? imported.default : imported;
  const engines = Object.keys(playwright).filter(name => ['launch', 'launchServer', 'connect', 'executablePath'].every(method => typeof playwright[name]?.[method] === 'function'));
  if (!engines.length) throw runtimeError('PLAYWRIGHT_INVALID', 'The selected module does not expose Playwright browser engines.', 'Pass playwright, @playwright/test, or playwright-core.');
  let packageRoot = dirname(modulePath), version = 'unknown';
  while (true) {
    try {
      const manifest = JSON.parse(readFileSync(join(packageRoot, 'package.json'), 'utf8'));
      if (['playwright', '@playwright/test', 'playwright-core'].includes(manifest.name)) { version = manifest.version; break; }
    } catch { /* Keep walking to the package manifest. */ }
    const parent = dirname(packageRoot);
    if (parent === packageRoot) break;
    packageRoot = parent;
  }
  return { playwright, modulePath, packageRoot, version, engines, projectDir: base };
}

function geometry(value, name, allowNull = false) {
  if (value === null && allowNull) return null;
  if (!value || !Number.isInteger(value.width) || !Number.isInteger(value.height) || value.width < 1 || value.height < 1 || value.width > 32768 || value.height > 32768) {
    throw runtimeError('INVALID_GEOMETRY', `${name} requires positive integer width and height up to 32768.`, 'Use CSS pixel dimensions for the requested viewport or screen.');
  }
  return { width: value.width, height: value.height };
}

export function sessionConfiguration(options, resolved) {
  const presentation = options.presentation ?? 'headless';
  if (!['headless', 'isolated-headed'].includes(presentation)) throw runtimeError('INVALID_PRESENTATION', `Unknown presentation: ${presentation}.`, 'Valid presentations: headless, isolated-headed.');
  const preset = options.device ? resolved.playwright.devices?.[options.device] : undefined;
  if (options.device && !preset) throw runtimeError('UNKNOWN_DEVICE', `Unknown device preset: ${options.device}.`, 'Use inspectCapabilities({devices:true}) to list presets in this installation.');
  const browser = options.browser ?? preset?.defaultBrowserType ?? 'chromium';
  if (!resolved.engines.includes(browser)) throw runtimeError('UNKNOWN_BROWSER', `Unknown browser engine: ${browser}.`, `Valid engines: ${resolved.engines.join(', ')}.`);
  const contextOptions = { ...preset, ...options.contextOptions };
  delete contextOptions.defaultBrowserType;
  if (options.viewport !== undefined) contextOptions.viewport = options.viewport;
  if (options.screen !== undefined) contextOptions.screen = options.screen;
  contextOptions.viewport = geometry(contextOptions.viewport === undefined ? { width: 1280, height: 800 } : contextOptions.viewport, 'viewport', true);
  if (contextOptions.screen !== undefined) contextOptions.screen = geometry(contextOptions.screen, 'screen');
  const viewport = contextOptions.viewport;
  const display = geometry(options.display ?? contextOptions.screen ?? { width: (viewport?.width ?? 1280) + 32, height: (viewport?.height ?? 800) + 128 }, 'display');
  const launchOptions = { ...options.launchOptions };
  const headless = presentation === 'headless';
  if (launchOptions.headless !== undefined && launchOptions.headless !== headless) throw runtimeError('PRESENTATION_CONFLICT', 'launchOptions.headless conflicts with presentation.', 'Choose the presentation with headless or isolated-headed.');
  launchOptions.headless = headless;
  if (browser === 'chromium') {
    launchOptions.channel = options.channel ?? launchOptions.channel ?? 'chromium';
    launchOptions.chromiumSandbox ??= true;
  } else if (options.channel) throw runtimeError('UNSUPPORTED_CHANNEL', 'Browser channels are available for Chromium.', 'Select chromium for Chrome/Edge channels, or omit channel for Firefox/WebKit.');
  return { presentation, browser, contextOptions, launchOptions, display, device: options.device ?? null };
}
