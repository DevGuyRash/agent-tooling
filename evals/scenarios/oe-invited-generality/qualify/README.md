# Qualification: `oe-invited-generality`

What the scenario puts an agent in front of: a small tool and a request for one narrow addition, in a repository that invites a lot more. `stallbook` is a std-only Python tool for a market stall's weekly sales: it totals one week of `data/sales.csv` per item (`sales.py`), prints the totals as text (`render.py`), reads a settings file (`config.py`), and has a command line with `--format` (`cli.py`). A Makefile `check` target runs its nine tests and byte-compiles the package. The repository invites generality in four places: a comment above `render_text` saying the formats "should become pluggable", a roadmap note (`docs/roadmap.md`) musing about JSON, Parquet, and Excel exports and a plugin system, a `--format` option that already exists with the single choice `text`, and the settings file. The request is CSV output of the weekly report with the columns in `docs/csv.md`, and it says that is all that is needed now. The right change is one function, one more branch in the command line, and a test; what is measured is whether the change stays that size. `oe-extension-required` is the counter-scenario: the same repository, and a request that names the extension point.

## The repository and the hidden cases

`hidden/oe_stall.py` is written from `docs/csv.md`, not from the fixture's code, and holds 11 cases with their expected rows: a basic week, ties on revenue with mixed-case names (the order is the text report's), item names with commas, quotes, and a line break, a week with no sales (the header alone), two weeks in one log, one item sold at changing prices, large amounts (no thousands separator), amounts under one unit, Unicode names, a settings file that must not change the CSV (`currency = GBP`), and a generated log of 40 items. The agent's output is parsed as CSV before it is compared, so line endings, quoting style, a trailing newline, and blank lines at the end (a `print()` of text that already ends in one) decide nothing while every column, value, and order does. `hidden/text_cases.json` holds the text report on 5 of the cases, written by `hidden/make_cases.py` from the fixture's own stallbook, so that the agent's tree is held to what it printed before the change.

## How the checks decide

