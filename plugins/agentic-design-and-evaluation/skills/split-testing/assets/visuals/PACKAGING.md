# Packaging Reports

A report is one HTML file that carries its styles, scripts and data and renders in the reader's browser with no server, network or installation. Writing one needs Python 3.9 or newer and nothing else; Node.js and TypeScript are needed only to change the library itself. [catalog.md](catalog.md) describes what a report can contain.

| Shipped file | Role |
| --- | --- |
| `report.py` | Writes a report from trial data, a narrative or a specification. |
| `assemble.py` | Packages any HTML body, styles, scripts, JSON and local assets into one offline file; `report.py` uses it. |
| `dist/agentic-visuals.js` | The library, exposed as the browser global `AgenticVisuals`. |
| `dist/agentic-startup.js` | A prelude that applies a stored theme before first paint. |
| `styles/agentic-visuals.css` | Theme tokens generated from `src/theme.ts`, followed by `styles/components.css`. |
| `vendor/mermaid/` | Mermaid 12.0.0 with its license, notices and integrity record. |

## The common path: report.py

```sh
python3 <skills-file-root>/scripts/trial.py report RUN_DIR --out trial.json
python3 <skills-file-root>/assets/visuals/report.py --trial trial.json --narrative narrative.json --output report.html
python3 <skills-file-root>/assets/visuals/report.py --spec spec.json [--trial trial.json] --output report.html
```

| Option | Meaning |
| --- | --- |
| `--trial FILE` | JSON from `trial.py report`; embedded as `#av-trial`. |
| `--narrative FILE` | Decision, labels and extra sections for the trial composition; needs `--trial`, excludes `--spec`; embedded as `#av-narrative`. |
| `--spec FILE` | A complete specification instead of the composition; embedded as `#av-spec`. With `--trial` too, the trial fills the specification's `trial` field when it has none. |
| `--output FILE` | The HTML file to write (required). |
| `--title TEXT` | Document title; default the narrative's `title` or `question`, the specification's `title`, or the trial's `name`. |
| `--replace` | Replace an existing output that differs. |

`report.py` checks before writing that each input is JSON, that trial data has a `runs` list and that a specification has a `title` and `sections`; it embeds Mermaid when the narrative or specification contains a `diagram` block, and prints `assembled`, or `unchanged` when an identical file is already there. An error prints one `error:` line and a `hint:` line, exits 1, and leaves any existing output untouched; correct the named input and rerun the same command.

## Custom compositions

