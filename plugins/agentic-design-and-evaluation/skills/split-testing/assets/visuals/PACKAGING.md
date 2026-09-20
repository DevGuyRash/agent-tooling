# Building and Packaging Visuals

The library ships browser-ready JavaScript in `dist/agentic-visuals.js` and CSS in `styles/agentic-visuals.css`. A report reader needs only a modern browser. Light, dark and system appearance require CSS `color-scheme`, `light-dark()` and `color-mix()` support. Saving reader records uses browser-native IndexedDB when available; unavailable storage remains an explicit session/export mode. Report authors can use Python 3.10 or newer to assemble a single offline HTML file; they need neither Node.js nor TypeScript unless they change the library source. These tools package the caller's data and composition without choosing report sections or interpreting evidence.

## Rebuild the library during development

`src/index.ts` and its local TypeScript imports are the runtime source. `src/theme.ts` is the pure theme owner; default builds generate `styles/agentic-visuals.css` from its exported definitions plus `styles/components.css`. Edit those sources rather than the generated stylesheet. `build.mjs` uses the TypeScript compiler's AMD `outFile` transform, checks every emitted dependency, and wraps the result in a private loader. Only the selected browser global is exposed; the default is `AgenticVisuals`. There is no separately maintained JavaScript implementation.

Development requires Node.js 18 or newer and the exact TypeScript version pinned in `package.json` (and the matching lockfile when one is supplied). The builder uses a local `typescript` package when available, otherwise the compiler package associated with an existing `tsc` on `PATH`. A differing compiler version is an error unless an exact qualification compiler is explicitly selected as described below. It does not install dependencies or read project `tsconfig.json` files.

For an explicitly authorized development setup **with a matching `package-lock.json`**, run the following from this directory. The supplied packed snapshot did not include that lockfile; do not assume `npm ci` is available from the snapshot alone or silently install dependencies during report creation. This setup accesses the public npm registry and installs development files under `node_modules`; it is unnecessary for report readers or Python-only assembly.

```sh
npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org
```

From this directory, rebuild and check with:

```sh
node build.mjs --replace
node build.mjs --check
python3 -m unittest discover -s tests -v
```

The first command explicitly authorizes replacing the generated bundle and stylesheet. `--check` recompiles in memory and compares bytes with both existing outputs; it never writes an output. The tests use temporary source fixtures and exercise the real CLIs, module exports, dependency refusal, safe embedding, and output preservation. Missing development dependencies cause failures rather than skipped build checks. Tests do not establish browser rendering or visual quality.

### Explicit compiler qualification

The default remains TypeScript **6.0.3**. In a constrained development environment, `--compiler-version EXACT` deliberately selects an already available compiler for a qualification build. It neither changes the package pin nor downloads or installs a compiler. The selected version must exactly match the compiler found by the builder; the CLI prints the exception. Record the exception and recheck with the pinned toolchain before release.

```sh
node build.mjs --replace --compiler-version 5.8.3
node build.mjs --check --compiler-version 5.8.3
AV_TEST_COMPILER_VERSION=5.8.3 python3 -m unittest discover -s tests -v
```

`AV_TEST_COMPILER_VERSION` is an explicit packaging-test option, not a browser setting. Other source tests use the installed `tsc` on `PATH`; ensure it is the compiler being qualified.

The source contract is static `import`/`export` declarations between local `.ts` modules under one root. Local directory indexes and `.js` import specifiers resolving to `.ts` source are supported. Runtime packages, dynamic `import()`, `require()`, CommonJS import/export forms, and imports outside the root are rejected. Standard browser APIs and TypeScript's ES2020/DOM libraries are available. The generated runtime uses a classic script and `globalThis`; it has no server, module-loader service, CDN, or browser package dependency.

Default paths are relative to `build.mjs`, so invoking that file from another working directory builds the same library. Explicit paths are relative to the current working directory. To compile a separate illustrative entry that imports library source, use a root containing both directories and a distinct browser global:

```sh
node build.mjs --entry examples/demo.ts --root . --output /absolute/report-work/demo.js --global AgenticVisualsDemo
```

The normal consumer bundle contains only the graph reachable from `src/index.ts`. A separately compiled demonstration is not added to it. `--entry`, `--root`, `--output`, and `--global` are presentation build parameters; they do not change the source's exports or add report content.

## Assemble one offline HTML file

Keep authoring inputs in any suitable report working directory. The body is a UTF-8 HTML fragment whose structure and content the caller chooses. The composition script is ordinary classic JavaScript that calls the library's selected renderers and, where applicable, its interaction hydration API. Supply styles in cascade order and scripts in execution order, with the library before the composition script.

For example, from this directory:

```sh
python3 assemble.py \
  --body /absolute/report-work/body.html \
  --title "Comparison evidence" \
  --style styles/agentic-visuals.css \
  --script dist/agentic-visuals.js \
  --data report-data=/absolute/report-work/evidence.json \
  --script /absolute/report-work/compose.js \
  --output /absolute/report.html
```

