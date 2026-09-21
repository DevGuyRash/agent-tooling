#!/usr/bin/env node
/** Build a private AMD module graph with the installed TypeScript compiler. */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { generateThemeStyles, generateStartupScript } from "./build-theme.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const usage = `Usage: node build.mjs [--entry FILE] [--root DIR] [--output FILE]
                      [--global NAME] [--compiler-version VERSION] [--replace | --check]

Defaults: src/index.ts, its parent as root, dist/agentic-visuals.js,
          browser global AgenticVisuals (paths relative to this tool).
Explicit paths are relative to the working directory. TypeScript must be
installed locally or with tsc on PATH; this command installs nothing.
--replace authorizes replacing a differing output; identical output is a no-op.
--check compares a fresh build with the existing output without writing files.
--compiler-version explicitly selects an exact installed qualification compiler;
  omitting it retains the pinned compiler check. Nothing is downloaded or installed.
`;

function fail(message, hint) {
  const error = new Error(message);
  error.hint = hint;
  throw error;
}

function options(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i += 1) {
    const option = argv[i];
    if (["--help", "--replace", "--check"].includes(option)) {
      result[option.slice(2)] = true;
    } else if (["--entry", "--root", "--output", "--global", "--compiler-version"].includes(option)) {
      if (!argv[i + 1] || argv[i + 1].startsWith("--")) fail(`${option} needs a value`, "use --help for supported options");
      result[option.slice(2)] = argv[++i];
    } else fail(`unknown option ${option}`, "use --help for supported options");
  }
  if (result.replace && result.check) fail("--replace and --check cannot be combined", "select writing or checking");
  return result;
}

function compiler() {
  const require = createRequire(import.meta.url);
  try { return require("typescript"); } catch (error) {
    if (error.code !== "MODULE_NOT_FOUND") throw error;
  }
  for (const directory of (process.env.PATH || "").split(path.delimiter)) {
    if (!directory) continue;
    try {
      const executable = fs.realpathSync(path.join(directory, "tsc"));
      return createRequire(executable)("typescript");
    } catch (error) {
      if (!["ENOENT", "ENOTDIR", "MODULE_NOT_FOUND"].includes(error.code)) throw error;
    }
  }
  fail("TypeScript compiler is unavailable", "provide a local typescript package or an existing tsc installation on PATH; no dependencies were installed");
}

// This same resolver is used for build-time graph validation and in the bundle.
function resolveModule(modules, from, dependency) {
  // TypeScript's outFile transform may replace a relative source specifier with
  // the emitted module's canonical name. Source checks reject bare imports.
  if (Object.prototype.hasOwnProperty.call(modules, dependency)) return dependency;
  if (!dependency.startsWith("./") && !dependency.startsWith("../")) throw new Error(`unsupported dependency ${JSON.stringify(dependency)} in ${from}; only local modules are supported`);
  const parts = from.split("/").slice(0, -1);
  for (const part of dependency.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (!parts.length) throw new Error(`dependency escapes module root: ${dependency} in ${from}`);
      parts.pop();
    } else parts.push(part);
  }
  const target = parts.join("/");
  const candidates = [target, target.replace(/\.js$/, ""), `${target}/index`];
  for (const candidate of candidates) if (Object.prototype.hasOwnProperty.call(modules, candidate)) return candidate;
  throw new Error(`unresolved dependency ${JSON.stringify(dependency)} in ${from}`);
}

function checkSource(ts, program) {
  for (const source of program.getSourceFiles()) {
    if (source.isDeclarationFile) continue;
    function reject(node, message) {
      const location = source.getLineAndCharacterOfPosition(node.getStart(source));
      fail(`${source.fileName}:${location.line + 1}:${location.character + 1}: ${message}`, "use static import/export declarations between local .ts modules");
    }
    function visit(node) {
      if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
        const specifier = node.moduleSpecifier;
        if (!ts.isStringLiteral(specifier) || !/^\.\.?\//.test(specifier.text)) reject(node, "external module dependencies are unsupported");
      }
      if (ts.isImportEqualsDeclaration(node) || (ts.isExportAssignment(node) && node.isExportEquals)) reject(node, "CommonJS import/export forms are unsupported");
      if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(node.expression) && node.expression.text === "require"))) reject(node, "dynamic imports and require calls are unsupported");
      ts.forEachChild(node, visit);
    }
    visit(source);
  }
}

function bundle(ts, entry, root, globalName, compilerVersion) {
  const pinnedVersion = JSON.parse(fs.readFileSync(path.join(here, "package.json"), "utf8")).devDependencies.typescript;
  const requiredVersion = compilerVersion || pinnedVersion;
  if (compilerVersion && !/^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$/.test(compilerVersion)) fail("--compiler-version needs an exact version", "version ranges are not supported");
  if (compilerVersion && compilerVersion !== pinnedVersion) process.stderr.write(`qualification compiler: TypeScript ${compilerVersion}; pinned default remains ${pinnedVersion}\n`);
  if (ts.version !== requiredVersion) fail(`TypeScript ${ts.version} differs from the pinned development compiler ${requiredVersion}`, "provide the pinned compiler from package-lock.json before rebuilding; no dependencies were installed");
  const major = Number(ts.versionMajorMinor.split(".")[0]);
  const settings = {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.AMD,
    moduleResolution: ts.ModuleResolutionKind.Node10,
    moduleDetection: ts.ModuleDetectionKind.Force,
    rootDir: root,
    outFile: path.join(os.tmpdir(), "agentic-visuals-virtual-output.js"),
    strict: true,
    noEmitOnError: true,
    esModuleInterop: true,
    types: [],
    lib: ["lib.es2020.d.ts", "lib.dom.d.ts", "lib.dom.iterable.d.ts"],
    newLine: ts.NewLineKind.LineFeed,
    ignoreDeprecations: major >= 6 ? "6.0" : "5.0",
  };
  const program = ts.createProgram([entry], settings);
  checkSource(ts, program);
  const diagnostics = ts.getPreEmitDiagnostics(program);
  if (diagnostics.length) {
    const lines = diagnostics.slice(0, 10).map(diagnostic => {
      let prefix = `TS${diagnostic.code}`;
      if (diagnostic.file && diagnostic.start !== undefined) {
        const location = diagnostic.file.getLineAndCharacterOfPosition(diagnostic.start);
        prefix = `${diagnostic.file.fileName}:${location.line + 1}:${location.character + 1} ${prefix}`;
      }
      return `${prefix}: ${ts.flattenDiagnosticMessageText(diagnostic.messageText, " ")}`;
    });
    if (diagnostics.length > 10) lines.push(`${diagnostics.length - 10} further compiler diagnostics omitted`);
    fail(lines.join("\n"), "correct the TypeScript inputs and rerun; existing output was not changed");
  }
  let emitted;
  const result = program.emit(undefined, (filename, content) => {
    if (!filename.endsWith(".js") || emitted !== undefined) fail("compiler produced an unsupported output set", "use a single static local TypeScript module graph");
    emitted = content;
  });
  if (result.emitSkipped || emitted === undefined) fail("compiler emitted no JavaScript", "check the entry and its local imports");

  const modules = Object.create(null);
  // AMD factories are collected, never executed, during dependency validation.
  vm.runInNewContext(emitted, {
    define(id, dependencies, factory) {
      if (typeof id !== "string" || !Array.isArray(dependencies) || typeof factory !== "function" || Object.hasOwn(modules, id)) fail("compiler emitted an invalid or duplicate AMD module", "use named static local modules");
      modules[id] = dependencies;
    },
  }, { timeout: 3000, filename: "compiled-module-graph.js" });
  const entryId = path.relative(root, entry).split(path.sep).join("/").replace(/\.ts$/, "");
  if (!Object.hasOwn(modules, entryId)) fail(`entry module ${entryId} was not emitted`, "use an entry .ts module inside --root");
  for (const [id, dependencies] of Object.entries(modules)) {
    for (const dependency of dependencies) {
      if (!["require", "exports", "module"].includes(dependency)) resolveModule(modules, id, dependency);
    }
  }

  return `// Generated by build.mjs from TypeScript. Do not edit this browser bundle.\n(function (root) {\n"use strict";\nconst modules = Object.create(null);\nconst resolveModule = ${resolveModule.toString()};\nfunction define(id, dependencies, factory) {\n  modules[id] = { dependencies, factory, module: { exports: {} }, started: false };\n}\nfunction load(id) {\n  const record = modules[id];\n  if (record.started) return record.module.exports;\n  record.started = true;\n  const localRequire = dependency => load(resolveModule(modules, id, dependency));\n  const values = record.dependencies.map(dependency => dependency === "require" ? localRequire : dependency === "exports" ? record.module.exports : dependency === "module" ? record.module : localRequire(dependency));\n  const value = record.factory.apply(undefined, values);\n  if (value !== undefined) record.module.exports = value;\n  return record.module.exports;\n}\n${emitted}\nObject.defineProperty(root, ${JSON.stringify(globalName)}, { value: load(${JSON.stringify(entryId)}), configurable: true, enumerable: true, writable: true });\n})(globalThis);\n`;
}