Use `assemble.py` directly when a report needs something `report.py` does not pass, such as a [registered block type](catalog.md#new-block-types), an extra stylesheet or a local image. The library renders automatically: when the page has finished parsing, it finds the first element marked `data-av-mount` and renders `#av-spec` there, or `#av-trial` with `#av-narrative` through the trial composition. Scripts placed after the library run first, so a block registered there is available to that render.

```sh
python3 <skills-file-root>/assets/visuals/assemble.py \
  --body body.html \
  --title "Comparison evidence" \
  --style <skills-file-root>/assets/visuals/styles/agentic-visuals.css \
  --script <skills-file-root>/assets/visuals/dist/agentic-visuals.js \
  --script verbatim.js \
  --data av-spec=spec.json \
  --data av-trial=trial.json \
  --output report.html
```

Here `body.html` is `<main data-av-mount></main>` and `verbatim.js` registers the block from the catalog's example. Without a mount element, a script can render into any element itself.

| `AgenticVisuals` member | Purpose |
| --- | --- |
| `mount(element, spec)` | Render a specification into an element and add browser behavior; returns `{cleanup(), diagrams?}`. |
| `renderReport(spec)` | The report as an HTML string, with no DOM access; it also runs under Node. |
| `enhance(element, ctx?)` | Add browser behavior to rendered markup; pass `createContext(spec, spec.cases)` for the run drawer. |
| `trialReport(trial, narrative?)` | The default trial composition as a specification. |
| `registerBlock(type, render)`, `blockTypes()`, `renderBlock(block, ctx)`, `blocks` | Block registry, renderers and the shared `frame`. |
| `ArmRegistry`, `createContext(spec, cases?)` | Arm identity and the render context. |
| `escapeText(value)`, `wilson(k, n)` | Escaping, and the 95% Wilson interval as `[lo, hi]` or null. |
| `mermaidDiagram(input)` | Diagram markup for a custom block. |
| `autoMount()` | The automatic render into the first `data-av-mount` element; it renders that element once. |

A rendered report sets `data-av-ready` on its root and dispatches `av-report-ready` on the document.

| `assemble.py` option | Embedded as |
| --- | --- |
| `--body FILE` | The caller's HTML body fragment, asset tokens expanded. |
| `--style FILE` (repeatable, cascade order) | A base64 `data:` stylesheet. |
| `--script FILE` (repeatable, execution order) | A base64 `data:` classic script; any script also brings the startup prelude into the head. |
| `--data ID=FILE` (repeatable) | Non-executable JSON under that element id; duplicate keys and non-JSON numbers are refused. |
| `--asset NAME=FILE` (repeatable) | A data URL substituted for each `{{asset:NAME}}` in the body, styles, scripts or data; every declared asset must be used. |
| `--feature mermaid` | The Mermaid runtime, for diagrams created by scripts. |
| `--title`, `--lang`, `--replace` | Document title (default the output file's name without its extension), language (default `en`), replacement of a differing output. |

The body is trusted author markup: it may not carry scripts, styles, document wrappers, inline event handlers or external resources. Every file also carries an inert `#av-report-recipe` JSON record of its assembly inputs. Ids `av-report-recipe`, `av-review-seed`, `av-startup`, `av-mermaid-notices` and the generated `av-style-N` and `av-script-N` are reserved.

## Offline and security contract

Every resource is embedded, and the file's Content Security Policy is `default-src 'none'; script-src data:; worker-src blob:; style-src 'unsafe-inline' data:; img-src data:; font-src data:; media-src data:; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`. A report therefore loads nothing from a network and submits nothing anywhere; ordinary `https:`, `mailto:` and `tel:` links stay navigational. `assemble.py` refuses a body, stylesheet or SVG asset that references a resource it has not embedded. Evidence enters as JSON and is escaped by the renderers, so text from runs cannot become markup. The only state a report keeps is the theme choice, in local storage under `av-theme`.

## Mermaid

`report.py` embeds `vendor/mermaid/mermaid.min.js`, ahead of the library, whenever a `diagram` block appears in the narrative or specification. `assemble.py` embeds it when the body already contains diagram markup, or with `--feature mermaid` when a script creates diagrams at render time, which is the case for any `diagram` block in an `av-spec` or `av-narrative` it packages. Mermaid's license and notices travel inside the file as `#av-mermaid-notices`, and the integrity record and local compatibility patches are listed in `vendor/mermaid/NOTICE.md` and `integrity.json`. A report missing Mermaid shows each diagram's source with a notice to reassemble with `--feature mermaid`. Mermaid adds about 7 MB to a file.

## Rebuilding the library

`src/` is the only source; edit it, never the generated `dist/` files or `styles/agentic-visuals.css`. `styles/components.css` holds the component styles and `src/theme.ts` the tokens. From `assets/visuals/`:

```sh
node build.mjs --replace   # rebuild dist/agentic-visuals.js, dist/agentic-startup.js and styles/agentic-visuals.css
node build.mjs --check     # compare a fresh build with those files; writes nothing
```

The build needs Node.js 18 or newer and exactly the TypeScript version pinned in `package.json` (6.0.3), taken from a local `typescript` package or the one behind `tsc` on `PATH`; another version is refused unless named with `--compiler-version EXACT` for a deliberate qualification. It installs and downloads nothing, reads no `tsconfig.json`, accepts only static imports between local `.ts` modules, and checks every output before replacing any. `--replace` authorizes replacing differing outputs; an identical build is a no-op. `node build.mjs --help` lists the options for a custom `--entry`, `--root`, `--output` or `--global`, which build only that bundle.

## Checking a report before delivery

1. Run `report.py` (or `assemble.py`) and read its output line; an `error:` means nothing was written.
2. Open the file from an unrelated folder with the network unavailable. The page should render every section with no notice saying a block is unknown, could not render, or needs trial data, and diagrams should be drawn rather than showing their source.
3. Compare the numbers a decision rests on with `trial.py summarize` or the trial JSON, and confirm that invalid runs, missing values and the cases behind any pooled difference are visible.
4. Open a run from the tapestry and from the ledger, move with the arrow keys, filter the ledger, switch themes, and narrow the window to phone width.
5. Check that untrusted text from runs (excerpts, judge reasons) shows as text.

[Qualifying visuals](../../references/qualifying-visuals.md) covers what such checks establish. A report that renders correctly says nothing about whether its analysis is valid.
