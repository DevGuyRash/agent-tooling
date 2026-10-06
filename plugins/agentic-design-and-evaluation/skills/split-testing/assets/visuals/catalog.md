# Visual Library Catalog

The library turns data into one report page. A report is a **specification**: a title and a list of sections, each holding **blocks** that name their `type` and carry their own fields. The page renders in the reader's browser from JSON embedded in the file, so a report is composed from data rather than written as markup. The library draws what it is given; from trial runs it computes only pass rates with 95% Wilson intervals, differences between pass rates with 95% Newcombe intervals, medians and quartiles, and it never decides, scores or ranks (see [What is not offered](#what-is-not-offered)).

Two entries reach it:

- **A trial.** `trial.py report RUN_DIR --out trial.json` writes the data. `report.py --skeleton narrative.json --trial trial.json` starts a narrative, `report.py --check --trial trial.json --narrative narrative.json` lists its problems, and `report.py --trial trial.json --narrative narrative.json --output report.html` composes the default trial report from it ([Trial composition](#trial-composition)). This is the quickest faithful path.
- **A specification.** `report.py --spec spec.json [--trial trial.json] --output report.html` renders a specification you write, mixing trial and general blocks.

[PACKAGING.md](PACKAGING.md) covers these commands, custom compositions and checking a report before delivery. [examples/](examples/) holds a fictional trial (`fictional-trial.json`, written by `make_fictional_trial.py`), a narrative for it (`fictional-narrative.json`) and a specification that uses every general block once (`showcase-spec.json`); `python3 examples/assemble-previews.py --output DIR` renders all three.

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
| `problems` | `[Problem]` | Set by `trialReport` to its narrative's problems; the page lists them ([Input checks](#input-checks)). Not written by hand. |

**Text.** Fields marked *text* (`summary`, `lead`, `description`, `detail`, `text`, `rule`) take a string, split into paragraphs at blank lines, or an array of paragraphs. They and a few short fields (a verdict's `headline`, `alert` text and list entries, `list` items and details, non-`mono` `facts` values, a `callout` title) recognize only `` `code` `` and `**strong**`; every other character is escaped, so evidence text never becomes markup. Labels, table cells, notes, excerpts, prompts and follow-ups are escaped with no markup at all.

**Blocks.** A block is `{type, ...fields}`. Besides its own fields, every block accepts `title`, `description` (text), `note` (a closing line) and `id`, except where its entry says otherwise. An unknown `type` renders a visible notice listing the valid types, and a block that fails on its fields renders a notice with the reason in its place, so a report never silently drops a block.

## Input checks

`validateSpec(spec, {trial?})` and `validateNarrative(narrative, trial?)` return problems, each `{level, where, message, hint?}` with `where` naming the place in the input, such as `narrative.decision.verdict`. The page lists them in an "Input check" panel above the first section (an error opens the list; warnings alone leave it folded under a one-line summary; eight show, the rest sit behind a disclosure), and `report.py --check` prints the same problems without a browser ([PACKAGING.md](PACKAGING.md#checking-a-report-before-delivery)). A specification that `trialReport` composed carries its narrative's problems in `problems` and is not checked a second time. Checks against the trial's arms, cases, checks and pairwise keys run only when trial data is present, and a value close to a valid one gets a "did you mean" hint.

| Level | Input |
| --- | --- |
| error | Input that would break a view or make it misread: a wrong type, a missing or empty required field, an unknown block type, a verdict word outside the five, an arm, case, check, pairwise key or cost measure the data does not have, more passes than valid runs, arms called `identical` whose recorded settings differ, an unknown section id in `include`, `exclude`, `append` or `after`, a `threshold` outside −1 to 1, a trial block with no trial data. |
| warning | Input the report does not use as written: an unknown field, a label for an arm or case the trial lacks, a repeated section id or arm entry, a decision `rule` (the plan's is quoted), table cells beyond the columns, matrix cells, bar segments or trend stages that match nothing, a section left out by `include` or `exclude` that `after` or `append` names, a misspelled option word that falls back to its default (`tone`, `sort`, `by` and `pairs` on most blocks). |

The arms and cases the checks accept are those in the plan or the runs, while the composition uses only those that ran: a label or `baseline` naming a planned arm with no runs passes the check and is not used.

## Trial blocks

These read the specification's `trial`; without it they render a notice naming the missing field, except `verdict` and `figures`, which need none, and `ladder`, `contrast` and `setup`, which can take their own counts or settings. Invalid runs (`passed: null`) are counted apart from failures, never as failures. A run mark or ledger row opens the [run drawer](#the-run-drawer). A **case variant** is a case run a second way: the same prompt, judge, required checks and artifact as its base case, with more follow-up turns; blocks that take `pairs` draw a variant beside its base.

### verdict

The decision and its rule: a stamp, the headline, detail, up to three lists, and beside them the rule with the state of each rule check. With verdict `none` the rule leads the block.

| Field | Meaning |
| --- | --- |
| `verdict` | `adopt`, `reject`, `inconclusive`, `mixed` or `none` (any case; anything else is `none`); stamps read Adopt, Do not adopt, Inconclusive, Mixed, No decision recorded. |
| `label` | Replaces the stamp's word. |
| `headline` | The decision in one sentence (required). |
| `detail` | Text under the headline. |
| `conditions`, `limits`, `changes` | String lists headed "Holds when", "Does not show", "Would change it". |
| `rule` | The decision rule, quoted and labelled "fixed before results"; pass only a rule that was. |
| `checks` | `[{label, observed, threshold?, met, group?}]`; `met` true, false or null reads met, not met, not evaluated. Ungrouped checks are the rule's terms that decide the verdict and come first; checks with a `group` follow, each group under its own subheading in the order first named. |
| `mentions` | Case or arm ids the rule names, with verdict `none` only: each is listed with its passed and valid counts (per arm when several ran, with its variants), headed "Named in the rule". When it names some cases, the cases it does not name are pooled into one entry ("The other N cases together", their variants apart). A note says the counts are counts only and the report does not apply the rule. |
| `pairs` | `[{base, variant, label?, note?}]`: a named base case also shows its variant's counts. |
| `alert` | `{text, href?, link?}`: a notice under the headline; `href` is a section anchor such as `#invalid`. |

Limit: the decision is shown as written; nothing is computed from or checked against the data, and `mentions` adds counts, never a reading of them.

### figures

A row of headline numbers. `items: [{value, label, note?, tone?}]`, `tone` one of `neutral`, `pass`, `fail`, `warn`, `invalid`. Whole numbers get thousands separators, other numbers a compact form (0.87, 4.2k), and a null value shows as missing; pass a formatted string such as `"87%"` for a unit.

### ladder

Pass rate per arm: a point at passed over valid runs, its 95% Wilson interval, the fraction and rate, a chip counting invalid runs, and an `n = …` chip below five valid runs, on a fixed 0–100% axis.

| Field | Meaning |
| --- | --- |
| `rows` | `[{arm, k, n, invalid?, note?}]` to draw your own counts (`case` in place of `arm` with `by: "case"`); omitted, runs are tallied from the trial. |
| `by` | `arm` (default) or `case`: one row per case, each variant beneath its base. |
| `case`, `cases`, `arms` | Tally one case, only the listed cases, or only the listed arms (default every case and arm; by case, the arms' runs are pooled per case). |
| `identical` | Groups of arm ids given identical material. Each group sits together with the spread between its rates drawn as a band ("N points apart"): what chance alone produced. |
| `baseline` | An arm whose rate draws a labelled dashed reference line, and whose row is marked "baseline". |
| `references` | `[{value, label}]`, rates in 0–1 drawn as labelled dotted lines across every row, such as a decision rule's bar. |
| `sort` | `identity` (default) or `rate`. |
| `pairs` | `[{base, variant, label?, note?}]`, by case: places each variant under its base, marked "↳". |

Limit: pooling weights cases by their valid runs; read `cases` or `tapestry` when cases differ.

### tapestry

Every run as one mark in a grid of cases by arms. A cell shows passed over valid runs, its invalid count, a bar marking the pass share within its 95% interval (the interval is also in the cell's tooltip and accessible name), and its marks in repeat order; a combination never run says "not run". Fields: `arms` and `cases` (subsets; arms keep identity order, cases the order given), `transpose` (arms as rows; on by default with more than eight arms and fewer cases than arms), `groups: [{label, cases, note?}]` (sections the case rows under named sets, each headed by its case count, passed over valid runs and invalid count, with ungrouped cases under "Other cases"; groups turn transposition off), `pairs` (as in `ladder`: a variant's row follows its base).

### checks

How often each check held per arm over valid runs, passed over valid runs with a shaded bar.

| Field | Meaning |
| --- | --- |
| `by` | `check`: one table in three groups, **Required checks** (counted over the cases that require each, with "in N of M cases" when not all do; rows that held in every run of every arm fold away once there are more than three), **Judge** (runs the judge passed, of valid judged runs) and **Recorded measures** (other booleans, "recorded, not required for a pass", shaded by share with no pass direction; measures that never change fold away once there are more than three). `case`: one panel per case with its passed count per arm, a "Must hold" table (checks that failed somewhere first, then "Judge says pass"), the checks that held everywhere folded, and recorded measures folded ("recorded, not required for a pass"; true or false shares, numbers as a median with the range); a case where everything held collapses to one sentence. Default `case` when there are several cases and a required check is not shared by all of them, otherwise `check`. |
| `arms`, `cases`, `checks` | Subsets; `checks` names the checks to keep. |
| `pairs` | Variants follow their bases. |
| `required` | `false` shows only the recorded measures by case, for a page whose case views already show the required checks and judge. |

Limit: a check that ever records a non-boolean value is left out of the by-check table, and one that records text is left out of the by-case measures too (numbers show there as measures); the drawer shows every value.

### pairwise

Blind pairwise judgments from `trial.py pairwise`. Per pair, one stacked bar for all cases and one per case: the first arm preferred in both orders, ties, the second arm preferred, order-inconsistent pairs and invalid pairs, with the first arm's win rate and interval over decisive pairs only ("no decisive pairs" otherwise). Bar length is the number of pairs on one scale shared by every row, the all-cases row included, so a case with fewer pairs draws a shorter bar; the legend lists only the outcomes present. Field: `pair`, a key such as `"A__B"` (default every pair).

### cost

One strip per measure and arm, with a dot per valid run (filled for a pass, a ring for a failure), the middle half and median of valid runs, a count of the arm's invalid runs beside the row ("N not shown": their cost is real, but a timeout is not a measurement of the task and would flatten the axis), and, when the trial names a baseline, the median across cases of the per-case percent difference `trial.py report` computed. Measures appear when some valid run records a positive value: `output_tokens`, `input_tokens`, `seconds` (executor time), `commands`, `total_cost_usd`. A range wider than 40 times turns the axis logarithmic, labelled so, with runs at zero counted beside it; otherwise a linear axis starts at zero unless the values sit far from it, in which case the panel says where it starts, and it ends on a labelled tick at or past the largest value. Time ticks share one unit per axis, and a duration of a minute or more reads like "1 min 26 s". The legend keys fill (passed, failed) in a neutral ink, since a dot takes its arm's color, and says so when several arms ran. Fields: `measures` (those ids), `arms`. Limits: executors report different usage fields, so compare like with like; when an executor reports `cache_read_input_tokens` or `cache_creation_input_tokens` apart from `input_tokens`, the input-token measure adds them back, says so in its title, and drops the baseline difference, since `trial.py`'s covers `input_tokens` alone; every other difference uses the trial's own `baseline` (from `--baseline` or the plan), never a narrative's.

### invalid

Invalid runs grouped by `invalid_reason` (else `status`), each group with the reason in plain words, the command that would give those runs a result (such as `trial.py run --retry-invalid` or `trial.py recheck RUN_DIR --rejudge`), counts per arm, the opening of the first run's message and a mark per run. The default description gives their share; with none, it says every run finished valid. Frame fields only.

### ledger

Every run in a table: number, outcome, case, arm, repeat, judge verdict, output tokens (when recorded), time (seconds, or m:ss past a minute) and **Why**: the required checks that did not hold (first three, then a count), the judge's reason, or the invalid reason in words; for a pass, the first 240 characters of the judge's reason. In the browser it gains outcome, arm and case filters, a text search, an "N of M runs" count, sortable columns, CSV export and a row that opens the drawer by click or Enter; at phone width the first 20 matching runs show as cards until "Show all N runs" ([Browser behavior](#browser-behavior)). Frame fields only.

### plan

The arms' recorded settings and each case's definition as a raw table: a column for every setting some arm records (digests shortened, in full on hover; values as written; instruction and artifact texts left out), arm notes, the judge's executor, model and effort, the run directory, and each case that ran as an expandable entry with description, prompt, follow-ups, judge question and criterion, and required checks. Frame fields only. `setup` is the reader-facing account of the same plan; `plan` stays for callers that want the table.

### setup

What was compared, read from the plan: one sentence on how the arms differ (or that they received the same recorded settings, so any difference is chance), a line saying whether every arm ran the same cases and how many runs per case (per arm when only the arms differ in it; a warning when not every arm ran every case), the settings every arm shares, a table of only the settings that differ, the judge's settings, and the instruction and artifact texts themselves. Texts are lettered (Text A, Text B; Artifact A, …), each with the arms that used it, its size and digest, and compared by digest. Each text other than the reference (the baseline's, else the first with text) shows a line diff from it, with lines added and removed counted and changed words marked inside replaced lines; long unchanged stretches fold (three lines stay beside each change), and the full text is one disclosure away. With one arm no arms are compared, and the view says what is compared instead (each case against its own pass criteria, or a case and its variant). Case variants appear as the follow-up turns they add, once per distinct addition with the cases it applies to; a pair that differs in more than added turns is named, not described. With several arms and variants, the variants lead: the opening sentence names them and their section comes before the settings, since they ran on every arm and are a comparison of their own.

| Field | Meaning |
| --- | --- |
| `arms` | Subset of the trial's arms. |
| `baseline` | The arm whose text is the diff reference, marked "baseline" (default the trial's baseline). |
| `identical` | Groups of arm ids meant to receive identical material. An arm whose every recorded setting matches another's is marked "identical material"; a listed arm that differs is marked "listed as identical but differs in …". |
| `hide` | Setting names to leave out, such as `"base_url"`. |
| `settings` | Arm settings keyed by arm id, in place of the plan's (needs no trial). |
| `judge` | The judge's settings in place of the plan's; `null` shows none. |
| `pairs` | Case variants whose added turns to show: found by content (default `"auto"`), `"off"`, or `[base, variant]` or `{base, variant}` pairs. |

Every recorded setting is shown (executor, model, effort, base URL, command, allowed tools, permission and approval modes, resources, stub skills, digests and any other), `model` as resolved with the plan's `model_spec` on hover, long values folded behind "Show all", and a home-directory prefix anywhere in a value (a command line, a config path) read as `~`. A judge that uses the same model as an arm it scores is flagged "same model". An arm with no recorded settings says so, and a planned arm that never ran is footnoted. Limits: a text reaches the report only while the run directory still holds content matching its digest, cut at 24,000 characters (marked "cut"); otherwise the view says "not in this report" and names the run directory's `instructions/` or `artifacts/` folder.

### cases

Case dossiers, one per case in plan order. A header gives the case, its chips (required checks, judged, follow-ups, variants) and each arm's passed over valid runs. **The task** shows the case's description, the prompt and follow-ups verbatim, and the name of the judged output file. **What counted as a pass** states the rule as `trial.py` applies it (every required check exactly true and, where the case's judge decides, a verdict of pass), a table of how often each required check and the judge's verdict held per arm, and the judge's question, criterion and framing; a criterion of up to 4,000 characters shows whole, since it is what decided the runs. **How it went** gives each arm, under a 0, 50 and 100% axis, a pass-rate track with its 95% Wilson interval, passed over valid runs, an `n = …` chip below five valid runs, one mark per run that opens the drawer, the failed checks as chips and an invalid count; then "Why runs failed", most frequent first (three shown, up to twelve more folded). Runs that failed the same way, on the same required checks or the judge's verdict, are one reason with a count (and, with several arms, a count per arm); when the recorded values or the judge's words differ inside it they are listed beneath, and a failure the data name no cause for keeps its own words. Each reason has an "open" button for its first run. With two or more entries an overview opens the block: "Pass rate by case" for one arm, "Cases at a glance" (each arm's rate as its shape, plus the pooled figure) for several; shapes stack only where a rate lies within about 3.5 points of its neighbour's, so they would touch. A base case and its variants share one dossier, side by side: each variant's result against its base's in points with a 95% Newcombe interval, and as passes gained or lost ("+2 passes of 3") when both sides had the same number of valid runs, "What differs" listing the differences the plan records, and a pooled row when several arms ran.

| Field | Meaning |
| --- | --- |
| `cases`, `arms` | Subsets in the order wanted (default every case in the plan, then any only the runs name; every arm that ran). |
| `groups` | `[{label, cases, note?}]`: headings with their case and passed counts, unless a variant set crosses groups, when the group labels name the variants instead. |
| `pairs` | Variant sets: `"auto"` (default; the same prompt where one case name extends another after a separator such as `-` or `_`), `"off"`, or a list of `[base, variant]`, `{base, variant or variants, label?, baseLabel?}` (`variants` a list or `{case: label}`) and `{suffix, label?, baseLabel?}` (every case X with X+suffix). |
| `index` | The overview; on by default with two or more entries. |

Limits: descriptions and judge texts are shown as prose (inline code and strong only), prompts and follow-ups verbatim; a long text shows a preview cut once, at a word, at about 230 characters, above a control that opens it whole; a description cut at 24,000 characters says so. When the recorded fields show no difference between a variant and its base, the view says the cases may differ in files the report does not carry (fixtures, setup, check code).

### failures

Why runs failed: every valid failed run grouped by what failed it, across cases and arms, from the same derivation the drawer and ledger use. Opens with how many of the valid runs failed, in how many cases and from how many causes; a run that failed several ways is listed under each cause, and the view says so. Each group is a required check that did not hold, the judge's verdict, or "failed with no recorded cause", headed by its runs over the valid runs that could have failed that way, with a "k of n" per arm (zeros kept), then by case with a mark per run and the reason quoted: the judge's words, or a recorded text check named like `problems` or tied by name to the check. Identical words or values are gathered with a count of the runs that gave them and listed most frequent first; the rest sit behind a disclosure, and an index appears with three or more causes. Invalid runs are counted in the opening line and never enter a group. With no failed valid run in scope the block draws nothing, and the composition leaves its section out.

| Field | Meaning |
| --- | --- |
| `cases`, `arms` | Subsets (default all that ran). |
| `by` | `cause` (default) or `case`: one group per case with its causes beneath, and the cases with no failure named. |
| `reasons` | Reasons quoted per row before the rest fold away (default 1, at most 5). |

### contrast

How far one set of runs' pass rate sits from another's: per row the first rate minus the second in percentage points with a 95% Newcombe interval on a zero-centred axis, the counts of both sides, and a sentence saying whether the interval lies above zero, below it or includes it. With a `threshold` it also says where the interval sits against the bar. Invalid runs are left out of both sides and counted beside them. A row says "uneven case mix" when its sides spread their valid runs over the cases differently (a share more than 10 points apart, or a case with valid runs on one side only), and gets no interval when counts are missing, a side has no valid runs, `k` exceeds `n`, or the two sides share runs. Identical arms add a "Chance alone" group, and their largest gap draws as a band. Name the rows one of three ways:

| Form | Fields | Rows |
| --- | --- | --- |
| Counts | `rows: [{label?, arm?, vs?, note?, k1, n1, k2, n2, invalid1?, invalid2?, identical?}]` | Each `k1`/`n1` minus `k2`/`n2`; needs no trial; `identical: true` rows are the chance-alone group. |
| Baseline | `baseline` (an arm or a list; default the trial's), `arms`, `cases` | Each other arm minus the baseline over the cases given (default all), leaving out the baseline's identical copies. |
| Two sets | `a` and `b`, each `{label?, arms? or arm?, cases? or case?}`; or `pair` (a suffix string or `{suffix}`) | `a` minus `b`; with `pair`, each case's variant (case plus suffix) against its base case. |

With none of these and no baseline in the trial, several arms give every pair (later minus earlier), and one arm whose case names show variants compares them. Other fields: `by` (`arm` or `case`: extra rows per arm under a two-set comparison, or per case under each comparison; default `none`), `identical`, `threshold` (a share from −1 to 1 such as `0.15`, or `{value, label?}`, drawn as a bar), `sort` (`identity` default, or `difference`), `method` (`false` hides the method note). Limits: no p-values and no winners; the interval covers run-to-run variation on these cases, not cases the trial did not include; pooled rates weight cases by their valid runs.

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

`trialReport(trial, narrative)`, which `report.py --trial` runs, builds a specification from the trial data and an optional narrative. `SECTION_IDS` lists the ids in order; each default section's `id` is the one in the table, so `#cases`, `#failures`, `#invalid` and `#runs` link to them.

| Id | Title | Blocks | Present |
| --- | --- | --- | --- |
| `verdict` | Verdict | `verdict` from the narrative's `decision` and the plan's `decision_rule`, then `figures`: runs, valid, invalid, pass rate (one arm only), arms, cases (base cases, with "+N variants: M versions" beside them), repeats, judge | Always; without a `decision` the stamp reads "No decision recorded" and the rule leads, with `mentions` counts for the cases and arms it names and the other cases pooled. A `decision` of your own, even with verdict `none`, gets no automatic counts; give `mentions` yourself. |
| `setup` | What was compared | `setup` with the narrative's `baseline`, `identical` and pairs | Always. `plan` is accepted as its older name. |
| `arms` | Results by arm | `ladder` over all cases (left out when every case is in a variant pair), one for base cases and one for variants when there are pairs, one per `groups` entry; `contrast` "Difference from BASELINE" or "Difference between identical arms" when a baseline or `identical` is set (with `threshold`); with pairs, `contrast` of variants against base cases by arm, and with more than one pair a second, "Each variant against its base case", by pair | Several arms and a valid run. With one arm and variants, titled "Variants against base cases", holding only the variants `contrast`; otherwise absent. |
| `cases` | Case by case | `cases` in variant order, sectioned by `groups` | Always |
| `grid` | Every run | `tapestry`, sectioned by `groups`, variants beside bases | Only when `include` names `grid` and a run is valid; the dossiers already place every run. |
| `failures` | Why runs failed | `failures` | When a valid run failed |
| `checks` | Checks | `checks` | Several arms: a valid run, and runs record boolean checks or judge pass or fail verdicts. One arm: titled "Recorded measures" with `required: false`, when some case records measures beyond its required checks and judge, which its dossier already shows. |
| `pairwise` | Pairwise judgments | `pairwise` | When the trial has pairwise results |
| `cost` | Cost and time | `cost` | When a valid run records a cost measure |
| `invalid` | Invalid runs | `invalid` | When a run is invalid |
| `runs` | Run ledger | `ledger` | Always |

The composition decides case variants once and passes them to every block, so each view pairs the same cases; standalone blocks that detect variants themselves do so differently (`setup` by content, `cases` by name and prompt, `contrast` by name suffix), so give them explicit `pairs` in a specification of your own. With a fifth or more of the runs invalid, or all of them, the verdict carries an `alert` naming the reasons and linking to the invalid section; it takes the place of any `alert` the decision gives. A section with nothing to show is left out, and no view repeats another.

Every narrative field is optional:

| Field | Meaning |
| --- | --- |
| `title` | Report title; default `question`, then the trial's `name`, then "Trial results". |
| `question` | The practical question; the title when there is no `title`, otherwise a meta line. |
| `summary` | Text under the title; default a sentence on the trial's shape: arms, base cases with the case versions named ("2 of them also run with 1 follow-up turn added (6 case versions)"), repeats, runs and judge. With a decision rule and none of `title`, `question` and `summary`, it adds that the rule is the only statement of what was tested. |
| `kicker` | Default "Split test · NAME". |
| `decision` | The verdict block's fields except `rule` (always the plan's): `verdict`, `headline`, `detail`, `label`, `checks`, `conditions`, `limits`, `changes`, `mentions`, `pairs`. |
| `arms` | `[{id, label?, note?}]` or `{id: {label?, note?}}`; these lead the identity order, other arms follow the plan. Only arms that ran are used. |
| `cases` | `{scenario: label}`. |
| `identical` | Groups of arm ids given identical material, for the ladder's noise band, the `contrast` chance-alone group and the setup marks. |
| `groups` | `[{label, cases, note?}]`: named sets of cases (conditions, variants, rounds), each with its own ladder, a heading in the dossiers and its own section of the run grid. |
| `pairs` | Case variants as `[base, variant]` or `{base, variant, label?}`. Without this field they are found in the plan by content, never by name: the variant has the same prompt, judge, judge role, required checks and artifact as its base and repeats its follow-ups with more added (the closest base wins, a tie means none). `[]` turns variants off. |
| `baseline` | The reference arm for the ladder and difference views (default the trial's `baseline`). |
| `threshold` | The difference the decision rule asks for, on the difference view: a share such as `0.15` for +15 points, or `{value, label?}`; drawn only where the difference-from-baseline view appears (several arms and a `baseline`), and otherwise left out without a warning. |
| `include`, `exclude` | Default section ids to keep or drop (`grid` appears only through `include`). |
| `sections` | Extra sections, `{title, blocks, …, after?}`, each placed after the section whose id is `after` (a default id or an earlier extra's `id`), else at the end. |
| `append` | `{sectionId: [blocks]}` added to the end of a default section. |
| `footer` | Closing line; default, when the trial records `generated_at`, "Report data written DATE. Every view is drawn from the data embedded in this file, and each run names its native record." |

The meta lines hold the question (when a title is also given), "Ran" (the date range of the trial's `ran`, the first and last `result.json` times in UTC; the footer gives when the data were written) and the run directory, with a home-directory prefix shown as `~`. Write the `decision` after applying the plan's rule yourself; the composition carries the rule and the data, never a verdict of its own. [examples/fictional-narrative.json](examples/fictional-narrative.json) shows a complete decision. In JavaScript the result is an ordinary specification whose `sections` can be dropped, reordered or extended before rendering.

## Arm identity and run marks

Each arm gets one color (eight hues in an Okabe–Ito-based order, tuned per theme) and one shape (circle, square, diamond, triangle, hexagon, downward triangle, star, cross), the same in every view; the first 64 arms get distinct pairs. The order is the specification's `arms` (a narrative's `arms`), then arms as the trial's plan and runs list them. An arm tag shows the shape, the label and, where a label replaces the id, the raw id in code; compact views drop the id, while the ladder, pairwise headings, setup, plan and drawer keep it. Pointing at an arm tag highlights that arm within its block.

Run outcomes share one mark language: passed is a filled circle, failed a hollow ring, invalid a grey square struck through. Cost dots take the arm's color with the same fill or ring. Shape and fill carry the state and color only reinforces it; in forced-colors mode the marks keep distinct fills and borders.

### The run drawer

A run mark (in `cases`, `failures`, `tapestry`, `cost` or `invalid`) or a ledger row opens a dialog headed by the run's number, job id, case, arm, repeat and outcome. A failed run opens with why it failed, and an invalid run with why it has no result and what would give it one. Then its status; executor, setup, check and judge times (when recorded; a minute or more reads "1 min 26 s"); commands; "unconfined" when the run ran outside the sandbox and "not produced" when its artifact is missing; the judge's verdict, reason and question; every check value (required ones marked, those that did not hold first; other checks next; recorded text and numbers folded); the final output (the first 2,000 characters, said so at the limit); usage fields as the executor reported them; and its native record, `RUN_DIR/runs/JOB/` (a home-directory prefix read as `~`), with a button that copies the full path. Buttons and the arrow keys move to the previous or next run in the ledger's current filter order, and "Copy link" copies a link to the run.

### Browser behavior

Every view is drawn complete by the renderers; the browser layer only adds ways to move through the data.

| Feature | Behavior |
| --- | --- |
| Top bar | The section index marks the section in view and moves to its own scrollable row in windows narrower than 860 pixels; a theme button cycles Auto, Light and Dark. A chosen theme is kept in the browser's local storage under `av-theme` and applied before first paint; Auto follows the system. Two skip links lead to the first section and to the run ledger. |
| Deep links | `#cases` (any section id) scrolls to and focuses that section; each section's "Link" control copies its link. `#run-12` opens run 12 (its number in the ledger), and `#run-JOB` opens the run whose job id is `JOB`. `#runs?outcome=fail&arm=ID&case=ID&q=TEXT` restores the ledger's filters (`runs` is the ledger section's id in the composition). Opening a run puts `#run-N` in the address without adding history, and closing the drawer restores the address before it. |
| Run marks | Hovering or focusing a mark shows its accessible name at once as a tooltip (also any element with `data-av-tip`). Each tapestry, failures block, cost panel, invalid group or case dossier is one tab stop: arrows move between marks (up and down by row), Home and End go to the ends, Enter or Space opens the run. |
| Ledger | Outcome buttons, arm and case filters, a text search over each row, the "N of M runs" count, "Clear filters", and sorting by column header. At 640 pixels or less rows become cards, sorting moves to a select, and only the first 20 matching runs show until "Show all N runs". Rows are one tab stop: up and down arrows, Home and End move, Enter or Space opens. `/` jumps to the search from anywhere outside a field. |
| Export | The ledger offers "Download CSV" and "Copy CSV" for the runs in view, in their order, and "Download all trial data (JSON)"; the footer repeats the JSON download for any report that carries a trial. Files are named from the trial's name (`NAME-runs.csv`, `NAME-trial.json`). The CSV has one row per run (number, job, case and label, arm and label, repeat, outcome, cause, invalid reason, judge verdict and reason, seconds, output and input tokens as the executor reported them, cost, commands, record path, in full) and a `check.NAME` column per recorded check, in UTF-8 (a byte-order mark in the downloaded file) with CRLF lines; text that a spreadsheet would run as a formula gets a leading apostrophe. A viewer that blocks downloads is told to use "Copy CSV" or the embedded JSON. |
| Announcements | One polite live region on the page and one inside the drawer say what changed: filtered counts, the run reached by stepping, and whether a copy reached the clipboard. |
| Print | Paper gets the light theme with every collapsed disclosure opened, restored afterwards. |

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

Register before the report renders: in an assembled file, a script placed after the library runs before the automatic render ([PACKAGING.md](PACKAGING.md#custom-compositions) gives the command). A registered type has no entry in the input checks, so its fields are accepted as written. Style a new block with an extra stylesheet built on the theme's custom properties (`--av-ink`, `--av-line`, `--av-pass`, `--av-fail`, `--av-arm-0` to `--av-arm-7` and the rest in [src/theme.ts](src/theme.ts)) so it follows both themes.

## Faithfulness guarantees

- **Invalid is not failure.** Every rate, interval and difference counts valid runs only; invalid runs are counted beside them (ladder chip, tapestry and dossier counts, cost rows, failures opening line, invalid section, ledger filter) and stay visible as marks.
- **Uncertainty is drawn.** Rates from counts carry 95% Wilson intervals, differences between rates 95% Newcombe intervals (none when counts are missing, a side has no valid runs, or the sides share runs); fewer than five valid runs is flagged, identical arms show what chance alone produces, and a pooled difference over an "uneven case mix" says so.
- **Identity order is not rank.** Arms keep their identity order in every view unless a ladder sets `sort: "rate"` or a contrast sets `sort: "difference"`.
- **Missing stays missing.** "missing", "not established", "not run", "not recorded", "no valid runs", "no value", "not in this report", "N missing" and "N at 0" replace absent values; nothing becomes a zero or a blank.
- **Order disagreement is reported.** Order-inconsistent and invalid pairs are their own segments, and win rates use decisive pairs only.
- **Cost is per run.** Every valid run is a dot, medians and quartiles describe valid runs, log scales and axes that do not start at zero are labelled, input tokens that add back cache reads say so, and differences are the trial's per-case medians, never one pooled number.
- **Checks keep their roles.** Required checks, the judge and directionless measures are separate groups, and a case's pass criteria are stated as `trial.py` applies them.
- **One account of a failure.** The ledger, drawer, marks, dossiers and failures view read one derivation, `failureCause`, so they cannot disagree; a failed run whose data name no cause says so rather than guessing.
- **Settings and texts are as recorded.** `setup` shows the plan's recorded settings and texts, diffs the texts it has, marks a text it lacks or had to cut, and says when arms listed as identical are not.
- **The decision is the author's.** The verdict shows only what the narrative or specification states, with the plan's rule verbatim; without a decision it says none was recorded and counts only what the rule names. A `threshold` is drawn and described, never decided.
- **Evidence text stays text.** All supplied text is escaped; prose fields recognize only inline code and strong.
- **Input problems are listed.** A misspelled field, arm or block type appears in the page's input check, and an unknown block renders a notice instead of vanishing.
- **Every run reaches its record.** The drawer names each run's native record directory, and the CSV carries its path.

## What is not offered

- Verdicts, scores, weights, composite rankings, significance tests, p-values or effect sizes: the only statistics are pass rates with Wilson intervals, differences between rates with Newcombe intervals, medians and quartiles, plus the trial's own percent differences.
- Raw HTML, Markdown blocks or scripts inside a specification: a new kind of view is a registered block.
- Totals that hide per-run or per-case values.
- Network access, remote fonts, analytics, annotations, accounts or saved reader state beyond the theme choice: filters and links live in the address, and exports are files the reader saves.
- Anything `trial.py report` does not carry: transcripts and events stay in the native record, final outputs are cut at 2,000 characters, texts and descriptions at 24,000, and fixtures, setup and check code are not in the report.
- Rendering without JavaScript: the page draws itself from its embedded data, and without scripts the reader sees a notice and the JSON.