function preflightOutput(output, content, replace, check) {
  let current;
  try { const info = fs.lstatSync(output); if (!info.isFile() || info.isSymbolicLink()) fail(`output is not a regular file: ${output}`, "choose a regular output path"); current = fs.readFileSync(output, "utf8"); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  if (current === content) return;
  if (check) fail(`bundle differs or is missing: ${output}`, "rebuild with --replace and review the generated change");
  if (current !== undefined && !replace) fail(`output exists and differs: ${output}`, "use --replace to authorize replacement, or choose another --output");
}

function writeOutput(output, content, replace, check) {
  let current;
  try {
    const info = fs.lstatSync(output);
    if (!info.isFile() || info.isSymbolicLink()) fail(`output is not a regular file: ${output}`, "choose a regular output path");
    current = fs.readFileSync(output, "utf8");
  } catch (error) { if (error.code !== "ENOENT") throw error; }
  if (current === content) { process.stdout.write(`unchanged ${output}\n`); return; }
  if (check) fail(`bundle differs or is missing: ${output}`, "rebuild with --replace and review the generated change");
  if (current !== undefined && !replace) fail(`output exists and differs: ${output}`, "use --replace to authorize replacement, or choose another --output");
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const scratch = fs.mkdtempSync(path.join(path.dirname(output), ".av-build-"));
  try {
    const temporary = path.join(scratch, "bundle.js");
    fs.writeFileSync(temporary, content, { encoding: "utf8", flag: "wx" });
    if (replace) fs.renameSync(temporary, output);
    else fs.linkSync(temporary, output);
  } finally { fs.rmSync(scratch, { recursive: true, force: true }); }
  process.stdout.write(`built ${output} (${Buffer.byteLength(content)} bytes)\n`);
}

try {
  const args = options(process.argv.slice(2));
  if (args.help) process.stdout.write(usage);
  else {
    const entry = path.resolve(args.entry || path.join(here, "src/index.ts"));
    const root = path.resolve(args.root || path.dirname(entry));
    const output = path.resolve(args.output || path.join(here, "dist/agentic-visuals.js"));
    const globalName = args.global || "AgenticVisuals";
    if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(globalName)) fail("--global must be a JavaScript identifier", "use a name such as AgenticVisuals or AgenticVisualsDemo");
    if (!entry.endsWith(".ts") || entry.endsWith(".d.ts")) fail("entry must be an executable .ts module", "choose a .ts file, not a declaration file");
    if (!output.endsWith(".js")) fail("output must have a .js extension", "choose a browser JavaScript output path");
    if (!fs.existsSync(entry)) fail(`entry is missing: ${entry}`, "provide --entry or restore src/index.ts");
    if (entry === output) fail("output would overwrite the TypeScript entry", "choose a separate .js output path");
    const relative = path.relative(root, entry);
    if (relative.startsWith(`..${path.sep}`) || relative === ".." || path.isAbsolute(relative)) fail("entry is outside --root", "choose a root containing the entry and every local import");
    const ts = compiler();
    const javascript = bundle(ts, entry, root, globalName, args["compiler-version"]);
    const stylesheet = entry === path.join(here, "src/index.ts") && output === path.join(here, "dist/agentic-visuals.js") ? generateThemeStyles(ts, here) : null;
    const startup = stylesheet === null ? null : generateStartupScript(ts, here);
    const startupPath = path.join(here, "dist/agentic-startup.js");
    // Validate all source outputs and destinations before writing any of them.
    preflightOutput(output, javascript, args.replace, args.check);
    if (stylesheet !== null) preflightOutput(path.join(here, "styles/agentic-visuals.css"), stylesheet, args.replace, args.check);
    if (startup !== null) preflightOutput(startupPath, startup, args.replace, args.check);
    writeOutput(output, javascript, args.replace, args.check);
    if (stylesheet !== null) writeOutput(path.join(here, "styles/agentic-visuals.css"), stylesheet, args.replace, args.check);
    if (startup !== null) writeOutput(startupPath, startup, args.replace, args.check);
  }
} catch (error) {
  process.stderr.write(`error: ${error.message}\n${error.hint ? `hint: ${error.hint}\n` : ""}`);
  process.exitCode = 1;
}
