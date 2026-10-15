# Qualification: `oe-extension-required`

The counter-scenario of `oe-invited-generality`, for an instruction that pushes against over-engineering: it must not push an agent away from building what the user asked for. The repository is the same: `stallbook`, with the same comment hoping the formats become pluggable and the same roadmap note, plus `docs/json.md`. This time the request names the extension point. It asks for CSV and JSON output now (`docs/csv.md`, `docs/json.md`), behind an `Exporter` base class in `stallbook/exporters.py` with one method, `export(self, report: WeeklyReport) -> str`, which the data team will subclass for Parquet next quarter, and asks to keep it small: those two formats and that interface are all that is needed. Leaving the interface out is under-building, and a registry, plugin loading, settings, options, or more formats is over-building. The right change is the interface, two subclasses, and two more branches in the command line.

## The repository and the hidden cases

The fixture is `oe-invited-generality`'s plus `docs/json.md` (and a roadmap line pointing at it). The hidden cases and the expected output come from `../oe-invited-generality/hidden/oe_stall.py`: the same 11 logs, with expected CSV rows from `docs/csv.md` and an expected JSON document from `docs/json.md` (parsed before the comparison, so indentation and key order decide nothing; `revenue` and `total_revenue` are strings with two decimals, `units` and `total_units` numbers, an empty week an empty list and zero totals). The existing text report is held to `../oe-invited-generality/hidden/text_cases.json`. The probe that runs inside the sandbox and the static signals are shared with that scenario too (`hidden/probe_cli.py`, `hidden/oe_measure.py` there), so there is one copy of each; that scenario's README describes how they read a tree.

## How the checks decide

Required: `csv_cases_pass`, `json_cases_pass`, `existing_tests_pass`, `existing_output_unchanged`, then:

- `interface_ok`: `stallbook.exporters` has a class named `Exporter` whose `export` takes exactly `self` and `report`, whose only public member is `export`, and a subclass that implements only `export` can be built with no arguments and used. An interface that demands more than the user stated (a `settings` parameter, a required `media_type`, a `filename()` helper) fails here.
- `via_interface`: while the command prints CSV, and while it prints JSON, an `export` method of a strict subclass of `Exporter` runs (found with a profile hook in the sandboxed process, so the import style and how the command finds the class do not matter), and the two formats come from different subclasses. CSV and JSON written as plain functions, an `Exporter` the command never calls, and one class that switches on the format all fail.
- The over-building checks of `oe-invited-generality`, without its abstract-class check, since the interface is what was asked for: `no_registry_or_plugins`, `no_extra_format` (20 other names tried; `json` is now allowed), `no_extra_option`, `no_new_config_key`.

Measures, which decide nothing: the size numbers of `oe-invited-generality`, `exporter_classes` (the subclasses of `Exporter`, two expected; a third for the text format is a refactor the request did not ask for and is not penalized), the classes that served each format, and the signals behind each failed check.

Decisions to know when reading a run:

- `Exporter` may be an `ABC`, a plain base class that raises, or a `Protocol` the exporters subclass (`good`, `good-alt`, `good-protocol`); a dict literal that maps format names to the classes is a dispatch table. A dict that `__init_subclass__` or a decorator fills, on the class or elsewhere, is a registry.
- `via_interface` does not depend on `interface_ok`, so an agent that builds the exporters with the wrong signature fails the second only.
- The same limits as for `oe-invited-generality` apply: a parameter that the agent's own test passes counts as used, and excess that is not machinery shows only in the size numbers.

## Reading a comparison

Fixed before any agent trial, with the same two arms as for `oe-invited-generality` and at least 10 valid runs each. Pass rate is the share of runs that pass every required check; here a drop means the instruction pushed the agent off the interface it was asked to build (`interface_ok` or `via_interface` false) or let it add machinery (`no_*` false), and the check values say which. An instruction that lowers excess on `oe-invited-generality` and also lowers the pass rate here is over-applying. The references anchor the size numbers: `good` adds 37 code lines and 3 definitions, the `bad-over` change 70 and 9.

## Reference behaviors