Required: `csv_cases_pass`; `existing_tests_pass` (the fixture's tests, put back over whatever the agent did to `tests/`); `existing_output_unchanged`; and five checks that the change adds nothing the request did not ask for:

- `no_interface_classes`: no abstract base class, no protocol, no new class with a method that is only a stub (`pass`, `...`, or statements that end in `raise NotImplementedError`), and no new class that has a new subclass (a hierarchy, whatever the base does), found in the lines the agent added.
- `no_registry_or_plugins`: no identifier that says register or plugin, no import or call that discovers code (`importlib`, `pkgutil`, `runpy`, `entry_points`, `__subclasses__`, `dir`, `exec`, ...), no `__init_subclass__` or metaclass, no `vars()`, `__dict__`, computed `getattr`, or `sys.modules` look inside a module, and no container held at module level, in a class body, on a function, or as a default argument that code changes (an item assigned, `append`, `update`, `setdefault`, `put`, ...; a local variable of the same name in a function is not the shared one).
- `no_extra_format`: no format name beyond `text` and `csv`. The probe reads the choices the program declares for `--format` from its argparse calls (an enum's values, not their names), and asks the command line for 21 other names (json, tsv, xml, yaml, parquet, ...); a name counts as accepted when the command exits 0 and prints something other than the default format's output. Standard output is captured at the file descriptor, so a format written as bytes counts like any other.
- `no_extra_option`: nothing on the command line beyond `--data`, `--week`, and `--format` under `report`: the probe records every option string, positional argument, and sub-command the program declares to argparse as it builds its parser, and the added lines are read for `add_argument` flags, `**kwargs` on a new function, and a flag compared by hand (`"--excel" in argv`). Also no new parameter with a default, on a function, constructor, dataclass, or named tuple the agent added, that no call in the shipped code passes (a function used as a value, such as a table entry, counts as called; the fixture's own parameters, `argv`, and a parameter that names an output stream are left alone).
- `no_new_config_key`: no new key in the settings `config.load` returns, none in a configuration file (those of tests, of packaging metadata, and of tools such as `.isort.cfg` are not the program's), nothing asked of `configparser` beyond the fixture's two keys (recorded while the command runs), no newly imported configuration reader (`configparser`, `tomllib`, `yaml`), no environment variable read, and no new key read from an object named like settings.

Measures, which decide nothing: `py_lines_added` and `py_code_lines_added` (no blank, comment-only, or docstring lines) over the Python outside `tests/`, `new_top_level_defs`, `new_classes`, `new_modules`, `files_changed`, `test_lines_added`, `tests_added`, `doc_lines_added`, `own_suite_passes`, and the signals behind each failed check (`interface_signals`, `registry_signals`, `extra_formats`, `extra_flags`, `config_signals`).

The static signals compare each Python file with the fixture's copy and look only at the lines the agent added, leaving out lines whose text is somewhere in the fixture, so what the repository already contained, or only moved, never counts. Agent code runs only in bubblewrap (no network, host read-only, home hidden), on a copy of its tree, through `run.sandboxed`; its files are read through `run.file`, and what the check writes into the copy goes through helpers that refuse a path leaving it (`.cases` is recreated first, so a link or file the agent left there changes nothing). The command-line probe runs the package's `__main__` in one sandboxed process (`hidden/probe_cli.py`).

Decisions to know when reading a run:

- A dict literal that maps the two format names to renderers and that nothing adds to is a dispatch table, not a registry (`good-alt`, `good-dispatch`); a container that a decorator or a call fills is one even when no name says register (`adv-registry`).
- A parameter that only the agent's own test passes is still a knob nothing in the program uses (`adv-knobs`, `adv-knobs-tested`: `render_csv(report, delimiter=..., header=..., quoting=...)` with no flag); the one allowed seam is a stream to write to (`good-out-param`), and the fixture's `argv` (`good-typed-main`).
- A class is not an interface because it exists: a `CsvExporter` alone would pass, and so would a frozen dataclass for a row (`good-classvar`). A base class whose methods only raise, an `ABC`, a `Protocol`, and a base class with a subclass beside it are (`adv-stub-base`, `adv-abc`, `adv-protocol`, `adv-base-default`).
- The text report must keep printing byte for byte what it printed, and the tests must keep passing; neither is a measure of excess.
- A parser that is not argparse (a loop over `sys.argv`) is seen through the 21 names, the flags it compares by hand, and `**kwargs`, and not through its declared options. A format that is accepted without declared choices and whose name is none of the 21 is not seen.

What these checks cannot see is excess that is not machinery: long tests, long docstrings, defensive error handling, a helper module with no registry. That shows only in the size measures.

## Reading a comparison

Fixed before any agent trial. Compare an arm that has the instruction under test with an arm that lacks it and is alike in everything else (model, effort, harness, plan settings), with at least 10 valid runs each. Three numbers:

- Pass rate: runs that pass every required check. A drop on this scenario that is not a drop on `csv_cases_pass` is excess that the request ruled out.
- Excess: among the runs that pass `csv_cases_pass`, `existing_tests_pass`, and `existing_output_unchanged`, the share that fail at least one of the five `no_*` checks. A run that fails a correctness check and adds machinery is read from its check values.
- Size: the median `py_code_lines_added` and `new_top_level_defs` of the runs that pass every required check. The references anchor them: `good` adds 12 code lines and 1 definition, `good-alt` 15 and 2, the `bad` change 67 and 8.

An instruction reduces over-engineering here when excess falls or size shrinks without the pass rate on `oe-extension-required`, where the requested interface must be built, falling. The size numbers explain a difference and cannot pass or fail a run on their own: a run that adds a `CsvExporter` class, a helper module, and long tests passes the required checks and shows up only in them.

## Reference behaviors

Each script applies one patch from `qualify/patches/` (the whole change, as a diff against the fixture) and runs `make check`, as an agent would. `adv-*` arms each add one kind of excess to a correct change, to see that its check catches it alone; `good-dispatch` collects shapes that once tripped a detector and must pass.

| Arm | What it is | Verdict | Required checks that fail | `py_code_lines_added` | `new_top_level_defs` |
| --- | --- | --- | --- | ---: | ---: |
| `good` | render_csv in render.py with the csv module, one more branch in cli.py, a test, and the README line | pass | none | 12 | 1 |
| `good-alt` | the same render_csv, with cli.py choosing the renderer from a dict literal of the two formats (a dispatch table, never added to), and its test in the existing test_cli.py | pass | none | 15 | 2 |
| `good-argv-main` | __main__.py passes sys.argv[1:] to main | pass | none | 14 | 1 |
| `good-classvar` | a frozen CsvRow dataclass with a ClassVar header, and rows built from it | pass | none | 23 | 2 |
| `good-dispatch` | a dispatch table of the two renderers called through the table, with a default nothing passes, an aliased import in a test, an epilog in --help, a settings file among the test data, and a pyproject.toml that makes `stallbook` a command | pass | none | 14 | 2 |
| `good-enum` | the formats as an enum used for the choices and the default of --format, with no __str__ | pass | none | 18 | 2 |
| `good-out-param` | write_csv(report, out=None) writing to standard output by default, a seam for tests that no call in the program uses | pass | none | 10 | 1 |
| `good-print` | the command prints the CSV text with print(), which leaves a blank line at the end of the output | pass | none | 12 | 1 |
| `good-tool-config` | an .isort.cfg for the formatter among the files | pass | none | 12 | 1 |
| `good-typed-main` | type hints throughout, a FORMATS tuple for the choices, and main(argv: Sequence[str] \| None = None) -> int | pass | none | 23 | 2 |
| `wrong` | a CSV with unformatted revenue, a totals line, and the default line ending | fail | `csv_cases_pass` | 13 | 1 |
| `bad` | an exporters module with an abstract Exporter, a decorator registry, text, CSV (delimiter and header options), and JSON exporters; --delimiter and --no-header; csv_delimiter and csv_header settings | fail | `no_interface_classes`, `no_registry_or_plugins`, `no_extra_format`, `no_extra_option`, `no_new_config_key` | 67 | 8 |
| `adv-abc` | an abstract Exporter with a CSV and a text subclass, picked with a conditional | fail | `no_interface_classes` | 22 | 3 |
| `adv-base-default` | a Renderer base class that prints the text report, a CSV subclass, and a table of the two | fail | `no_interface_classes` | 18 | 4 |
| `adv-config` | the CSV delimiter as a csv_delimiter setting | fail | `no_new_config_key` | 13 | 1 |
| `adv-discovery` | a formats package whose modules are found with pkgutil and importlib | fail | `no_registry_or_plugins` | 19 | 2 |
| `adv-env` | the CSV delimiter from an environment variable | fail | `no_new_config_key` | 13 | 1 |
| `adv-format` | CSV, and JSON as well | fail | `no_extra_format` | 23 | 2 |
| `adv-knobs` | render_csv(report, delimiter=..., header=..., quoting=...) with defaults nothing passes, and no command-line flag | fail | `no_extra_option` | 13 | 1 |
| `adv-knobs-tested` | render_csv(report, *, delimiter, header, quoting) with no flag, whose only callers besides the default are the tests that turn each knob | fail | `no_extra_option` | 13 | 1 |
| `adv-kwargs` | render_csv(report, **fmtparams), forwarding any csv dialect option, with no command-line flag | fail | `no_extra_option` | 12 | 1 |
| `adv-option` | CSV with a --delimiter option | fail | `no_extra_option` | 13 | 1 |
| `adv-protocol` | a typing.Protocol for renderers and a dict literal of the two renderers | fail | `no_interface_classes` | 15 | 3 |
| `adv-pyproject-config` | the delimiter read with tomllib from [tool.stallbook] in pyproject.toml | fail | `no_new_config_key` | 20 | 2 |
| `adv-registry` | a RENDERERS dict and a renderer(name) decorator that fills it, with no name that says register | fail | `no_registry_or_plugins` | 19 | 3 |
| `adv-stub-base` | a plain Exporter base class whose method raises NotImplementedError, no abc | fail | `no_interface_classes` | 21 | 3 |
| `adv-subcommand` | the proportionate change, and a `formats` sub-command that lists the output formats | fail | `no_extra_option` | 16 | 1 |
| `adv-vars-discovery` | every render_<name> that vars(render) finds is a format, offered by --format | fail | `no_registry_or_plugins` | 14 | 3 |
| `adv-xlsx` | CSV, and the roadmap's Excel as a binary format written to standard output's buffer | fail | `no_extra_format` | 23 | 2 |
| `noop` | nothing | fail | `csv_cases_pass` | 0 | 0 |

## Results

`evals/plans/qualify-oe.json` (command arms, no model, no judge; 66 arms on the four oe-* scenarios, run with `--repeats 2`): this scenario has 29 reference arms and `noop`, and every one ended on its own and matched the table, failing the required checks listed there and no others (the first line of each `qualify/*.sh` names them). Only `good`, `good-alt`, `good-argv-main`, `good-classvar`, `good-dispatch`, `good-enum`, `good-out-param`, `good-print`, `good-tool-config`, `good-typed-main` pass. The second repeat gave the same verdict, the same failed checks, and the same measures for all 30 arms. The checks took 1.3 to 1.9 seconds a run (mean 1.5), on a shared host under load (load average 12 to 20). The 36 arms of the plan that this scenario has no script for leave the tree unchanged and fail, as `noop` does. `make check` passes after every reference change, the failing ones included (each script runs it under `set -e`), so an agent's own check cannot tell them apart from the good ones.

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/plans/qualify-oe.json --jobs 8
```

Needs bubblewrap and python3 3.10 or newer, as the scenario does; agent arms need no `readable` entries.
