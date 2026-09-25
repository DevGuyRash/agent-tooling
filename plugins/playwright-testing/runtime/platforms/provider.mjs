import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { runtimeError } from '../resolution.mjs';

export async function loadProvider(provider, projectDir = process.cwd()) {
  let loaded = provider;
  if (typeof provider === 'string') {
    const module = await import(pathToFileURL(resolve(projectDir, provider)).href);
    loaded = module.default ?? module.provider ?? module;
  }
  if (typeof loaded?.acquire !== 'function') throw runtimeError('PROVIDER_INVALID', 'An isolated session provider must expose acquire(options).', 'Pass a provider module path or an object with acquire().');
  return loaded;
}

export async function acquireProvider(options) {
  const provider = await loadProvider(options.provider, options.projectDir);
  const lease = await provider.acquire({ ...options, ownerPid: process.pid });
  const release = typeof lease?.close === 'function' ? () => lease.close() : typeof provider.release === 'function' ? () => provider.release(lease) : null;
  const close = async () => { if (release) await release(); };
  try {
    if (!lease || !release || !lease.identity || !lease.renderingOS) throw runtimeError('PROVIDER_CONTRACT', 'Provider acquisition must return identity, renderingOS, and close(), or expose provider.release(lease).', 'Return a stable non-secret session identity and an owned teardown operation.');
    if (options.presentation === 'isolated-headed' && (lease.capabilities?.isolated !== true || lease.capabilities?.headed !== true)) throw runtimeError('PROVIDER_ISOLATION', 'The provider has not declared isolated headed capability.', 'Use a provider that reports capabilities.isolated and capabilities.headed as true.');
    return { ...lease, backend: 'configured-provider', close };
  } catch (error) { await close(); throw error; }
}
