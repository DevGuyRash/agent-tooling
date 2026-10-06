# Visual library maintainer corpus

This directory is repository-maintainer test infrastructure. It is deliberately outside the shipped plugin skills.

## What it covers

- The pinned Mermaid 12.0.0 registry: all 37 registered diagram families.
- The two historical detector/error sentinels (`error` and `---`).
- Eleven layout cases, long/repeated-label cases, author configuration, literal-untrusted labels, and explicit error cases. CoSE-Bilkent has a passing mindmap example as well as the retained incompatible flowchart request.
- The maintained examples: the fictional trial with and without its narrative, and the showcase of every general block.
- A full Mermaid family gallery, a layout/error gallery, and a mixed report that places Mermaid drawings beside table, requirement-matrix, interval, excerpt, fact and callout blocks, with repeated labels under distinct record identifiers, one missing measurement and one long qualification.
- Exact source fidelity, expected renderer status, pinned syntax/reference metadata, offline packaging, and native rendering, containment and label geometry.
- The Mermaid engine contracts: layout repair geometry, clip-aware bounds, inherited theme and typography, failure isolation and recovery, and the reversible vendor patches.

Fixtures live in `mermaid-fixtures/`; `index.json` records each fixture's family, coverage kind, expected state, diagnostics and known visual limitations.

## Generate

The generator installs nothing and compiles nothing. It checks the maintained browser bundle against source unless `--skip-build-check` is explicitly supplied, verifies the pinned Mermaid vendor digest, builds into a sibling temporary directory, then atomically promotes the result. `--replace` only replaces a directory carrying this generator's marker.

`render_corpus.cjs` runs the shipped `dist/agentic-visuals.js` in a local VM without a DOM. It writes one report specification per maintainer report, in which each fixture is a `diagram` block whose id is `fixture-` plus the fixture file name with other characters replaced by `-`, and renders every report's static markup with `AgenticVisuals.renderReport`. The generator then packages each report with the skill's `report.py`, so the standalone files are exactly what that entry point produces and render in the reader's browser from embedded data.

Default output is the plugin project's generic `.local/visual-tests` directory:

```bash
python3 scripts/tests/visuals/generate.py
python3 scripts/tests/visuals/generate.py --replace
```

For a bounded review run, choose another dedicated generated directory:

```bash
python3 scripts/tests/visuals/generate.py \
  --output plugins/agentic-design-and-evaluation/.local/visual-review \
  --replace \
  --prior-preview-dir /absolute/path/to/prior/reports
```

`--prior-preview-dir` is optional and only inventories the HTML files of a supplied historical preview set. The maintained generator does not depend on any transient review directory by default. `python3 -B scripts/artifacts.py sync --task visual_previews` (or `just visual-previews`) generates the same corpus into the ignored local context directory.

Generated output contains:

- `specs/` — the gallery, layout and mixed report specifications.
- `bodies/` — deterministic static markup for those three reports and the three maintained examples, plus one body per fixture under `bodies/fixtures/`.
- `reports/` — six offline standalone reports written by `report.py`: `mermaid-gallery`, `mermaid-layouts`, `mixed-components`, `fictional-trial`, `fictional-trial-bare` and `showcase`.
- `inventory.json` — maintained examples, optional supplied prior previews, every fixture, and generated files with hashes/sizes.
- `manifest.json` — vendor, runtime and packager hashes, exact family list, special fixture list, and generated specification/body/report hashes.

## Fast tests

```bash
node scripts/tests/visuals/verify_registry.cjs
python3 -m unittest scripts.tests.visuals.test_corpus
python3 -m unittest scripts.tests.visuals.test_layout_repairs scripts.tests.visuals.test_mermaid_bounds scripts.tests.visuals.test_mermaid_vendor_patch
```

`just test-visual-corpus` runs all three. The registry test executes the pinned vendor in a local VM only. It never fetches upstream documentation; references in `index.json` are provenance strings pinned to the maintained Mermaid commit.

The corpus tests generate a temporary complete corpus by default, including standalone packaging checks. To test an already generated corpus, set `VISUAL_TEST_OUTPUT` to its directory. Missing output is an error rather than a skipped qualification. Determinism is checked by generating the specifications and bodies twice and comparing exact hashes; native screenshots record their browser and fonts rather than claiming identical rasterization across platforms.

The engine contracts compile `src/index.ts` with `tsc` into a temporary directory and exercise the compiled Mermaid modules against explicit DOM, font and renderer doubles from the plugin's `assets/visuals/tests/` directory. They are numerical and lifecycle models, not browser rendering tests.

The four error fixtures have distinct expected diagnostics. Two are malformed source. The routed block diamond retains a confirmed bundled-renderer exception. The flowchart/CoSE-Bilkent request retains its incompatible-layout diagnostic; the passing mindmap example demonstrates that CoSE-Bilkent itself is available. A different error message fails qualification.

