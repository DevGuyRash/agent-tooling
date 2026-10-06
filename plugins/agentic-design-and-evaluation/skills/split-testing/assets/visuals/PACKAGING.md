# Packaging Reports

A report is one HTML file that carries its styles, scripts and data and renders in the reader's browser with no server, network or installation. Writing one needs Python 3.9 or newer and nothing else; Node.js and TypeScript are needed only to change the library itself. [catalog.md](catalog.md) describes what a report can contain.

| Shipped file | Role |
| --- | --- |
| `report.py` | Writes a report from trial data, a narrative or a specification; checks them first on request. |
| `assemble.py` | Packages any HTML body, styles, scripts, JSON and local assets into one offline file; `report.py` uses it. |
| `dist/agentic-visuals.js` | The library, exposed as the browser global `AgenticVisuals`. |
| `dist/agentic-startup.js` | A prelude that applies a stored theme before first paint. |
| `styles/agentic-visuals.css` | Theme tokens generated from `src/theme.ts`, followed by `styles/components.css`. |
| `vendor/mermaid/` | Mermaid 12.0.0 with its license, notices and integrity record. |
| `examples/` | A fictional trial, a narrative for it, a showcase specification and the script that renders them. |

## The common path: report.py

```sh
python3 <skills-file-root>/scripts/trial.py report RUN_DIR --out trial.json
python3 <skills-file-root>/assets/visuals/report.py --skeleton narrative.json --trial trial.json
python3 <skills-file-root>/assets/visuals/report.py --check --trial trial.json --narrative narrative.json
python3 <skills-file-root>/assets/visuals/report.py --trial trial.json --narrative narrative.json --output report.html
python3 <skills-file-root>/assets/visuals/report.py --spec spec.json [--trial trial.json] --output report.html
```

Fill in the skeleton, check it, then write the report; `--check` also takes `--spec SPEC [--trial FILE]`.

| Option | Meaning |
| --- | --- |
| `--trial FILE` | JSON from `trial.py report`; embedded as `#av-trial`. |
| `--narrative FILE` | Decision, labels and extra sections for the trial composition; needs `--trial`, excludes `--spec`; embedded as `#av-narrative`. |
| `--spec FILE` | A complete specification instead of the composition; embedded as `#av-spec`. With `--trial` too, the trial fills the specification's `trial` field when it has none. |
| `--output FILE` | The HTML file to write (required unless `--check` or `--skeleton`). |
| `--title TEXT` | Document title; default the narrative's `title` or `question`, the specification's `title`, or the trial's `name`. |
| `--replace` | Replace an existing output (or, with `--skeleton FILE`, an existing file) that differs. |
| `--check` | Write nothing; read the inputs as the page will and print every problem. |
| `--skeleton [FILE]` | Print a starter narrative for `--trial`, or write it to `FILE`. |

**Writing.** `report.py` checks before writing that each input is JSON, that trial data has a `runs` list and that a specification has a `title` and `sections`. It embeds Mermaid when the narrative or specification contains a `diagram` block, and prints `assembled PATH (N bytes)`, or `unchanged PATH (N bytes)` when an identical file is already there. An error prints one `error:` line and a `hint:` line, exits 1, and leaves any existing output untouched; correct the named input and rerun the same command. When the inputs have problems of the kind `--check` lists, the report is still written, a `warning:` line on stderr counts them, and the page lists them in an input-check panel at its top.

