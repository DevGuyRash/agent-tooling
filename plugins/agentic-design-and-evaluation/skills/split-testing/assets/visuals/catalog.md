# Visual Library Catalog

The library turns data into one report page. A report is a **specification**: a title and a list of sections, each holding **blocks** that name their `type` and carry their own fields. The page renders in the reader's browser from JSON embedded in the file, so a report is composed from data rather than written as markup. The library draws what it is given; from trial runs it computes only pass rates with 95% Wilson intervals, differences between pass rates with 95% Newcombe intervals, medians and quartiles, from a comparison of any alternatives only the [statistics](#metric-kinds) its views name, and it never decides, scores or ranks on its own (a weighted total appears only from weights the author supplies; see [What is not offered](#what-is-not-offered)).

Three entries reach it:

- **A trial.** `trial.py report RUN_DIR --out trial.json` writes the data. `report.py --skeleton narrative.json --trial trial.json` starts a narrative, `report.py --check --trial trial.json --narrative narrative.json` lists its problems, and `report.py --trial trial.json --narrative narrative.json --output report.html` composes the default trial report from it ([Trial composition](#trial-composition)); `--general` draws the same trial through the [comparison views](#from-a-trial) instead. This is the quickest faithful path.
- **A comparison of any alternatives.** `report.py --data comparison.json [--csv table.csv] [--narrative narrative.json] --output report.html` composes a report from [comparison data](#comparisons-of-any-alternatives): options, ads, designs, directions with alternatives inside them, rated, measured, counted, ranked or judged head to head.
- **A specification.** `report.py --spec spec.json [--trial trial.json] [--data comparison.json | --csv table.csv] --output report.html` renders a specification you write, mixing trial, comparison and general blocks.

[PACKAGING.md](PACKAGING.md) covers these commands, custom compositions and checking a report before delivery. [examples/](examples/) holds a fictional trial (`fictional-trial.json`, written by `make_fictional_trial.py`), a narrative for it (`fictional-narrative.json`), a specification that uses every general block once (`showcase-spec.json`) and the [five comparisons](#comparisons-of-any-alternatives); `python3 examples/assemble-previews.py --output DIR` renders all of them as eight pages.

## Specification

| Field | Type | Meaning |
| --- | --- | --- |
| `title` | string, required | The report's heading. |
| `sections` | array, required | `{title, blocks, label?, id?, lead?}`, numbered 01, 02, … in order. `label` is the section-index entry (default `title`); `lead` is text under the heading; `id` is kept when it starts with a letter and holds only letters, digits, `_`, `.`, `:` or `-`, otherwise one is derived from the title. |
| `kicker` | string | A line above the title, shown only when set, and the top bar's name (default "Report"). |
| `summary` | text | Paragraphs under the title. |
| `meta` | `[{label, value}]` | Facts under the summary. |
| `arms` | `[{id, label?, note?}]` | Identity order and readable labels ([Arm identity](#arm-identity-and-run-marks)). |
| `cases` | `{id: label}` | Readable labels for trial cases, and for comparison cases the comparison does not label. |
| `trial` | object | The `trial.py report` JSON that trial blocks and the run drawer read; `report.py --trial` fills it when the specification has none. |
| `comparison` | object | [Comparison data](#comparison-data) that the comparison views read; `report.py --data` or `--csv` fills it when the specification has none. |
| `footer` | string | Closing line; the default says every view is drawn from the embedded data. |
| `problems` | `[Problem]` | Set by `trialReport` to its narrative's problems; the page lists them ([Input checks](#input-checks)). Not written by hand. |

**Text.** Fields marked *text* (`summary`, `lead`, `description`, `detail`, `text`, `rule`) take a string, split into paragraphs at blank lines, or an array of paragraphs, except a verdict's `rule` (and a comparison's `decision_rule`), which takes a string only: an array renders nothing and no check reports it. They and a few short fields (a verdict's `headline`, `alert` text and list entries, `list` items and details, non-`mono` `facts` values, a `callout` title, an alternative's `note`) recognize only `` `code` `` and `**strong**`; every other character is escaped, so evidence text never becomes markup. Labels, table cells, other notes, excerpts, prompts and follow-ups are escaped with no markup at all.

**Blocks.** A block is `{type, ...fields}`. Besides its own fields, every block accepts `title`, `description` (text), `note` (a closing line) and `id`, except where its entry says otherwise. An unknown `type` renders a visible notice listing the valid types, and a block that fails on its fields renders a notice with the reason in its place, so a block in a section is never dropped silently; only a block `append`ed to a default section that is left out does not appear ([Trial composition](#trial-composition)).

## Input checks

`validateSpec(spec, {trial?, comparison?})`, `validateNarrative(narrative, trial?)` and `validateComparison(comparison, narrative?)` return problems, each `{level, where, message, hint?}` with `where` naming the place in the input, such as `narrative.decision.verdict`. The page lists them in an "Input check" panel above the first section (an error opens the list; warnings alone leave it folded under a one-line summary; eight show, the rest sit behind a disclosure), and `report.py --check` prints the same problems without a browser ([PACKAGING.md](PACKAGING.md#checking-a-report-before-delivery)), except that it reports a registered block type as unknown. A specification that `trialReport` composed carries its narrative's problems in `problems` and is not checked a second time. Checks against the trial's arms, cases, checks and pairwise keys run only when trial data is present, checks against a comparison's alternatives, metrics and cases only when comparison data is present (a block with its own `data` is checked against it), and a value close to a valid one gets a "did you mean" hint.

| Level | Input |
| --- | --- |
| error | Input that would break a view or make it misread: a wrong type, a missing or empty required field, an unknown block type, a verdict word outside the five, an arm, case, check, pairwise key or cost measure the data does not have, more passes than valid runs, a trial block with no trial data. In a narrative only: arms called `identical` whose recorded settings differ, an unknown section id in `include`, `exclude`, `append` or `after`, a `threshold` outside −1 to 1. In a comparison: an alternative, metric or baseline id it does not have, a repeated alternative, case or metric id, a value that does not fit its metric's kind, a count without `n` or with more successes than trials, an ordinal value or a `counts` key outside the levels (or text values with no levels), `k` above `n`, a `lo` above `hi`, an aggregate missing what its kind needs, a judgment against itself or with a winner outside the pair, an alternative placed twice in a ranking, a rate `threshold` outside 0–1, a comparison block with no comparison data; in a comparison narrative, a criterion with no `metric`, `scores` or cells, a negative weight. |
| warning | Input the report does not use as written: an unknown field, a label for an arm or case the trial lacks, a repeated section id, table cells beyond the columns, matrix cells, bar segments or trend stages that match nothing, a misspelled option word that falls back to its default (`tone`, `sort`, `by`, `pairs`, `orient` and `center` on most blocks). In a narrative only: a repeated arm entry, a decision `rule` (the plan's is quoted), a section left out by `include` or `exclude` that `after` or `append` names. In a comparison: a case named in the data but missing from a non-empty `cases` list (shown by its id), a metric with no data, `levels` on a non-ordinal metric or `n` on a non-count one, more than one `primary` metric, a judgment naming a metric of another kind, an `identical` group of fewer than two; in a comparison narrative, only some criteria carrying a weight, a `decision.rule` (the data's `decision_rule` is quoted). |

`report.py --check --trial T --general --narrative N` confirms only that the narrative is a JSON object: the page checks the ids it names against the comparison derived from the trial. The arms and cases the checks accept are those in the plan or the runs, while the composition uses only those that ran: a label or `baseline` naming a planned arm with no runs passes the check and is not used.

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
| `checks` | `[{label, observed, threshold?, met?, group?}]`; `met` true reads met, false not met, null or left out not evaluated. Ungrouped checks are the rule's terms that decide the verdict and come first; checks with a `group` follow, each group under its own subheading in the order first named. |
| `mentions` | Case or arm ids the rule names, with verdict `none` only: each is listed with its passed and valid counts (per arm when several ran, with its variants), headed "Named in the rule". When it names some cases, the cases it does not name are pooled into one entry ("The other N cases together", or "The one case the rule does not name, ID" when one is left; their variants apart). A note says the counts are counts only and the report does not apply the rule. |
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

Every run as one mark in a grid of cases by arms. A cell shows passed over valid runs, its invalid count, a bar marking the pass share within its 95% interval (the interval is also in the cell's tooltip and accessible description), and its marks in repeat order; a combination never run says "not run". Fields: `arms` and `cases` (subsets; arms keep identity order, cases the order given), `transpose` (arms as rows; on by default with more than eight arms and fewer cases than arms), `groups: [{label, cases, note?}]` (sections the case rows under named sets, each headed by its case count, passed over valid runs and invalid count, with ungrouped cases under "Other cases"; groups turn transposition off), `pairs` (as in `ladder`: a variant's row follows its base).

### checks

How often each check held per arm over valid runs, passed over valid runs with a shaded bar.

| Field | Meaning |
| --- | --- |
| `by` | `check`: one table in three groups, **Required checks** (counted over the cases that require each, with "in N of M cases" when not all do; with more than three required checks, the rows that held in every run of every arm fold away), **Judge** (runs the judge passed, of valid judged runs) and **Recorded measures** (other booleans, "recorded, not required for a pass", shaded by share with no pass direction; with more than three measures, those that never change fold away). `case`: one panel per case with its passed count per arm, a "Must hold" table (checks that failed somewhere first, then "Judge says pass"), the checks that held everywhere folded, and recorded measures folded ("recorded, not required for a pass"; true or false shares, numbers as a median with the range); a case where everything held collapses to one sentence. Default `case` when there are several cases and a required check is not shared by all of them, otherwise `check`. |
| `arms`, `cases`, `checks` | Subsets; `checks` names the checks to keep. |
| `pairs` | Variants follow their bases. |
| `required` | `false` shows only the recorded measures by case, for a page whose case views already show the required checks and judge. |

Limit: a check that ever records a non-boolean value is left out of the by-check table, and one that records text is left out of the by-case measures too (numbers show there as measures); the drawer shows every value.

### pairwise

Blind pairwise judgments from `trial.py pairwise`. Per pair, one stacked bar for all cases and one per case: the first arm preferred in both orders, ties, the second arm preferred, order-inconsistent pairs and invalid pairs, with the first arm's win rate and interval over decisive pairs only ("no decisive pairs" otherwise). Bar length is the number of pairs on one scale shared by every row, the all-cases row included, so a case with fewer pairs draws a shorter bar; the legend lists only the outcomes present. Field: `pair`, a key such as `"A__B"` (default every pair).

### cost

One strip per measure and arm, with a dot per valid run (filled for a pass, a ring for a failure), the middle half and median of valid runs, a count of the arm's invalid runs beside the row ("N not shown": their cost is real, but a timeout is not a measurement of the task and would flatten the axis), and, when the trial names a baseline, the median across cases of the per-case percent difference `trial.py report` computed. Measures appear when some valid run records a positive value: `output_tokens`, `input_tokens`, `seconds` (executor time), `commands`, `total_cost_usd`. A range wider than 40 times turns the axis logarithmic, labelled so, with runs at zero counted beside it; otherwise a linear axis starts at zero unless the values sit far from it, in which case the panel says where it starts, and it ends on a labelled tick at or past the largest value. Time ticks share one unit per axis, and a duration of a minute or more reads like "1 min 26 s". The legend keys fill (passed, failed) in a neutral ink, since a dot takes its arm's color, and says so when several arms ran. Fields: `measures` (those ids), `arms`. Limits: executors report different usage fields, so compare like with like; when an executor reports `cache_read_input_tokens` or `cache_creation_input_tokens` apart from `input_tokens`, the input-token measure adds them back, says so in its title, and drops the baseline difference, since `trial.py`'s covers `input_tokens` alone; every other difference uses the trial's own `baseline` (from `--baseline` or the plan), never a narrative's.

### invalid

Invalid runs grouped by `invalid_reason` (else `status`), each group with the reason in plain words, the command that would give those runs a result (such as `trial.py run PLAN --out RUN_DIR --retry-invalid` or `trial.py recheck RUN_DIR --rejudge`), counts per arm, the opening of the first run's message and a mark per run. The default description gives their share; with none, it says every run finished valid. Frame fields only.

### ledger

Every run in a table: number, outcome, case, arm, repeat, judge verdict, output tokens (when recorded), time (seconds, or m:ss past a minute) and **Why**: the required checks that did not hold (first three, then a count), the judge's reason, or the invalid reason in words; for a pass, the first 240 characters of the judge's reason. In the browser it gains outcome, arm and case filters, a text search, an "N of M runs" count, sortable columns, CSV export and a row that opens the drawer by click or Enter; at phone width the first 20 matching runs show as cards until "Show all N runs" ([Browser behavior](#browser-behavior)). Frame fields only.

### plan

The arms' recorded settings and each case's definition as a raw table: a column for every setting some arm records (digests shortened, in full on hover; values as written; instruction and artifact texts left out), arm notes, the judge's executor, model and effort, the run directory, and each case that ran as an expandable entry with description, prompt, follow-ups, judge question and criterion, and required checks. Frame fields only. `setup` is the reader-facing account of the same plan; `plan` serves callers that want the table.

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

Case dossiers, one per case in plan order. A header gives the case, its chips (required checks, judged, follow-ups, variants) and each arm's passed over valid runs. **The task** shows the case's description, the prompt and follow-ups verbatim, and the name of the judged output file. **What counted as a pass** states the rule as `trial.py` applies it (every required check exactly true and, where the case's judge decides, a verdict of pass), a table of how often each required check and the judge's verdict held, pooled over every arm shown (one column per version of a variant set), and the judge's question, criterion and framing; a criterion of up to 4,000 characters shows whole, since it is what decided the runs. **How it went** gives each arm, under a 0, 50 and 100% axis, a pass-rate track with its 95% Wilson interval, passed over valid runs, an `n = …` chip below five valid runs, one mark per run that opens the drawer, the failed checks as chips (with several arms) and an invalid count; then "Why runs failed", most frequent first (three shown, up to twelve more folded). Runs that failed the same way, on the same required checks or the judge's verdict, are one reason with a count (and, with several arms, a count per arm); when the recorded values or the judge's words differ inside it they are listed beneath, and a failure the data name no cause for keeps its own words. Each reason has an "open" button for its first run. With two or more entries an overview opens the block: "Pass rate by case" for one arm, "Cases at a glance" (each arm's rate as its shape, plus the pooled figure) for several; shapes stack only where a rate lies within about 3.5 points of its neighbour's, so they would touch. A base case and its variants share one dossier, side by side: each variant's result against its base's in points with a 95% Newcombe interval, and as passes gained or lost ("+2 passes of 3") when both sides had the same number of valid runs, "What differs" listing the differences the plan records, and a pooled row when several arms ran.

| Field | Meaning |
| --- | --- |
| `cases`, `arms` | Subsets. `cases` keep the order given (default every case in the plan, then any only the runs name); `arms` keep identity order (default every arm that ran). |
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
| `rows` | Arrays of cells: a string, number, boolean (yes or no), null ("missing"), or `{value, status?, note?, mono?}`. A `status` of `pass`, `fail` or `invalid` adds the run mark, and `pass` and `fail` color the text; `neutral`, `warn` and `accent` change nothing in a table. |
| `numeric` | Column indexes to right-align (number cells align anyway). |
| `rowHeader` | The first column is a row header unless `false`. |

Numbers print exactly as given. With no rows it says so.

### matrix

Requirements against alternatives. `columns: [{id, label, arm?}]` (`arm: true` shows the arm named by `id`), `rows: [{id, label, detail?}]`, `cells: [{row, column, status?, text?, note?}]`, `status` an outcome or a tone. A missing cell, or one with status `missing`, reads "not established".

### intervals

Values with intervals on one axis, drawn like the ladder. `rows: [{label, arm?, k?, n?, value?, lo?, hi?, note?}]`: `k` and `n` give a rate with its 95% Wilson interval; otherwise `value`, `lo` and `hi` are drawn as given, and a row without a value says so. `percent` (default when every row is a count or a value within 0–1), `domain` (`[min, max]`; default 0–1 for percents, otherwise from 0, or the lowest negative value, to the largest), `unit` (after non-percent numbers), `reference: {value, label}` (a labelled line).

### bars

Composition. `segments: [{id, label, tone?}]`, `rows: [{label, arm?, values: {segment: number or null}, note?}]`. Each row is a bar split in proportion, with its total and "N missing" for segments without a number. Limits: a row with `arm` shows the arm's tag, and its own `label` as a note when that differs from the arm's label; a segment's number prints only when it fills more than 7% of the bar.

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
| `verdict` | Verdict | `verdict` from the narrative's `decision` and the plan's `decision_rule`, then `figures`: runs, valid, invalid, pass rate (one arm only), arms, cases (base cases, with "+N variants: M versions" beside them), repeats, judge | Always; without a `decision` the stamp reads "No decision recorded" and the rule leads, with `mentions` counts for the cases and arms it names (an id of letters only counts when the rule sets it in backticks) and the other cases pooled. A `decision` of your own, even with verdict `none`, gets no automatic counts; give `mentions` yourself. |
| `setup` | What was compared | `setup` with the narrative's `baseline`, `identical` and pairs | Always. `plan` is another id for it. |
| `arms` | Results by arm | `ladder` over all cases (left out when every case is in a variant pair), one for base cases and one for variants when there are pairs, one per `groups` entry; `contrast` "Difference from BASELINE" or "Difference between identical arms" when a baseline or `identical` is set (with `threshold`); with pairs, `contrast` of variants against base cases by arm, and with more than one pair a second, "Each variant against its base case", by pair | Several arms and a valid run. With one arm and variants, titled "Variants against base cases", holding only the variants `contrast`; otherwise absent. |
| `cases` | Case by case | `cases` in variant order, sectioned by `groups` | Always |
| `grid` | Every run | `tapestry`, sectioned by `groups`, variants beside bases | Only when `include` names `grid` and a run is valid; the dossiers already place every run. |
| `failures` | Why runs failed | `failures` | When a valid run failed |
| `checks` | Checks | `checks` | Several arms: a valid run, and runs record boolean checks or judge pass or fail verdicts. One arm: titled "Recorded measures" with `required: false`, when some case records measures beyond its required checks and judge, which its dossier already shows. |
| `pairwise` | Pairwise judgments | `pairwise` | When the trial has pairwise results |
| `cost` | Cost and time | `cost` | When a valid run records a cost measure |
| `invalid` | Invalid runs | `invalid` | When a run is invalid |
| `runs` | Run ledger | `ledger` | Always |

The composition decides case variants once and shares them with every view, so each view pairs the same cases (the verdict only when you give no `decision`); standalone blocks that detect variants themselves do so differently (`setup` by content, `cases` by name and prompt, `contrast` by name suffix), so give them explicit `pairs` in a specification of your own (`contrast` has none: give it `a` and `b`, or a `pair` suffix). With a fifth or more of the runs invalid, or all of them, the verdict carries an `alert` naming the reasons and linking to the invalid section; it takes the place of any `alert` the decision gives. A section with nothing to show is left out, and no view repeats another.

Every narrative field is optional:

| Field | Meaning |
| --- | --- |
| `title` | Report title; default `question`, then the trial's `name`, then "Trial results". |
| `question` | The practical question; the title when there is no `title`, otherwise a meta line. |
| `summary` | Text under the title; default a sentence on the trial's shape: arms, base cases with the case versions named ("2 of them also run with 1 follow-up turn added (6 case versions)"), repeats, runs and judge. With a decision rule and none of `title`, `question` and `summary`, it adds that the rule is the only statement of what was tested. |
| `kicker` | Default "Split test · NAME". |
| `decision` | The verdict block's fields except `rule` (always the plan's): `verdict`, `headline`, `detail`, `label`, `checks`, `conditions`, `limits`, `changes`, `mentions`, `pairs`, `alert`. |
| `arms` | `[{id, label?, note?}]` or `{id: {label?, note?}}`; these lead the identity order, other arms follow the plan. Only arms that ran are used. |
| `cases` | `{scenario: label}`. |
| `identical` | Groups of arm ids given identical material, for the ladder's noise band, the `contrast` chance-alone group and the setup marks. |
| `groups` | `[{label, cases, note?}]`: named sets of cases (conditions, variants, rounds), each with its own ladder (with several arms), a heading in the dossiers and its own section of the run grid (when `include` names `grid`). |
| `pairs` | Case variants as `[base, variant]` or `{base, variant, label?}`. Without this field they are found in the plan by content, never by name: the variant has the same prompt, judge, judge role, required checks and artifact as its base and repeats its follow-ups with more added (the closest base wins, a tie means none). `[]` turns variants off. |
| `baseline` | The reference arm for the ladder and difference views (default the trial's `baseline`). |
| `threshold` | The difference the decision rule asks for, on the difference view: a share such as `0.15` for +15 points, or `{value, label?}`; drawn only where the difference-from-baseline view appears (several arms and a `baseline`), and otherwise left out without a warning. |
| `include`, `exclude` | Default section ids: `include` keeps only the ones it names (`grid` appears only through `include`), `exclude` drops the ones it names. |
| `sections` | Extra sections, `{title, blocks, …, after?}`, each placed after the section whose id is `after` (a default id or an earlier extra's `id`), else at the end. |
| `append` | `{sectionId: [blocks]}` added to the end of a default section. Blocks appended to a section that is left out do not render; the check warns when `include`, `exclude` or an unnamed `grid` left it out, not when the section has nothing to show. |
| `footer` | Closing line; default, when the trial records `generated_at`, "Report data written DATE. Every view is drawn from the data embedded in this file, and each run names its native record." |

The meta lines hold the question (when a title is also given), "Ran" (the date range of the trial's `ran`, the first and last `result.json` times in UTC; the footer gives when the data were written) and the run directory, with a home-directory prefix shown as `~`. Write the `decision` after applying the plan's rule yourself; the composition carries the rule and the data, never a verdict of its own. [examples/fictional-narrative.json](examples/fictional-narrative.json) shows a complete decision. In JavaScript the result is an ordinary specification whose `sections` can be dropped, reordered or extended before rendering.

## Comparisons of any alternatives

A **comparison** is the general form of the data. Anything chosen between is an *alternative* (a prompt, a sandwich, an ad, a game rule, a research direction that holds approaches of its own), a *case* is any context it was tried in, and a *metric* is anything observed about it: nothing in it assumes agents, runs or pass/fail. `report.py --data comparison.json` or `--csv table.csv` composes a report from it ([composition](#comparison-composition)), the [views](#comparison-views) draw it inside a specification (its `comparison` field), and `report.py --check` checks it ([input checks](#input-checks)). [examples/comparisons/](examples/comparisons/) holds five fictional ones: a two-way lunch choice judged head to head with a decision matrix, nested research directions with two identical copies, ad totals by segment, game-design playtests with rankings and excerpts, and a commute table as CSV.

### Comparison data

| Field | Type | Meaning |
| --- | --- | --- |
| `alternatives` | `[{id, label?, description?, group?, attributes?, content?, note?}]`, required | What is compared; ids are unique. `group` is a path, outermost first (`["Ask people", "Interviews"]`; a string is one level), and a group is named by its full path, so two "Concept 1"s under different directions stay apart. `attributes` are recorded settings (string, number, boolean or null), shown as what differs. `content` is the full text compared, diffed against the baseline's. |
| `metrics` | `[{id, kind, label?, better?, unit?, levels?, primary?, description?, threshold?}]`, required | `kind` is one of the six [below](#metric-kinds). `better`: `higher`, `lower` or `none` (default: nothing is colored good or bad). `levels`: ordinal names, lowest first. `threshold`: a decision bar in the metric's units, a share in 0–1 for binary and count. Mark at most one `primary`: the views' default metric, listed first in the composition. |
| `cases` | `[{id, label?, description?, group?}]` | Contexts, with nested groups (segments, regions, rounds). A case named only by an observation is shown by its id, with a warning when the comparison declares any `cases`. |
| `observations` | `[{alternative, metric, value, case?, n?, unit?, valid?, invalid_reason?, note?, excerpt?, source?, id?}]` | One value each. `n`: the trials behind a count. `unit`: the repeat, rater or session. `excerpt`: a quotation or output behind the value. Only an http(s) `source` becomes a link. |
| `aggregates` | `[{alternative, metric, case?, k?, n?, mean?, sd?, median?, lo?, hi?, counts?, source?, note?}]` | Totals where no per-unit values exist: `k` of `n` (binary and count; wins of decisive judgments for preference), `mean` with `sd` and `n` (numeric and rank), `counts` per level (ordinal). An alternative's aggregates on a metric are read only when it has no observations on it. `lo` and `hi`, an interval the source reported, are drawn as given for binary, count, numeric and rank totals, and labelled so in the method note, when one aggregate stands alone; pooled totals recompute and grouped ones drop it. |
| `preferences` | `[{a, b, winner, case?, metric?, judge?, note?}]` | Head-to-head judgments. `winner` is `a`, `b`, `"tie"`, or `null` when none was reached (unreached, counted apart, never a loss; a winner naming neither is counted the same). `metric` names the criterion judged; a judgment naming none is the overall preference, and also counts toward the comparison's only preference metric, or its primary one. |
| `rankings` | `[{order, case?, metric?, judge?}]` | A full ordering, first place first. It gives each listed alternative a position on the `rank` metric it names (else the only or primary one), and every pair inside it counts as a judgment for the criterion `metric` names, or when it names none for the overall preference and the only or primary preference metric. |
| `baseline`, `identical` | id; `[[id, …]]` | The reference others are read against; groups of alternatives given identical material, whose gap is shown as chance alone. |
| `title`, `question`, `summary`, `decision_rule`, `sources` | text (`decision_rule` a single string); `[{label, href?, note?}]` | Headings, the rule fixed before results (quoted verbatim in the verdict) and where the data came from. |

#### Metric kinds

An observation is invalid, and counted by its reason, when `valid` is false, its value is empty (null, absent or `""`), or its value does not fit the kind (the reason says why: "not a number", "count has no trials (n)", "not one of the levels", …). Every interval is 95%, and the method note in `metric`, `difference` and `hierarchy` names its method; the bootstrap is seeded from the metric and alternative ids, so identical data give identical intervals.

| Kind | An observation's `value` | Summary of one alternative | Difference, first minus second |
| --- | --- | --- | --- |
| `binary` | `true` or `false` (or 1 and 0) | k of n valid, the rate with a Wilson score interval | Difference in rates, Newcombe's hybrid score interval (method 10) |
| `count` | Successes as a whole number, with `n` trials | k of the summed n, Wilson score interval | As binary |
| `numeric` | A number | Mean with a Student t interval, median, sample sd; every value shown (thinned evenly past 240 per alternative) | Difference in means, Welch interval (Welch–Satterthwaite degrees of freedom); difference in medians, percentile bootstrap of 2,000 seeded resamples per side |
| `ordinal` | A level name, or its position from 0 when `levels` is given; without `levels`, numbers are the levels in numeric order | Counts per level and the median level, never a mean of positions | P(a higher) + ½P(tie) − ½ (Vargha and Delaney's A less one half, half of Cliff's delta), percentile bootstrap |
| `rank` | A position, 1 first; or positions from `rankings` | Mean rank with a Student t interval, median, first-place share | Difference in mean rank: paired t within the rankings or `case` and `unit` pairs that placed both (two or more), else Welch |
| `preference` | None: read from `preferences` and `rankings` | Wins, losses and ties; win rate over decisive judgments, Wilson score interval | Net head-to-head share, (a's wins − b's wins) ÷ decisive judgments, interval 2p − 1 from a's Wilson interval |

Totals-only numeric and rank data take the t interval from the supplied `mean`, `sd` and `n`; several such aggregates pool exactly; with no `sd` or fewer than two values there is no interval, and a difference says why. Filters (`cases`, `caseGroups`, `groups`, `alternatives`) narrow what a summary reads, and an observation naming no case is left out when `cases` is set. A group pools every observation of its members, so members with more observations weigh more, and groups at one depth are compared as alternatives of their own; judgments between two members of one group are set aside. An alternative with nothing recorded appears with n = 0, never as zero.

#### CSV

`report.py --csv` reads a long table, one observation per row.

| Column | Meaning |
| --- | --- |
| `alternative`, `metric`, `value` | Required. Headers are case-insensitive and a UTF-8 BOM is accepted. |
| `case`, `unit`, `n`, `note`, `excerpt`, `invalid_reason` | The observation's fields. A new `case` is declared by its id. |
| `group` | The alternative's group path separated by `>`, outermost first; one path per alternative. |
| `valid` | true/false, yes/no, pass/fail or 1/0; empty is valid. |
| `source` | Default `FILE row N`: the table's file name and the row. |

A metric's kind comes from `--data` when it defines the metric; the two merge, `--data` supplying what a table cannot (labels, levels, directions, units, cases, the baseline, and every `ordinal`, `rank` or `preference` metric). Otherwise any `n` makes it a count, true/false, yes/no and pass/fail make it binary, and numbers make it numeric. An empty value or `valid` false is an invalid observation. Ambiguous or broken input is refused with an `error:` and a specific `hint:`: values that are only 0 and 1, numbers mixed with true/false words, text values with no levels given, a metric with no values to infer from, `n` on only some rows of a metric, an unknown (with a suggested spelling) or repeated column, a missing required column, a row with the wrong number of cells, an empty alternative or metric, an unreadable `valid` or `n`, one alternative in two groups, and a value its metric's kind cannot read (unless the row is invalid).

### Comparison views

Each view reads the specification's `comparison`, or its own `data` (a comparison; its alternatives take their arm identity), and takes the frame fields `title`, `description`, `note` and `id`. `metric`, `scorecard`, `difference` and `hierarchy` also share these fields; the other four take their own, listed with them.

| Shared field | Meaning |
| --- | --- |
| `metric` | The metric to draw; default the primary one, then the first. |
| `alternatives`, `cases` | Which alternatives (in this order) and cases to read. |
| `groups`, `caseGroups` | Group-path prefixes, outermost first, keeping the alternatives or cases inside them. |
| `baseline` | The reference; default the comparison's. One outside the alternatives shown is said and ignored. |
| `method` | `false` hides the method note: "How these values are computed" in `metric` and `hierarchy`, "How these differences are computed" in `difference`. |

Narrowing by `cases`, `groups` or `caseGroups` is named in an "Only …" line, and an unknown metric, alternative or case is listed in a problem box. When alternatives have data for different cases, an "Unequal cases" line names who lacks what, since a pooled gap can then come from the case mix; the views do not restrict to the shared cases themselves, so set `cases` for a like-with-like comparison. "Better" or "worse than baseline" appears only when the metric has a direction and the 95% interval for the difference excludes zero. Fewer than five observations mark the n as rough.

#### metric

One metric drawn by its kind: rates with intervals and k of n (binary, count); a dot per numeric value (thinned evenly past 240 per alternative) with the mean, its interval and the median; ordinal levels as one bar split around a centre line with the median level named; mean rank with circles for each position's share; win rates against a 50% line (preference).

| Field | Meaning |
| --- | --- |
| `by` | `alternative` (default); `case`, a panel per case on the pooled rows' scale, which says when no entry names a case and counts those that name none when only some do; `group`, rows nested under pooled groups. |
| `depth` | With `by: "group"`, the group levels to nest; default 1. |
| `sort` | `identity` (default) or `value`: largest headline first (smallest first for `better: "lower"`, and for ranks unless `better: "higher"`), missing last. |
| `threshold` | A number, `{value, label?}`, or `null` to hide the metric's own: a line in the metric's units, not drawn for ordinal. |
| `center` | `mean` (default) or `median` as a numeric headline. |

#### scorecard

Alternatives against metrics: headline value, interval and count in each cell, a level bar for ordinal cells, missing cells said, the baseline marked, a tint with ▲ or ▼ only under the rule above, and group headers spanning their members. It scrolls sideways in its own frame.

| Field | Meaning |
| --- | --- |
| `metrics` | Metric ids in order; default every metric, the primary first. |
| `orient` | `columns` (alternatives across; the default up to 8 alternatives) or `rows`. |
| `center` | `mean` (default) or `median`. |

#### difference

Each alternative minus the baseline (or the pairs named), per metric, with a zero line, a plain reading of whether the interval excludes zero, and the gap between identical alternatives as a hatched band and its own "Chance alone" group.

| Field | Meaning |
| --- | --- |
| `metrics` | Metric ids, a panel each; default the single `metric`. |
| `pairs` | `baseline` (default with a baseline); `all` (every pair, later minus earlier; the default without one); or `[[a, b], …]`, a minus b. |
| `threshold` | A difference worth acting on, in difference units (0.05 is 5 points for rates); drawn only when one metric is shown. |
| `identical` | Groups of identical alternatives; default the comparison's; `false` hides them. |
| `sort` | `identity` (default) or `difference`, largest first. |
| `center` | `median` compares the medians of numeric metrics (a bootstrap interval); default `mean`. |

#### hierarchy

Nested groups as a tree: pooled group rows, members read against their group, and "Between" rows wherever a level holds two or more groups (one group minus another, among the top-level groups and among the groups inside each), all on one scale of their own, centred on zero.

| Field | Meaning |
| --- | --- |
| `depth` | Group levels to show; deeper groups fold into their ancestor; default all. |
| `between` | `false` hides the "Between" rows. |
| `center` | `mean` (default) or `median`. |

#### alternatives

What was compared: label, description and note per alternative; groups as nested lists; attributes shared by all on one line and differing ones in a table (a value over 320 characters or three lines folds behind "Show all"); lettered texts (equal `content` shares a letter) with line and word diffs against the baseline's text, else the first, the full text one disclosure away; "identical material" or "listed as identical but differs in …" marks; and a sentence on how they differ.

| Field | Meaning |
| --- | --- |
| `alternatives` | A subset of the comparison's. |
| `baseline` | The alternative whose text is the diff reference, marked "baseline"; default the comparison's. |
| `hide` | Attribute names to leave out. |
| `identical` | Groups of alternatives meant to be identical, in place of the comparison's. |

#### preferences

Head-to-head judgments and rankings: a census (decisive, tied, undecided and unreadable judgments, and the judges by name), a win matrix when two or more alternatives were judged (each cell the row's wins–losses against the column, ties beside, shaded by the row's share of decisive judgments), win rates over decisive judgments with Wilson intervals, rankings as first-place share, mean rank and the spread of positions, and by-case and by-criterion win-rate tables when several cases or criteria were judged. Undecided and unreadable judgments are counted and left out of the numbers. A ranking that lists fewer than two alternatives, repeats one or names one the comparison lacks is left out of the rankings table alone: its pairs still count in the win matrix and win rates, and its places in rank summaries.

| Field | Meaning |
| --- | --- |
| `metric` | The criterion (a preference metric's id). Omitted: the overall judgments, or the primary or first criterion when only criteria were judged, which a note says. |
| `alternatives`, `cases`, `groups` | Subsets; only judgments between the remaining alternatives count. |

#### decision-matrix

Criteria down, alternatives across: each cell's rating, text and collapsed evidence, "not assessed" where there is none, and a "best" mark on the top rating of a criterion whose ratings differ (the lowest for `better: "lower"`).

| Field | Meaning |
| --- | --- |
| `criteria` | Required. `[{id, label?, weight?, better?, description?, note?, metric?, scores?}]`. `weight` is a number of 0 or more. `better`: `higher` (default; for a measured criterion, its metric's `better`, else `lower` for a rank metric, else `none`), `lower`, or `none` (context only, not in a total). `note` is another word for `description`. `scores` is `{alternative: rating}` (a number, level or text; a boolean reads yes or no; null no rating), a shorter way to write cells. `metric` names a comparison metric: a criterion with it and no cells shows each alternative's measured value (rate, mean, mean rank, win rate or commonest level), marked "measured" and never scaled into a total. The composition derives a missing `id` from `metric`, then `label`, then the position. |
| `cells` | `[{criterion, alternative, rating?, text?, evidence?}]`. `rating` is a number or a level name from `scale.levels`; `evidence` is text or a list, shown collapsed. A cell naming a criterion or alternative the matrix lacks is counted, not shown; a repeat shows the first. |
| `scale` | `{min?, max?, levels?, labels?, note?}`. `levels` name the ratings lowest first from `min` (default 1); `max` defaults to the last level; `labels` are words for ratings as written (`{"1": "poor"}`); `note` closes the block. |
| `alternatives` | Ids or `{id, label}`; default the comparison's, then those the cells name. |

A weighted total appears only when the author gives weights. It sums weight × rating over the weighted criteria, a `lower` rating entering as min + max − rating (which needs `min` and `max`); a criterion with no number for an alternative is skipped, and that total is marked incomplete and not compared with complete ones. The arithmetic is shown per alternative, and a note names the criteria left out (no weight, `none`, measured, or a weight that is not a number of 0 or more).

#### observations

Every observation and every supplied total in one table (cards on a phone): number, alternative, case, metric, value read by its kind, validity with its reason, unit, note and source; excerpts open in place. The opening line counts valid and invalid observations and gives the commonest reasons; totals show k of n, mean and sd, median, n, the reported interval or counts, marked "aggregate". In the browser it filters and sorts ([Browser behavior](#browser-behavior)).

| Field | Meaning |
| --- | --- |
| `alternatives`, `cases`, `groups` | Subsets; the page's filters narrow further. |
| `metrics`, `metric` | Metric ids to keep; `metric` is shorthand for one. |

### Comparison composition

`comparisonReport(comparison, narrative?)`, which `report.py --data` and `--csv` run, builds a specification. Each section appears only when the data holds its content, in this order (`COMPARISON_SECTION_IDS`).

| Id | Blocks | Present |
| --- | --- | --- |
| `verdict` | `verdict` from the narrative's `decision` and the data's `decision_rule`, then `figures` (alternatives, metrics, cases, valid and invalid observations, judgments) | Always; without a decision the stamp reads "No decision recorded". An alert links to the observations when all are invalid or a fifth or more are. |
| `compared` | `alternatives` | Any alternative. |
| `results` | `scorecard` with several metrics, then a `metric` per metric, the primary first | Any metric. |
| `differences` | `difference` over every metric | A metric and two or more alternatives, with a baseline, identical groups, or exactly two alternatives (first minus second). |
| `groups` | `hierarchy` on the primary metric | Any alternative names a group. |
| `cases` | `metric` with `by: "case"` per metric | More than one case and at least one metric. |
| `judgments` | `preferences` per preference metric with judgments, plus an overall one for judgments that name no metric when no preference metric is the only or primary one (the only block when no preference metric has judgments) | Any judgment or ranking. |
| `decision` | `decision-matrix` from the narrative's `criteria`, `cells` and `scale` | The narrative gives criteria. |
| `observations` | `observations`; titled "Every supplied total" when there are only totals | Any observation or supplied total. |
| `sources` | `list` | The data lists sources. |

The narrative is JSON beside the data; `report.py --skeleton --data …` starts one with every id spelled as recorded.

| Narrative field | Meaning |
| --- | --- |
| `title`, `question`, `summary`, `kicker`, `footer` | The page's words. Title: the narrative's `title`, its `question`, the data's `title` or `question`, else "Comparison". Summary: the narrative's, else the data's, else a generated sentence on the data's shape. Kicker: default "Comparison". |
| `decision` | The [verdict block's](#verdict) fields as in the [trial composition](#trial-composition) (`verdict`, `label`, `headline` (required), `detail`, `checks`, `conditions`, `limits`, `changes`, `alert`; `mentions` and `pairs` read trial data). Its `rule` is ignored: the verdict quotes the data's `decision_rule`. |
| `alternatives` | Labels, notes and identity order, as `[{id, label?, note?}]` or `{id: {label?, note?}}`; they win over the data's. |
| `baseline`, `identical` | Used in place of the data's when valid. |
| `criteria`, `cells`, `scale` | The decision matrix, with the fields above. |
| `include`, `exclude`, `sections`, `append` | As in the trial composition: choose sections by id, add `{title, blocks, id?, label?, lead?, after?}` sections (placed after `after`, else last) and append blocks to a section. Other names select a section too: `setup` and `alternatives` (compared), `metrics` (results), `hierarchy` (groups), `preferences` and `pairwise` (judgments), `matrix` (decision), `ledger` and `runs` (observations). |

### From a trial

`fromTrial(trial)` turns `trial.py report` data into a comparison. Arms become alternatives with their recorded settings as `attributes` and instructions as `content`; scenarios become cases; each run observes a primary `passed` yes/no metric (an invalid run stays invalid) with the judge's reason as `note`, the final-output excerpt as `excerpt` and the repeat as `unit`; usage and timing become numeric metrics where lower is better; checks whose values are all booleans or all numbers become `check:<name>` metrics (higher is better only for a check some case requires); the judge's verdict becomes a yes/no metric; pairwise summaries become head-to-head judgments (order-inconsistent and invalid pairs unreached); the plan's baseline and decision rule carry over. `report.py --trial trial.json --general [--narrative narrative.json]` draws a trial through these views, and the narrative is then a comparison narrative, which the page checks against the derived comparison (`--check` cannot, having no Python conversion). The trial composition is the default for trial data: it adds the run drawer, failure reasons, the tapestry and the cost views.

## Arm identity and run marks

Each arm (in a comparison, each alternative) gets one color (eight hues in an Okabe–Ito-based order, tuned per theme) and one shape (circle, square, diamond, triangle, hexagon, downward triangle, star, cross), the same in every view; the first 64 arms get distinct pairs. The order is the specification's `arms` (a narrative's `arms`, or its `alternatives` in a comparison narrative), then the trial's arms (in plan order in the trial composition, else as its runs first name them), then the comparison's alternatives as listed. An arm tag shows the shape, the label and, where a label replaces the id, the raw id in code; compact views drop the id, while the ladder, pairwise headings, setup, plan and drawer keep it. Pointing at an arm tag highlights that arm within its block.

Run outcomes share one mark language: passed is a filled circle, failed a hollow ring, invalid a grey square struck through. Cost dots take the arm's color with the same fill or ring. Shape and fill carry the state and color only reinforces it; in forced-colors mode the marks keep distinct fills and borders.

### The run drawer

A run mark (in `cases`, `failures`, `tapestry`, `cost` or `invalid`) or a ledger row opens a dialog headed by the run's number, job id, case, arm, repeat and outcome. A failed run opens with why it failed, and an invalid run with why it has no result and what would give it one. Then its status; executor, setup, check and judge times (when recorded; a minute or more reads "1 min 26 s"); commands; "unconfined" when the run ran outside the sandbox and "not produced" when its artifact is missing; the judge's verdict, reason and question; every check value (required ones marked, those that did not hold first; other checks next; recorded text and numbers folded when there are more than four); the final output (the first 2,000 characters, said so at the limit); usage fields as the executor reported them; and its native record, `RUN_DIR/runs/JOB/` (a home-directory prefix read as `~`), with a button that copies the full path. Buttons and the arrow keys move to the previous or next run in the ledger's current filter order, and "Copy link" copies a link to the run.

### Browser behavior

Every view is drawn complete by the renderers; the browser layer only adds ways to move through the data.

| Feature | Behavior |
| --- | --- |
| Top bar | The section index marks the section in view and moves to its own scrollable row in windows 860 pixels wide or less; a theme button cycles Auto, Light and Dark. A chosen theme is kept in the browser's local storage under `av-theme` and applied before first paint; Auto follows the system. A skip link leads to the first section, and another to the run ledger when the report has one. |
| Deep links | `#cases` (any section id) scrolls to and focuses that section; each section's "Link" control copies its link. `#run-12` opens run 12 (its number in the ledger), and `#run-JOB` opens the run whose job id is `JOB`. `#runs?outcome=fail&arm=ID&case=ID&q=TEXT` restores the ledger's filters (`runs` is the ledger section's id in the composition). Opening a run puts `#run-N` in the address without adding history, and closing the drawer restores the address before it. |
| Run marks | Hovering or focusing a mark shows its accessible name at once as a tooltip (also any element with `data-av-tip`). Each tapestry, failures block, cost panel, invalid group or case dossier is one tab stop: arrows move between marks (up and down by row), Home and End go to the ends, Enter or Space opens the run. |
| Ledger | Outcome buttons, arm and case filters, a text search over each row, the "N of M runs" count, "Clear filters", and sorting by column header. At 640 pixels or less rows become cards, sorting moves to a select, and only the first 20 matching runs show until "Show all N runs". Rows are one tab stop: up and down arrows, Home and End move, Enter or Space opens. `/` jumps to the search from anywhere outside a field. |
| Observations table | The `observations` block's table has the ledger's filters, sorting, search, count, "Clear filters" and phone cards, with validity buttons (All, Valid, Invalid, and Aggregates when the data holds totals) and alternative, case and metric selects wherever there is more than one to choose, the first 20 matching rows on a phone until "Show all N observations", and no run drawer, row keyboard model or export. Its filters live in the address as `#observations?outcome=invalid&arm=ID&case=ID&metric=ID&q=TEXT` (`outcome` is `valid`, `invalid` or `aggregate`; `observations` is the section's id in the composition). |
| Export | The ledger offers "Download CSV" and "Copy CSV" for the runs in view, in their order, and "Download all trial data (JSON)"; the footer repeats the JSON download for any report that carries a trial. Files are named from the trial's name (`NAME-runs.csv`, `NAME-trial.json`). The CSV has one row per run (number, job, case and label, arm and label, repeat, outcome, cause, invalid reason, judge verdict and reason, seconds, output and input tokens as the executor reported them, cost, commands, record path, in full) and a `check.NAME` column per recorded check, in UTF-8 (a byte-order mark in the downloaded file) with CRLF lines; text that a spreadsheet would run as a formula gets a leading apostrophe. A viewer that blocks downloads is told to use "Copy CSV" or the embedded JSON. |
| Announcements | One polite live region on the page and one inside the drawer say what changed: filtered counts, the run reached by stepping, and whether a copy reached the clipboard. |
| Print | Paper gets the light theme with every collapsed disclosure opened, restored afterwards. |

## New block types

`AgenticVisuals.registerBlock(type, render)` adds a block type or replaces one, returning a function that restores the previous renderer; `blockTypes()` lists the registered types. A `type` is lowercase letters, digits and hyphens, starting with a letter. `render(block, ctx)` receives the block object and the render context and returns an HTML string. Escape everything it takes from data; `AgenticVisuals.escapeText` escapes a string or finite number and throws on anything else.

| Context | Use |
| --- | --- |
| `ctx.arms` | `tag(id, {id: false}?)`, `glyph(id)`, `label(id)`, `note(id)`, `color(id)` (a CSS color), `shape(id)`, `index(id)`, `ids()` |
| `ctx.trial`, `ctx.runs`, `ctx.runIndex` | The trial and its runs; an element with `data-run="${ctx.runIndex.get(run)}"` opens that run's drawer when selected |
| `ctx.comparison` | The specification's comparison, or undefined |
| `ctx.caseLabels` | Case labels |
| `ctx.uid(base)` | A unique element id |

`AgenticVisuals.blocks.frame(kind, block, bodyHtml)` wraps a body in the shared block frame (title, description, note, id), and `renderBlock(block, ctx)` renders a built-in block inside a new one:

```js
AgenticVisuals.registerBlock("verbatim", (block, ctx) =>
  AgenticVisuals.blocks.frame("verbatim", block,
    `<ul>${block.items.map(i => `<li>${ctx.arms.tag(i.arm)} ${AgenticVisuals.escapeText(i.text)}</li>`).join("")}</ul>`));
```

Register before the report renders: in an assembled file, a script placed after the library runs before the automatic render ([PACKAGING.md](PACKAGING.md#custom-compositions) gives the command). A registered type has no entry in the input checks: the page accepts its fields as written, but `report.py --check` knows only the built-in types and reports the type as unknown (an error, exit 1). Style a new block with an extra stylesheet built on the theme's custom properties (`--av-ink`, `--av-line`, `--av-pass`, `--av-fail`, `--av-arm-0` to `--av-arm-7` and the rest in [src/theme.ts](src/theme.ts)) so it follows both themes.

## Faithfulness guarantees

- **Invalid is not failure.** Every rate, interval and difference counts valid runs only; invalid runs are counted beside them (ladder chip, tapestry and dossier counts, cost rows, failures opening line, invalid section, ledger filter) and stay visible as marks in the tapestry, dossiers, invalid section and ledger.
- **Uncertainty is drawn.** Rates from counts carry 95% Wilson intervals, differences between rates 95% Newcombe intervals (none when counts are missing, a side has no valid runs, or the sides share runs); fewer than five valid runs is flagged, identical arms show what chance alone produces, and a pooled difference over an "uneven case mix" says so.
- **Identity order is not rank.** Arms keep their identity order in every view unless you set a sort (a ladder's `sort: "rate"`, a contrast's or `difference` view's `sort: "difference"`, a `metric` view's `sort: "value"`) or the view orders by result: `preferences` in its win-rate and ranking tables, `invalid` in its arm counts.
- **Missing stays missing.** "missing", "not established", "not run", "not recorded", "no valid runs", "no value", "not in this report" and "N missing" replace absent values; nothing becomes a zero or a blank.
- **Order disagreement is reported.** Order-inconsistent and invalid pairs are their own segments, and win rates use decisive pairs only.
- **Cost is per run.** Every valid run is a dot (on a log axis, runs at zero are counted beside it), medians and quartiles describe valid runs, log scales and axes that do not start at zero are labelled, input tokens that add back cache reads say so, and differences are the trial's per-case medians, never one pooled number.
- **Checks keep their roles.** Required checks, the judge and directionless measures are separate groups, and a case's pass criteria are stated as `trial.py` applies them.
- **One account of a failure.** The ledger, drawer, marks, dossiers and failures view read one derivation, `failureCause`, so they cannot disagree; a failed run whose data name no cause says so rather than guessing.
- **Comparisons keep their kinds and say their methods.** Every comparison interval is 95%, and the method note in `metric`, `difference` and `hierarchy` names its method, labelling an interval the source reported "as reported by the source"; ordinal levels are counted, never averaged; bootstraps are seeded, so the same data give the same interval; a metric with no `better` is never colored good or bad, and "better" or "worse than baseline" needs an interval that excludes zero.
- **Uneven coverage is said.** Alternatives with data for different cases get an "Unequal cases" note, data naming no case is reported as such rather than drawn as empty panels, an unreached judgment is counted apart from wins and losses, and a missing rating or value reads "not assessed", "no value" or missing, never zero.
- **Settings and texts are as recorded.** `setup` shows the plan's recorded settings and texts, diffs the texts it has, marks a text it lacks or had to cut, and says when arms listed as identical are not.
- **The decision is the author's.** The verdict shows only what the narrative or specification states, with the plan's (or a comparison's `decision_rule`) rule verbatim, and a decision matrix totals only the author's weights over their own ratings, showing the arithmetic; without a decision it says none was recorded and counts only what the rule names. A `threshold` is drawn and described, never decided.
- **Evidence text stays text.** All supplied text is escaped; prose fields recognize only inline code and strong.
- **Input problems are listed.** A misspelled field, arm or block type appears in the page's input check, and an unknown block renders a notice instead of vanishing.
- **Every run reaches its record.** The drawer names each run's native record directory, and the CSV carries its path.

## What is not offered

- Verdicts, invented scores or weights, composite rankings, significance tests or p-values: the statistics are those named here (for trials, pass rates with Wilson intervals, differences between rates with Newcombe intervals, medians and quartiles, plus the trial's own percent differences; for comparisons, the [methods](#metric-kinds) each view names), and a weighted total appears only from the author's own weights with its arithmetic shown.
- Raw HTML, Markdown blocks or scripts inside a specification: a new kind of view is a registered block.
- Totals that hide per-run or per-case values.
- Adjustments the data's design might call for: comparison intervals treat observations as independent (apart from paired rank differences) and are not adjusted for several comparisons, and pooled values are not restricted to the shared cases, which the views flag instead.
- Network access, remote fonts, analytics, annotations, accounts or saved reader state beyond the theme choice: filters and links live in the address, and exports are files the reader saves.
- Anything `trial.py report` does not carry: transcripts and events stay in the native record, final outputs are cut at 2,000 characters, texts and descriptions at 24,000, and fixtures, setup and check code are not in the report.
- Rendering without JavaScript: the page draws itself from its embedded data, and without scripts the reader sees only a notice that points to the JSON blocks in the file's source.
