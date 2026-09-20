/** Generate CSS from the trusted pure theme module. This helper never writes files. */
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

/** Catch truncated blocks, strings and comments before shipping a stylesheet.
 * This is a delimiter check, not a CSS grammar or browser-compatibility validator. */
export function validateCssBlocks(css, label = "Stylesheet") {
  const stack = [];
  let quote = "", comment = false;
  for (let index = 0; index < css.length; index++) {
    const char = css[index], next = css[index + 1];
    if (comment) { if (char === "*" && next === "/") { comment = false; index++; } continue; }
    if (char === "\\") { index++; continue; }
    if (quote) { if (char === quote) quote = ""; continue; }
    if (char === "/" && next === "*") { comment = true; index++; continue; }
    if (char === "'" || char === '"') { quote = char; continue; }
    if ("{([".includes(char)) stack.push(char);
    else if ("})]".includes(char) && stack.pop() !== ({"}":"{", ")":"(", "]":"["})[char]) throw new Error(`${label} has an unmatched ${char} near character ${index}.`);
  }
  if (quote || comment || stack.length) throw new Error(`${label} ends inside an unclosed ${quote ? 'string' : comment ? 'comment' : 'block'}.`);
}

export function generateThemeStyles(ts, visualsDirectory) {
  const source = path.join(visualsDirectory, "src/theme.ts");
  const text = fs.readFileSync(source, "utf8");
  const parsed = ts.createSourceFile(source, text, ts.ScriptTarget.ES2020, true);
  for (const statement of parsed.statements) {
    if (ts.isImportDeclaration(statement) || ts.isImportEqualsDeclaration(statement) || (ts.isExportDeclaration(statement) && statement.moduleSpecifier)) throw new Error("theme.ts must be a self-contained pure module; imports are not allowed");
  }
  const output = ts.transpileModule(text, { fileName: source, reportDiagnostics: true, compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, newLine: ts.NewLineKind.LineFeed } });
  const errors = (output.diagnostics || []).filter(diagnostic => diagnostic.category === ts.DiagnosticCategory.Error);
  if (errors.length) throw new Error("theme.ts cannot compile: " + ts.flattenDiagnosticMessageText(errors[0].messageText, " "));
  const context = vm.createContext({ exports: Object.create(null) }, { codeGeneration: { strings: false, wasm: false } });
  vm.runInContext(output.outputText, context, { timeout: 3000, filename: "trusted-theme.js" });
  const css = vm.runInContext("exports.themeCss()", context, { timeout: 3000 });
  if (typeof css !== "string" || !css.trim()) throw new Error("themeCss() must return nonempty CSS");
  const components = fs.readFileSync(path.join(visualsDirectory, "styles/components.css"), "utf8");
  validateCssBlocks(css, "Generated theme"); validateCssBlocks(components, "Component styles");
  return css + "\n/* Maintained component styles from styles/components.css. */\n" + components;
}
