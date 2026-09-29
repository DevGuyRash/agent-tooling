// Check harness (never copied into the agent's repository): list what each module exports.
//
// Usage: node exports.mjs <module path>...
// Prints one line `EXPORTS {"<path>": {"<name>": "function" | "class" | "generator" | "other"} | null}`;
// null means the module could not be imported.
import { pathToFileURL } from 'node:url';

function kind(value) {
  if (typeof value !== 'function') return 'other';
  if (/^class[\s{]/.test(Function.prototype.toString.call(value))) return 'class';
  const ctor = Object.getPrototypeOf(value)?.constructor?.name;
  if (ctor === 'GeneratorFunction' || ctor === 'AsyncGeneratorFunction') return 'generator';
  return 'function';
}

const kinds = {};
for (const modulePath of process.argv.slice(2)) {
  try {
    const mod = await import(pathToFileURL(modulePath).href);
    kinds[modulePath] = Object.fromEntries(Object.keys(mod).map((name) => [name, kind(mod[name])]));
  } catch {
    kinds[modulePath] = null;
  }
}
process.stdout.write(`\nEXPORTS ${JSON.stringify(kinds)}\n`);
setImmediate(() => process.exit(0));