For optional interaction, call `AgenticVisuals.enhanceVisuals(document.getElementById("report"))` after the composition inserts its markup. Keep the returned cleanup function if the report will replace that root. Repeating enhancement on the same root returns that function; enhancing an overlapping ancestor or descendant throws before attaching another controller. Independently embedded sibling reports should each be enhanced once. The library does not auto-enhance unrelated page content. A single component can use the same interaction entry without the workspace shell.

For a static-first report, render the chosen components to the body file during authoring and embed the library plus a small enhancement script. The complete document is then present even when JavaScript is unavailable. The synthetic showcase follows this route: `examples/demo.ts` supplies its markup through `renderDemo()`, while the final report embeds the ordinary library bundle and calls `enhanceVisuals` on its workspace.

The composition script reads that data with `JSON.parse(document.getElementById("report-data").textContent)`. JSON blocks appear after the body and before every executable script. IDs must be unique and must not collide with body element IDs. JSON validation rejects duplicate object keys and non-JSON numbers. Numeric literal text is retained without Python rounding or reserialization; JavaScript's own numeric precision still applies when the composition calls `JSON.parse`.

| Input option | Embedded form |
| --- | --- |
| `--body FILE` | The caller's body fragment, with explicit asset tokens expanded |
| `--style FILE` (repeatable) | A base64 `data:text/css` stylesheet |
| `--script FILE` (repeatable) | A base64 `data:text/javascript` classic script |
| `--data ID=FILE` (repeatable) | A non-executable JSON script with HTML-significant characters escaped |
| `--feature mermaid` | The pinned full Mermaid runtime for diagrams produced only by composition scripts |
| `--asset NAME=FILE` (repeatable) | A MIME-labelled base64 data URL substituted for `{{asset:NAME}}` |

Base64 script and stylesheet embedding preserves their bytes, including JavaScript raw templates, comments, Unicode, and literal closing tags such as `</script>` and `</style>`. It requires no `eval`. JSON escaping prevents a label from terminating its data block while preserving the decoded value. Both scripts and styles remain inside the single output HTML file.

To embed a local image or font, declare it with `--asset logo=/absolute/report-work/logo.png` or `--asset report-font=/absolute/report-work/font.woff2`. Use `src="{{asset:logo}}"` in HTML or `url("{{asset:report-font}}")` in CSS. Tokens also work inside JSON strings and composition scripts. Every declared asset must be used, and every token must name a declared asset. Asset filenames are local paths; the tool never downloads URLs. SVG image assets must already be self-contained and contain no active embedded document or script.

`--lang` controls the document language and defaults to `en`. The title defaults to the output filename stem. Successful identical reruns leave the output unchanged. A differing existing output requires `--replace`; symlink outputs and outputs that would replace an input are refused. Writes use an owned temporary directory and atomic replacement or exclusive creation. Input, compilation, or dependency failures leave existing output intact; correct the named problem and rerun the same command. Temporary files are removed on normal completion and handled failures.

## Offline contract and verification limits

HTML resource attributes and CSS `url()` references must use embedded data or document fragments. Relative dependencies are not silently resolved or omitted: declare their local bytes with asset tokens. CSS `@import`, resource-bearing `image()`/`image-set()`/`src()` forms, HTML `srcset`, inline event attributes, and nested documents are explicitly unsupported. Supply separate CSS files through `--style`, a single embedded image source, and event listeners through `--script`. A body fragment uses explicitly balanced elements and complete tags/comments; it must not introduce its own document wrapper, head elements, scripts, styles, JSON script blocks, or legacy raw-text elements such as `plaintext`.

The same dependency checks apply to inline SVG presentation attributes: `fill`, `stroke`, `filter`, `clip-path`, `mask`, `marker`, `marker-start`, `marker-mid`, `marker-end`, `cursor`, and legacy `color-profile`. Their values use CSS syntax, including quoted URLs and CSS escapes. Local definitions such as `fill="url(#paint)"` are retained, and declared assets can be used as `fill="url('{{asset:paints}}#paint')"`. Exported figures that refer to a separate paint, filter, or marker file must inline those definitions or declare the referenced file as an asset. These checks inspect static resource references; they do not validate every SVG or CSS value, prove that fragment targets exist, or establish browser support for a particular resource form.

Inline SVG accessibility `<title>` elements are allowed and retained, including those generated by the library's charts. They do not set the HTML document title. HTML `<title>` remains forbidden in a body fragment, including inside SVG's HTML integration points such as `foreignObject`; use `--title` for the document title.

The generated Content Security Policy allows embedded scripts, styles, images, fonts, media, and inline style attributes; it blocks network connections, external resource loads, frames, objects, base URLs, and form submissions. Ordinary HTTP(S), mail, and telephone citation links remain navigational links and are not fetched during report loading. An external citation still needs its destination service when the reader elects to open it.