**Checking.** `--check` applies the rules of `validateSpec` and `validateNarrative` (the catalog's [input checks](catalog.md#input-checks)) without a browser. It prints each problem to stderr as `error: WHERE: MESSAGE` or `warning: WHERE: MESSAGE` followed by a `hint:` line (often "did you mean …"), then `checked INPUTS: N errors and M warnings` (or `no problems`) to stdout, and exits 1 when any problem is an error. An error is input that would break a view or make it misread, such as a misspelled verdict, arm or case, an unknown block type, more passes than valid runs, or arms called `identical` whose recorded settings differ; a warning is input the report does not use as written. JSON is read strictly (duplicate keys and non-JSON numbers are refused). Arm and case ids are checked against those in the trial's plan or runs, so an id naming a planned arm that never ran passes although the report ignores it.

**Starting a narrative.** `--skeleton` takes only `--trial` (and `--replace` when writing a file). With no file it prints to stdout; with one it writes it, refusing to replace a differing file without `--replace`, and prints `wrote PATH` or `unchanged PATH`. The skeleton holds the arm and case ids spelled as the trial records them, `arms` and `cases` with the ids as placeholder labels, `identical` groups of arms whose recorded settings all match (their instruction and artifact texts aside), `baseline` when the trial names one, the plan's decision rule as a note, and an empty `title`, `question` and `decision`. The decision's `headline` is empty, so `--check` reports it as an error until you write the decision you reached by applying the rule, or delete `decision` to report the results without one. Arms that share an instructions digest but differ in other settings are listed in a `$same_instructions` note, not under `identical`. Keys that start with `$` are notes that the report and the checks ignore.

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
| `trialReport(trial, narrative?)`, `SECTION_IDS` | The default trial composition as a specification (it carries the narrative's problems in `problems`), and the default section ids in order. |
| `validateSpec(spec, {trial?})`, `validateNarrative(narrative, trial?)` | Input problems as `[{level, where, message, hint?}]`: the rules `report.py --check` applies. |
| `registerBlock(type, render)`, `blockTypes()`, `renderBlock(block, ctx)`, `blocks` | Block registry, renderers and the shared `frame`. |
| `ArmRegistry`, `createContext(spec, cases?)` | Arm identity and the render context. |
| `escapeText(value)`, `wilson(k, n)`, `newcombe(k1, n1, k2, n2)` | Escaping; the 95% Wilson interval as `[lo, hi]` or null; the 95% Newcombe interval for the difference of two rates (first minus second) or null. |
| `tally(runs)`, `trialAxes(trial)` | Pass, fail, invalid, valid and run counts with rate and interval; the arms and cases that ran, in plan order. |
| `casePairs(trial)`, `pairedOrder(cases, pairs)` | Case variants found by content; cases with each variant after its base. |
| `failureCause(run, scenario?)`, `invalidReason(code)` | Why a run did not pass, as `{kind, text, failedChecks}`; an invalid reason in words with its remedy, as `{code, text, remedy}`. |
| `lineDiff(before, after)`, `diffRuns(lines)`, `diffStats(lines)`, `wordDiff(before, after)` | A line diff, its changed and foldable stretches, its counts, and word-level marks for a replaced line. |
| `runsCsv(trial, indexes?, labels?)`, `csvCell(value)` | The CSV the ledger exports, and one escaped CSV field. |
| `mermaidDiagram(input)` | Diagram markup for a custom block. |
| `browserTextMeasure(document, font)` | A canvas text-width measure for layout code, or null where canvas is unavailable. |
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

Every resource is embedded, and the file's Content Security Policy is `default-src 'none'; script-src data:; worker-src blob:; style-src 'unsafe-inline' data:; img-src data:; font-src data:; media-src data:; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`. A report therefore loads nothing from a network and submits nothing anywhere; ordinary `https:`, `mailto:` and `tel:` links stay navigational. `assemble.py` refuses a body, stylesheet or SVG asset that references a resource it has not embedded. Evidence enters as JSON and is escaped by the renderers, so text from runs cannot become markup. The only state a report keeps is the theme choice, in local storage under `av-theme`; ledger filters and run links live in the address, and the CSV and JSON exports are files the page builds in the browser for the reader to save, so a viewer that blocks downloads gets a message naming the clipboard and embedded-JSON alternatives. The embedded JSON is the whole trial: its run directory path, instruction texts and final-output excerpts travel with the file. The page shows a home-directory prefix as `~` in its headings, settings and run drawer, but the embedded JSON, the copy buttons and the CSV export keep the full path, so read the trial JSON before sending a report beyond its machine.

## Mermaid

`report.py` embeds `vendor/mermaid/mermaid.min.js`, ahead of the library, whenever a `diagram` block appears in the narrative or specification. `assemble.py` embeds it when the body already contains diagram markup, or with `--feature mermaid` when a script creates diagrams at render time, which is the case for any `diagram` block in an `av-spec` or `av-narrative` it packages. Mermaid's license and notices travel inside the file as `#av-mermaid-notices`, and the integrity record and local compatibility patches are listed in `vendor/mermaid/NOTICE.md` and `integrity.json`. A report missing Mermaid shows each diagram's source with a notice to reassemble with `--feature mermaid`. Mermaid adds about 7 MB to a file.

## Rebuilding the library

`src/` is the only source; edit it, never the generated `dist/` files or `styles/agentic-visuals.css`. `styles/components.css` and `styles/blocks/` hold the component styles and `src/theme.ts` the tokens. From `assets/visuals/`:

```sh
node build.mjs --replace   # rebuild dist/agentic-visuals.js, dist/agentic-startup.js and styles/agentic-visuals.css
node build.mjs --check     # compare a fresh build with those files; writes nothing
python3 -m unittest discover -s tests   # rendering, composition, checks, CLI, examples and, with Chrome on PATH, browser behavior
```

The build needs Node.js 18 or newer and exactly the TypeScript version pinned in `package.json` (6.0.3), taken from a local `typescript` package or the one behind `tsc` on `PATH`; another version is refused unless named with `--compiler-version EXACT` for a deliberate qualification. It installs and downloads nothing, reads no `tsconfig.json`, accepts only static imports between local `.ts` modules, and checks every output before replacing any. `--replace` authorizes replacing differing outputs; an identical build is a no-op, and `--check` prints `unchanged PATH` for each output that is current. `node build.mjs --help` lists the options for a custom `--entry`, `--root`, `--output` or `--global`, which build only that bundle. The tests skip the browser cases when neither `google-chrome-stable` nor `chromium` is on `PATH`, and `python3 examples/make_fictional_trial.py` prints exactly `examples/fictional-trial.json`.

## Checking a report before delivery

1. Start from `report.py --skeleton`, write the narrative, and run `report.py --check` with the same `--trial` and `--narrative`; it exits 0 when no problem is an error. Read each warning too: it names input the report does not use as written.
2. Run `report.py` (or `assemble.py`) and read its output line; an `error:` means nothing was written, and a `warning:` means the page lists input problems at its top.
3. Open the file from an unrelated folder with the network unavailable. The page should render every section with no notice saying a block is unknown, could not render, or needs trial data, no input-check panel you did not expect, and diagrams drawn rather than showing their source.
4. Compare the numbers a decision rests on with `trial.py summarize` or the trial JSON, and confirm that invalid runs, missing values and the cases behind any pooled difference are visible.
5. Open a run from a case dossier, the failures view and the ledger, move with the arrow keys, filter the ledger, follow a `#run-1` link and a `#runs?outcome=fail` link, switch themes, and narrow the window to phone width (the ledger then shows its first 20 runs until "Show all").
6. Check that untrusted text from runs (excerpts, judge reasons, instruction texts) shows as text.

[Qualifying visuals](../../references/qualifying-visuals.md) covers what such checks establish. A report that renders correctly says nothing about whether its analysis is valid.