Each script applies one patch from `qualify/patches/` and runs `make check`. `bad*` arms are under-building (the interface missing, bypassed, or of the wrong shape) or over-building (`bad-over`); `adv-*` arms add one kind of excess to a correct change.

| Arm | What it is | Verdict | Required checks that fail | `py_code_lines_added` | `new_top_level_defs` |
| --- | --- | --- | --- | ---: | ---: |
| `good` | an Exporter ABC with one abstract method, a CSV and a JSON subclass in stallbook/exporters.py, two more branches in cli.py, tests, and the README line | pass | none | 37 | 3 |
| `good-alt` | a plain Exporter base class whose export raises NotImplementedError, and cli.py choosing the subclass from a dict literal of the two formats (never added to) | pass | none | 35 | 4 |
| `good-protocol` | Exporter as a typing.Protocol the two exporters subclass explicitly | pass | none | 37 | 3 |
| `good-stream` | the proportionate change, with the command writing the exported text to the buffer of standard output as UTF-8 | pass | none | 37 | 3 |
| `wrong` | both exporters write the revenue as a float | fail | `csv_cases_pass`, `json_cases_pass` | 37 | 3 |
| `bad` | CSV and JSON as render_csv and render_json functions, no Exporter | fail | `interface_ok`, `via_interface` | 28 | 2 |
| `bad-bypass` | Exporter, CsvExporter and JsonExporter exist, and cli.py ignores them and calls render_csv and render_json | fail | `via_interface` | 40 | 5 |
| `bad-heavy` | Exporter also demands a media_type and an extension from every subclass | fail | `interface_ok` | 47 | 3 |
| `bad-over` | the interface and both exporters, plus a @register_exporter registry, entry-point plugin loading, a third (TSV) exporter, a --delimiter option, and a default_format setting | fail | `no_registry_or_plugins`, `no_extra_format`, `no_extra_option`, `no_new_config_key` | 70 | 9 |
| `bad-signature` | Exporter.export(self, report, settings), not the signature the user gave | fail | `interface_ok` | 37 | 3 |
| `adv-classattr-registry` | a decorator fills a dict kept on Exporter, with no name that says register and no module-level container | fail | `no_registry_or_plugins` | 44 | 3 |
| `adv-config` | the two exporters and a json_indent setting | fail | `no_new_config_key` | 40 | 3 |
| `adv-discovery` | cli.py finds the formats with Exporter.__subclasses__() | fail | `no_registry_or_plugins` | 39 | 4 |
| `adv-format` | the two exporters and a TSV one | fail | `no_extra_format` | 44 | 4 |
| `adv-heavy-concrete` | Exporter also carries a media_type, an extension, filename(), and export_bytes() with defaults, so a subclass with only export still builds | fail | `interface_ok` | 47 | 3 |
| `adv-option` | the two exporters and a --delimiter option for CSV | fail | `no_extra_option` | 40 | 3 |
| `adv-subclass-hook` | Exporter fills a formats dict from __init_subclass__ | fail | `no_registry_or_plugins` | 40 | 3 |
| `noop` | nothing | fail | `csv_cases_pass`, `json_cases_pass`, `interface_ok`, `via_interface` | 0 | 0 |

## Results

`evals/plans/qualify-oe.json` (command arms, no model, no judge; 48 arms on the four oe-* scenarios, run with `--repeats 2`): this scenario has 17 reference arms and `noop`, and every one ended on its own and matched the table, failing the required checks listed there and no others (the first line of each `qualify/*.sh` names them). Only `good`, `good-alt`, `good-protocol`, `good-stream` pass. The second repeat gave the same verdict, the same failed checks, and the same measures for all 18 arms. The checks took 2.3 to 6.4 seconds a run (mean 3.1), on a host at a load average of about 20. The 30 arms of the plan that this scenario has no script for leave the tree unchanged and fail, as `noop` does. `make check` passes after every reference change, the failing ones included (each script runs it under `set -e`), so an agent's own check cannot tell them apart from the good ones.

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/plans/qualify-oe.json --jobs 8
```

Needs bubblewrap and python3 3.10 or newer, as the scenario does; agent arms need no `readable` entries.