The body and composition scripts are trusted author inputs, not arbitrary untrusted HTML to sanitize. Evidence labels should enter through data and the renderer's escaping or DOM text APIs. Static packaging checks cannot prove that arbitrary composition code runs successfully, never attempts a blocked request, renders data faithfully, or remains usable with a keyboard. After assembly, open the final file directly in the intended browser with network access unavailable and check the actual composition, interactions, data values, and layout. The final deliverable is that HTML file; the authoring directory is not a runtime dependency.

## Mermaid and reviewed copies

Markup produced by `mermaidDiagram` declares `data-av-requires="mermaid"`. Assembly embeds `vendor/mermaid/mermaid.min.js` once, before the caller scripts, together with its required notices. For diagrams created only at runtime, pass `--feature mermaid`. The full 12.0.0 distribution, integrity metadata and license material live under `vendor/mermaid/`; report readers install nothing. Diagram families and bundled layout engines come from that distribution. External icon packs, fonts and images still require embedded local resources supplied by the author. The report CSP prevents a diagram from obtaining undeclared network resources.

Assembly also retains an inert recipe identifying the original body, data and embedded assets. The notebook uses it to create annotated HTML copies from those originals, then hydrates a fresh reader interface on opening. Expanded dialogs, generated toolbars and temporary selection state are not serialized into the body. The annotated file retains selected reader feedback as versioned JSON and preserves its report/revision ownership. Keep the recipe and generated asset IDs intact; older files without a recipe can still export their notebook data and readable handoff.

The Markdown handoff complements the annotated report. It retains comments, original target context and sources, unresolved attachments, drafts and conflicts; it does not replace the original report or confer analytical authority on feedback. Version-1 and version-2 notebook imports remain supported with recovery bytes preserved. Embedded review adoption is recorded at the transactional storage boundary so reopening a portable copy does not recreate feedback that the reader subsequently edited or removed.

## Representative reports and native qualification

`examples/assemble-previews.py` compiles the maintained example compositions in a temporary directory and assembles four static-first consumer reports with the ordinary library bundle. It does not install dependencies or include example logic in the library API.

```sh
python3 examples/assemble-previews.py --output /absolute/review-previews
python3 tests/native_browser.py --previews /absolute/review-previews \
  --output /absolute/native-results --browser /absolute/chromium --mode file --mermaid
```

Use `--compiler-version EXACT` on the preview helper only when deliberately qualifying a different available compiler. Existing differing preview files require `--replace`. The native runner needs an already available Python Playwright package and Chromium executable; these are development tools, not reader dependencies.

File mode opens the **assembled file** with networking disabled. `--mode content` is an explicit fallback that loads the same assembled HTML and its embedded resources into a native page when administrative policy blocks file navigation. It exercises native layout, focus, pointer/keyboard behavior, download generation and a fresh-page reviewed-copy reopen; it does **not** qualify operating-system file opening, file-origin permissions or native IndexedDB persistence. A content-mode pass is not a file-mode pass.

Outputs include assertions, input hashes, viewport screenshots, figure exports, a reviewed HTML copy and Markdown handoff. `--mermaid` records the outcome of every supplied family/layout/error fixture separately; inspect those outcomes, not only the core pass count. Family fixtures are a compatibility suite, not a whitelist. Invalid-source fixtures should fail visibly while retaining the source. Inspect final screenshots after animations settle, and repeat independent ordinary/adversarial review of the final artifact before publishing.

### Layout and interaction regression pass

`tests/native_polish.py` complements `native_browser.py`; it does not replace its export, reviewed-copy, long-comparison and Mermaid checks. It visits every demonstration view at 280, 320, 390, 520, 760, 1024 and 1440 CSS pixels, measures intersecting controls rather than only page overflow, changes an embedded container without changing the outer viewport, exercises first-open command layout, source-reader return, notebook editing, keyboard shortcuts, short landscape windows and emulated coarse-pointer hit areas.

```sh
python3 tests/native_polish.py --previews /absolute/review-previews \
  --output /absolute/polish-results --browser /absolute/chromium --mode file
```

Its explicit `--mode content` fallback has the same file-origin and persistence limitations described above. Inspect the screenshots as well as the assertions: an element can pass a center-point hit test while its surrounding reading space is poor. Physical touch, screen readers, alternate engines and operating-system zoom/keyboard behavior require separate qualification.

The stylesheet generator now rejects unbalanced CSS delimiters, quoted strings and comments before writing generated assets. This is an early corruption guard, not a CSS grammar validator or a substitute for native rendering. Internal overlay placement uses one shared geometry primitive; zero-width controls remain in closed overflow until their container can be measured. Adapter bounds are validated before figure toolbars or wrappers are attached.