Renderer completion and visual qualification are separate. The optional ELK stress, multi-root tree, overlap-removal, box, and rectangle-packing candidates retain observed routing or overlap limitations for the shared cyclic topology. Their `visualLimitation` records appear in the block heading and the drawing's caption. A `ready` result for these cases confirms execution and source preservation; it does not certify readable geometry. The ordinary family examples and layered-layout comparisons remain separate from these retained cases.

The Journey, C4, and Cynefin fixtures also declare `expectedRenderedLabels`. The native runner checks those labels in the drawing itself, independently of retained source text, to catch successful parses that discard records. Screenshot inspection still matters: a label can exist in the SVG while another label or shape covers it.

## Native qualification

The native runner attaches to one existing Chromium page. It never launches a browser or creates a page. When the debugger exposes multiple page targets, raw CDP requires an explicit `--target-id` so qualification cannot choose another open page ambiguously.

Raw CDP is preferred because offline emulation is scoped to the selected target:

```bash
python3 scripts/tests/visuals/native_runner.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --target-id EXISTING_PAGE_TARGET \
  --reports plugins/agentic-design-and-evaluation/.local/visual-tests/reports
```

If `websocket-client` is unavailable but Playwright is already installed, `--engine playwright` connects only when the CDP browser has exactly one existing page. It refuses a browser with multiple pages; use raw CDP with an explicit `--target-id` in that case. The runner never installs Playwright and does not set shared-context offline mode in the Playwright fallback.

The runner loads each generated report and waits for its own mount to finish and for every Mermaid diagram to reach `ready` or the explicitly retained `error` state. It checks that every block rendered and the page does not overflow horizontally, then, in the gallery, compares the DOM source attribute, the disclosed source and the figure's retained source with the exact fixture bytes, checks the expected state and diagnostic, the rendered evidence labels, one positive-bounds SVG and its accessible name, and finally checks the mixed report's composition, containment, page errors and the absence of HTTP(S) requests.

The focused native suites below create and close their own page targets in the supplied existing Chromium process through `native_page.py`, which needs `websocket-client` to be installed already. Each one renders its diagrams as complete reports through the public API (`renderReport` then `enhance`) inside a generated report that embeds Mermaid, such as `mixed-components.html`, and retains screenshots and JSON findings in the chosen output directory. No browser, dependency, or plugin is installed by these commands.

```bash
python3 scripts/tests/visuals/native_c4_container.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --report plugins/agentic-design-and-evaluation/.local/visual-tests/reports/mixed-components.html \
  --output plugins/agentic-design-and-evaluation/.local/c4-container-check

python3 scripts/tests/visuals/native_ishikawa_labels.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --report plugins/agentic-design-and-evaluation/.local/visual-tests/reports/mixed-components.html \
  --output plugins/agentic-design-and-evaluation/.local/ishikawa-check

python3 scripts/tests/visuals/native_venn_labels.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --report plugins/agentic-design-and-evaluation/.local/visual-tests/reports/mixed-components.html \
  --vendor plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js \
  --output plugins/agentic-design-and-evaluation/.local/venn-check
```

C4 qualification changes the emulated physical screen width to 390, 800, and 1600 pixels while holding its rendering container constant. It asserts the actual `screen.availWidth` change and compares native drawing geometry, catching a dependency that viewport resizing alone misses. The packaged C4 fix has a guarded, offline reproducer in `scripts/patch_mermaid_vendor.py`; `test_mermaid_vendor_patch.py` proves all declared patches are reversible changes in the exact pinned upstream bytes and protects existing inputs and outputs.

Ishikawa qualification renders rich, shallow and nested cause trees, and Venn qualification renders rich, multi-set, Unicode and single-set cases, each in the light and dark themes at two widths. Ishikawa checks wrapped cause labels for collisions, exact labels and branch counts, and content inside the final viewBox; Venn checks that set names and notes neither collide nor leave their semantic regions. `--vendor` evaluates a local candidate Mermaid runtime after the report starts, and `--expect-collisions` qualifies a known failing baseline instead of a fix.

On failure, inspect the retained result and screenshots before rerunning. Existing outputs from a failed run are evidence, not a passing qualification. Rebuild and regenerate after changes to sources or fixtures so the recorded input and report hashes describe the same checkpoint.

The documentation-catalog tests (`python3 -m unittest scripts.tests.test_mermaid_catalog`) are offline. Live upstream retrieval belongs only to the explicitly invoked `scripts/update_mermaid_catalog.py` maintenance command; it is never part of generation, normal builds, report startup, or these tests.

## Fixture editing rules

Keep fixtures deterministic and offline:

- no current dates, random IDs, live requests, or fetched data;
- retain exact family detector names and layout directives;
- keep repeated labels, missing values, long qualifications, Unicode, and relationship complexity meaningful rather than decorative;
- preserve intentional failures as failures;
- update `index.json` only when coverage/status/provenance actually changes;
- qualify changed sources against the pinned vendor before treating a family as covered.
