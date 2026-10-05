# Visual Library Catalog

The library turns data into one report page. A report is a **specification**: a title and a list of sections, each holding **blocks** that name their `type` and carry their own fields. The page renders in the reader's browser from JSON embedded in the file, so a report is composed from data rather than written as markup. The library draws what it is given; from trial runs it computes only pass rates, 95% Wilson intervals, medians and quartiles, and it never decides, scores or ranks (see [What is not offered](#what-is-not-offered)).

Two entries reach it:

- **A trial.** `trial.py report RUN_DIR --out trial.json` writes the data, and `report.py --trial trial.json --narrative narrative.json --output report.html` composes the default trial report from it ([Trial composition](#trial-composition)). This is the quickest faithful path.
- **A specification.** `report.py --spec spec.json [--trial trial.json] --output report.html` renders a specification you write, mixing trial and general blocks.

[PACKAGING.md](PACKAGING.md) covers both commands, custom compositions and checking a report before delivery. [examples/](examples/) holds a fictional trial (`fictional-trial.json`, written by `make_fictional_trial.py`), a narrative for it (`fictional-narrative.json`) and a specification that uses every general block once (`showcase-spec.json`); `python3 examples/assemble-previews.py --output DIR` renders all three.

## Specification

| Field | Type | Meaning |
| --- | --- | --- |
| `title` | string, required | The report's heading. |
| `sections` | array, required | `{title, blocks, label?, id?, lead?}`, numbered 01, 02, … in order. `label` is the section-index entry (default `title`); `lead` is text under the heading; `id` is kept when it starts with a letter and holds only letters, digits, `_`, `.`, `:` or `-`, otherwise one is derived from the title. |
| `kicker` | string | A line above the title and the top bar's name (default "Report"). |
| `summary` | text | Paragraphs under the title. |
| `meta` | `[{label, value}]` | Facts under the summary. |
| `arms` | `[{id, label?, note?}]` | Identity order and readable labels ([Arm identity](#arm-identity-and-run-marks)). |
| `cases` | `{scenario: label}` | Readable labels for trial cases. |
| `trial` | object | The `trial.py report` JSON that trial blocks and the run drawer read; `report.py --trial` fills it when the specification has none. |
| `footer` | string | Closing line; the default says every view is drawn from the embedded data. |

**Text.** Fields marked *text* (`summary`, `lead`, `description`, `detail`, `text`, `rule`) take a string, split into paragraphs at blank lines, or an array of paragraphs. They and a few short fields (a verdict's `headline` and list entries, `list` items and details, non-`mono` `facts` values, a `callout` title) recognize only `` `code` `` and `**strong**`; every other character is escaped, so evidence text never becomes markup. Labels, table cells, notes and excerpts are escaped with no markup at all.

**Blocks.** A block is `{type, ...fields}`. Besides its own fields, every block accepts `title`, `description` (text), `note` (a closing line) and `id`, except where its entry says otherwise. An unknown `type` renders a visible notice listing the valid types, and a block that fails on its fields renders a notice with the reason in its place, so a report never silently drops a block.

## Trial blocks

Except `verdict` and `figures`, these read the specification's `trial` and render a notice naming the missing field without it. Invalid runs (`passed: null`) are counted apart from failures, never as failures. A run mark or ledger row opens the [run drawer](#the-run-drawer).

### verdict

The decision and its rule: a stamp, the headline, detail, up to three lists, and beside them the rule with the state of each rule check.

| Field | Meaning |
| --- | --- |
| `verdict` | `adopt`, `reject`, `inconclusive`, `mixed` or `none` (anything else is `none`); stamps read Adopt, Do not adopt, Inconclusive, Mixed, No decision recorded. |
| `label` | Replaces the stamp's word. |
| `headline` | The decision in one sentence. |
| `detail` | Text under the headline. |
| `conditions`, `limits`, `changes` | String lists headed "Holds when", "Does not show", "Would change it". |
| `rule` | The decision rule, quoted and labelled "fixed before results"; pass only a rule that was. |
| `checks` | `[{label, observed, threshold?, met}]`; `met` true, false or null reads met, not met, not evaluated. |

Limit: it shows the decision as written; nothing is computed from or checked against the data.

### figures

A row of headline numbers. `items: [{value, label, note?, tone?}]`, `tone` one of `neutral`, `pass`, `fail`, `warn`, `invalid`. Whole numbers get thousands separators, other numbers a compact form (0.87, 4.2k), and a null value shows as missing; pass a formatted string such as `"87%"` for a unit.

### ladder

Pass rate per arm: a point at passed over valid runs, its 95% Wilson interval, the fraction and rate, a chip counting invalid runs, and an `n = …` chip below five valid runs, on a fixed 0–100% axis.

| Field | Meaning |
| --- | --- |
| `rows` | `[{arm, k, n, invalid?, note?}]` to draw your own counts; omitted, each arm's runs are tallied from the trial. |
| `case`, `cases` | Tally one case, or only the listed cases (default: every case pooled). |
| `identical` | Groups of arm ids given identical material. Each group sits together with the spread between its rates drawn as a band ("N points apart"): what chance alone produced. |
| `baseline` | An arm whose rate draws a labelled dashed reference line, and whose row is marked "baseline". |
| `references` | `[{value, label}]`, rates in 0–1 drawn as labelled dotted lines across every row, such as a decision rule's bar. |
| `sort` | `identity` (default) or `rate`. |

Limit: pooling weights cases by their valid runs; read `tapestry` when cases differ.

### tapestry

Every run as one mark in a grid of cases by arms. A cell shows passed over valid runs, its invalid count, a bar marking the pass share within its 95% interval (the interval is also in the cell's tooltip and accessible name), and its marks in repeat order; a combination never run says "not run". Fields: `arms` and `cases` (subsets; arms keep identity order, cases the order given), `transpose` (arms as rows; on by default with more than eight arms and fewer cases than arms), `groups: [{label, cases, note?}]` (sections the case rows under named sets, each headed by its case count, passed over valid runs and invalid count, with ungrouped cases under "Other cases"; groups turn transposition off).

### checks

How often each boolean check held per arm, as passed over valid runs with a shaded bar, in three groups: **Required checks** (named in a case's `required` list, counted over the runs of the cases that require it, with "in N of M cases" when not all do), **Judge** (runs the judge passed, of valid judged runs) and **Recorded measures** (other booleans, shaded by share with no pass direction). Fields: `arms`, `checks` (names to keep). Limit: a check that ever records a non-boolean value is left out (the drawer still shows it).

### pairwise

Blind pairwise judgments from `trial.py pairwise`. Per pair, one stacked bar for all cases and one per case: the first arm preferred in both orders, ties, the second arm preferred, order-inconsistent pairs and invalid pairs, with the first arm's win rate and interval over decisive pairs only ("no decisive pairs" otherwise). Bar length is the number of pairs, so a case with fewer pairs draws a shorter bar; the legend lists only the outcomes present. Field: `pair`, a key such as `"A__B"` (default every pair).

### cost

One strip per measure and arm, with a dot per valid run (filled for a pass, a ring for a failure), the middle half and median of valid runs, a count of the arm's invalid runs beside the row ("N not shown": their cost is real, but a timeout is not a measurement of the task and would flatten the axis), and, when the trial names a baseline, the median across cases of the per-case percent difference `trial.py report` computed. Measures appear when some run records a positive value: `output_tokens`, `input_tokens`, `seconds` (executor time), `commands`, `total_cost_usd`. A range wider than 40 times turns the axis logarithmic, labelled so, with runs at zero counted beside it; otherwise a linear axis starts at zero unless the values sit far from it, in which case the panel says where it starts. Time ticks share one unit per axis. Fields: `measures` (those ids), `arms`. Limits: executors report different usage fields, so compare like with like; the difference uses the trial's own `baseline` (from `--baseline` or the plan), never a narrative's.

### invalid

Invalid runs grouped by `invalid_reason` (else `status`), with counts per arm, the opening of the first run's message and a mark per run. The default description gives their share and the remedy, `trial.py run --retry-invalid`; with none, it says every run finished valid. Frame fields only.

### ledger

Every run in a table: number, outcome, case, arm, repeat, judge verdict, output tokens (when recorded), time, and the invalid reason or the first 240 characters of the judge's reason. In the browser it gains outcome, arm and case filters, a text search, an "N of M runs" count and sortable columns; a row opens the drawer by click or Enter. Frame fields only.

### plan

What was compared: each arm's recorded `executor`, `model`, `effort`, `model_spec` and instruction, artifact and resource digests (only columns some arm records; digests shortened, in full on hover), arm notes, the judge's executor, model and effort, the run directory, and each case that ran as an expandable entry with its prompt, follow-ups, judge question and required checks. Frame fields only. Limit: other recorded settings (`base_url`, `command`, `allowed_tools`, permission and approval modes) are not shown.

## General blocks

These need no trial. Where a row takes `arm`, it gets that arm's color, shape and label.

| Block | Fields | Shows |
| --- | --- | --- |
| `text` | `text` (text) | Paragraphs. |
| `callout` | `text` (text), `title` (inside the box), `tone`, `label`, `id` | A boxed statement beside the evidence it qualifies. `tone`: `neutral`, `pass`, `fail`, `invalid`, `warn`, `accent`, or the aliases `note` (accent) and `limit` (warn); `label` replaces the tone's word (Note, Holds, Problem, Not measured, Limit). No `description` or `note`. |
| `list` | `items` (strings or `{text, tone?, detail?}`), `ordered` | A bulleted or numbered list. |
| `facts` | `items: [{label, value, mono?}]` | Label and value pairs; a null value reads "missing", `mono` shows code. |

### table

| Field | Meaning |
| --- | --- |
| `columns` | Header strings. |
| `rows` | Arrays of cells: a string, number, boolean (yes or no), null ("missing"), or `{value, status?, note?, mono?}`. A `status` of `pass`, `fail` or `invalid` adds the run mark; another tone tints the cell. |
| `numeric` | Column indexes to right-align (number cells align anyway). |
| `rowHeader` | The first column is a row header unless `false`. |

Numbers print exactly as given. With no rows it says so.

### matrix

Requirements against alternatives. `columns: [{id, label, arm?}]` (`arm: true` shows the arm named by `id`), `rows: [{id, label, detail?}]`, `cells: [{row, column, status?, text?, note?}]`, `status` an outcome or a tone. A missing cell, or one with status `missing`, reads "not established".

### intervals

Values with intervals on one axis, drawn like the ladder. `rows: [{label, arm?, k?, n?, value?, lo?, hi?, note?}]`: `k` and `n` give a rate with its 95% Wilson interval; otherwise `value`, `lo` and `hi` are drawn as given, and a row without a value says so. `percent` (default when every row is a count or a value within 0–1), `domain` (`[min, max]`; default 0–1 for percents, otherwise from 0, or the lowest negative value, to the largest), `unit` (after non-percent numbers), `reference: {value, label}` (a labelled line).

### bars

Composition. `segments: [{id, label, tone?}]`, `rows: [{label, arm?, values: {segment: number or null}, note?}]`. Each row is a bar split in proportion, with its total and "N missing" for segments without a number. Limits: a row with `arm` shows the arm's label instead of its own `label` (which survives only in the accessible name), so put what the row compares in `note`; a segment's number prints only when it fills more than 7% of the bar.

### trend

Change across ordered stages. `stages` (strings), `series: [{label, arm?, points: [{stage, k?, n?, value?, lo?, hi?}]}]`, `percent`. Points with counts get a rate and Wilson whiskers; a "Values" table lists every point, "missing" where absent. A stage without a value breaks the line; `unit` follows non-percent values. Limit: a series without `arm` borrows an arm color by its position.

### excerpts

Quoted output. `items: [{text, source?, arm?, outcome?, note?}]`, the text shown verbatim with an outcome badge and the arm.

### diagram

A Mermaid diagram: `source` (required), `title`, `caption`, `config` (Mermaid configuration), `description`, `note`, `id`. It is drawn in the browser by the bundled Mermaid, redrawn when the theme changes; the original source stays readable under "Diagram source", and a source that fails to render says why. The file must embed Mermaid, which `report.py` does whenever a `diagram` block appears. [Mermaid diagrams](../../references/mermaid-diagrams.md) lists what the bundled renderer supports.

## Trial composition

`trialReport(trial, narrative)`, which `report.py --trial` runs, builds a specification from the trial data and an optional narrative. Its sections are a starting order, not a fixed page:

| Id | Title | Blocks | Present |
| --- | --- | --- | --- |
| `verdict` | Verdict | `verdict` from the narrative's `decision` and the plan's `decision_rule`, then `figures`: runs, valid, invalid, arms, cases, repeats, judge | Always; without a `decision` the stamp reads "No decision recorded". |
| `arms` | Pass rate by arm | `ladder` with `identical` and `baseline`; with `groups`, titled "All cases" and followed by one ladder per group | Always |
| `cases` | Every run, by case | `tapestry`, sectioned by `groups` | Always |
| `checks` | Checks | `checks` | When runs record boolean checks or judge pass or fail verdicts |
| `pairwise` | Pairwise judgments | `pairwise` | When the trial has pairwise results |
| `cost` | Cost and time | `cost` | When a run records a cost measure |
| `invalid` | Invalid runs | `invalid` | Always |
| `runs` | Run ledger | `ledger` | Always |
| `plan` | What was compared | `plan` | Always |

Every narrative field is optional:

| Field | Meaning |
| --- | --- |
| `title` | Report title; default `question`, then the trial's `name`, then "Trial results". |
| `question` | The practical question; the title when there is no `title`, otherwise a meta line. |
| `summary` | Text under the title. |
| `kicker` | Default "Split test · NAME". |
| `decision` | The verdict block's fields except `rule` (always the plan's) and `title`: `verdict`, `headline`, `detail`, `label`, `checks`, `conditions`, `limits`, `changes`. |
| `arms` | `[{id, label?, note?}]` or `{id: {label?, note?}}`; these lead the identity order, other arms follow the plan. |
| `cases` | `{scenario: label}`. |
| `identical` | Groups of arm ids given identical material, for the ladder's noise band. |
| `groups` | `[{label, cases, note?}]`: named sets of cases (conditions, variants, rounds), each with its own ladder and its own section of the run grid. |
| `baseline` | The ladder's reference arm (default the trial's `baseline`). |
| `include`, `exclude` | Default section ids to keep or drop. |
| `sections` | Extra sections, `{title, blocks, …, after?}`, each placed after the section whose id is `after` (a default id or an earlier extra's `id`), else at the end. |
| `append` | `{sectionId: [blocks]}` added to the end of a default section. |
| `footer` | Closing line. |

The meta lines hold the question (when a title is also given), runs and valid runs, the judge and the run directory. Write the `decision` after applying the plan's rule yourself; the composition carries the rule and the data, never a verdict of its own. [examples/fictional-narrative.json](examples/fictional-narrative.json) shows a complete decision. In JavaScript the result is an ordinary specification whose `sections` can be dropped, reordered or extended before rendering.

## Arm identity and run marks

Each arm gets one color (eight hues in an Okabe–Ito-based order, tuned per theme) and one shape (circle, square, diamond, triangle, hexagon, downward triangle, star, cross), the same in every view; the first 64 arms get distinct pairs. The order is the specification's `arms` (a narrative's `arms`), then arms as the trial's plan and runs list them. An arm tag shows the shape, the label and, where a label replaces the id, the raw id in code; compact views drop the id, while the ladder, pairwise headings, plan and drawer keep it. Pointing at an arm tag highlights that arm within its block.

Run outcomes share one mark language: passed is a filled circle, failed a hollow ring, invalid a grey square struck through. Cost dots take the arm's color with the same fill or ring. Shape and fill carry the state and color only reinforces it; in forced-colors mode the marks keep distinct fills and borders.

### The run drawer

A run mark (in `tapestry`, `cost` or `invalid`) or a ledger row opens a dialog with the run's case, arm, repeat and outcome; its status and invalid reason; executor, setup, check and judge times; commands; "unconfined" when the run ran outside the sandbox and "not produced" when its artifact is missing; the judge's verdict, reason and question; every check value, required ones marked; the final-message excerpt; usage fields; and its native record, `RUN_DIR/runs/JOB/`, with a button that copies the path. The arrow keys move through runs in the ledger's current filter order.

### Browser behavior

The top bar holds the section index, marking the section in view and moving to its own scrollable row in windows narrower than 860 pixels, and a theme button that cycles Auto, Light and Dark. A chosen theme is kept in the browser's local storage under `av-theme` and applied before first paint; Auto follows the system.

## New block types

`AgenticVisuals.registerBlock(type, render)` adds a block type or replaces one, returning a function that restores the previous renderer; `blockTypes()` lists the registered types. A `type` is lowercase letters, digits and hyphens, starting with a letter. `render(block, ctx)` receives the block object and the render context and returns an HTML string. It must escape everything taken from data; `AgenticVisuals.escapeText` escapes a string or finite number and throws on anything else.

| Context | Use |
| --- | --- |
| `ctx.arms` | `tag(id, {id: false}?)`, `glyph(id)`, `label(id)`, `note(id)`, `color(id)` (a CSS color), `shape(id)`, `index(id)`, `ids()` |
| `ctx.trial`, `ctx.runs`, `ctx.runIndex` | The trial and its runs; an element with `data-run="${ctx.runIndex.get(run)}"` opens that run's drawer when selected |
| `ctx.caseLabels` | Case labels |
| `ctx.uid(base)` | A unique element id |

`AgenticVisuals.blocks.frame(kind, block, bodyHtml)` wraps a body in the shared block frame (title, description, note, id), and `renderBlock(block, ctx)` renders a built-in block inside a new one:

```js
AgenticVisuals.registerBlock("verbatim", (block, ctx) =>
  AgenticVisuals.blocks.frame("verbatim", block,
    `<ul>${block.items.map(i => `<li>${ctx.arms.tag(i.arm)} ${AgenticVisuals.escapeText(i.text)}</li>`).join("")}</ul>`));
```

Register before the report renders: in an assembled file, a script placed after the library runs before the automatic render ([PACKAGING.md](PACKAGING.md#custom-compositions) gives the command). Style a new block with an extra stylesheet built on the theme's custom properties (`--av-ink`, `--av-line`, `--av-pass`, `--av-fail`, `--av-arm-0` to `--av-arm-7` and the rest in [src/theme.ts](src/theme.ts)) so it follows both themes.

## Faithfulness guarantees

- **Invalid is not failure.** Every rate and interval counts valid runs only; invalid runs are counted beside them (ladder chip, tapestry count, cost rows, invalid section, ledger filter) and stay visible as marks in the tapestry and invalid views.
- **Uncertainty is drawn.** Rates from counts carry 95% Wilson intervals (ladder, intervals, trend), the ladder flags fewer than five valid runs, and identical arms show what chance alone produces.
- **Identity order is not rank.** Arms keep their identity order in every view unless a ladder sets `sort: "rate"`.
- **Missing stays missing.** "missing", "not established", "not run", "no valid runs", "no value", "N missing" and "N at 0" replace absent values; nothing becomes a zero or a blank.
- **Order disagreement is reported.** Order-inconsistent and invalid pairs are their own segments, and win rates use decisive pairs only.
- **Cost is per run.** Every valid run is a dot, medians and quartiles describe valid runs, log scales and axes that do not start at zero are labelled, and differences are the trial's per-case medians, never one pooled number.
- **Checks keep their roles.** Required checks, the judge and directionless measures are separate groups.
- **The decision is the author's.** The verdict shows only what the narrative or specification states, with the plan's rule verbatim; without a decision it says none was recorded.
- **Evidence text stays text.** All supplied text is escaped; prose fields recognize only inline code and strong.
- **Every run reaches its record.** The drawer names each run's native record directory.

## What is not offered

- Verdicts, scores, weights, composite rankings, significance tests or effect sizes: the only statistics are pass rates, Wilson intervals, medians and quartiles, plus the trial's own percent differences.
- Raw HTML, Markdown blocks or scripts inside a specification: a new kind of view is a registered block.
- Totals that hide per-run or per-case values.
- Network access, remote fonts, analytics, annotations, sharing or saved reader state beyond the theme choice.
- Rendering without JavaScript: the page draws itself from its embedded data, and without scripts the reader sees a notice and the JSON.
