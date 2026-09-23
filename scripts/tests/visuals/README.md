# Visual library maintainer corpus

This directory is repository-maintainer test infrastructure. It is deliberately outside the shipped plugin skills.

## What it covers

- The pinned Mermaid 12.0.0 registry: all 37 registered diagram families.
- The two historical detector/error sentinels (`error` and `---`).
- Eleven layout cases, long/repeated-label cases, author configuration, literal-untrusted labels, and explicit error cases. CoSE-Bilkent has a passing mindmap example as well as the retained incompatible flowchart request.
- The maintained field-study, compact, embedded, stress, and snippets consumer examples.
- A full Mermaid family gallery, a layout/error gallery, and a mixed-component report combining Mermaid with quantitative, structured, narrative, lineage, and native-record components. Its lineage keeps repeated labels under distinct IDs, parallel qualified relationships, and one long bounded note for reader-navigation qualification.
- Exact source fidelity, expected renderer status, pinned syntax/reference metadata, offline packaging, SVG/PNG export, containment, and representative native interaction.

Fixtures live in `mermaid-fixtures/`. Plugin-local compatibility tests locate them through the repository-relative external path; `AGENTIC_VISUAL_MERMAID_FIXTURES` can override the location for a copied checkout.

## Generate

The generator installs nothing. It checks the maintained browser bundle against source unless `--skip-build-check` is explicitly supplied, verifies the pinned Mermaid vendor digest, builds into a sibling temporary directory, then atomically promotes the result. `--replace` only replaces a directory carrying this generator's marker.

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

`--prior-preview-dir` is optional and exists only to inventory a supplied historical preview set. The maintained generator does not depend on any transient review directory by default.

Generated output contains:

- `bodies/` — deterministic report fragments plus one body per fixture.
- `reports/` — eight offline standalone reports.
- `inventory.json` — maintained examples, optional supplied prior previews, every fixture, and generated files with hashes/sizes.
- `manifest.json` — vendor/runtime hashes, exact family list, special fixture list, and generated body/report hashes.

## Fast tests

```bash
node scripts/tests/visuals/verify_registry.cjs
python3 -m unittest scripts/tests/visuals/test_corpus.py
```

The registry test executes the pinned vendor in a local VM only. It never fetches upstream documentation; references in `index.json` are provenance strings pinned to the maintained Mermaid commit.

The Python tests generate a temporary complete corpus by default, including standalone packaging checks. To test an already generated corpus, set `VISUAL_TEST_OUTPUT` to its directory. Missing output is an error rather than a skipped qualification. Determinism is checked by generating the bodies twice and comparing exact hashes; native screenshots record their browser and fonts rather than claiming identical rasterization across platforms.

The four error fixtures have distinct expected diagnostics. Two are malformed source. The routed block diamond retains a confirmed bundled-renderer exception. The flowchart/CoSE-Bilkent request retains its incompatible-layout diagnostic; the passing mindmap example demonstrates that CoSE-Bilkent itself is available. A different error message fails qualification.

Renderer completion and visual qualification are separate. The optional ELK stress, multi-root tree, overlap-removal, box, and rectangle-packing candidates retain observed routing or overlap limitations for the shared cyclic topology. Their `visualLimitation` records appear above the drawing and in its exportable caption. A `ready` result for these cases confirms execution and source preservation; it does not certify readable geometry. The ordinary family examples and layered-layout comparisons remain separate from these retained cases.

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

Native checks use the generated reports' real enhancement entry. They wait for all Mermaid fixtures to reach `ready` or the explicitly retained `error` state, compare the DOM source attribute to the exact fixture bytes, check positive SVG bounds, exercise one native item selection, capture real SVG/PNG export blobs without changing browser-wide download behavior, and verify mixed-report containment.

The focused native suites below create and close their own page targets in the supplied existing Chromium process. They use real pointer, wheel, and keyboard input and retain screenshots, JSON findings, and input hashes in the chosen output directory. No browser, dependency, or plugin is installed by these commands.

```bash
python3 scripts/tests/visuals/native_inspector.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --reports plugins/agentic-design-and-evaluation/.local/visual-tests/reports \
  --output plugins/agentic-design-and-evaluation/.local/inspector-check

python3 scripts/tests/visuals/native_navigation.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --reports plugins/agentic-design-and-evaluation/.local/visual-tests/reports \
  --report compact.html --theme light \
  --output plugins/agentic-design-and-evaluation/.local/navigation-check

python3 scripts/tests/visuals/source_review_native.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --report plugins/agentic-design-and-evaluation/.local/visual-tests/reports/mixed-components.html \
  --output plugins/agentic-design-and-evaluation/.local/source-check

python3 scripts/tests/visuals/native_c4_container.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --report plugins/agentic-design-and-evaluation/.local/visual-tests/reports/mixed-components.html \
  --output plugins/agentic-design-and-evaluation/.local/c4-container-check

python3 scripts/tests/visuals/native_mermaid_exports.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --gallery plugins/agentic-design-and-evaluation/.local/visual-tests/reports/mermaid-gallery.html \
  --gallery-sha256 EXACT_GENERATED_GALLERY_SHA256 \
  --output plugins/agentic-design-and-evaluation/.local/mermaid-export-check

python3 scripts/tests/visuals/native_portable_review.py \
  --cdp http://127.0.0.1:EXISTING_DEBUG_PORT \
  --output plugins/agentic-design-and-evaluation/.local/portable-review-check

python3 -m unittest scripts/tests/visuals/test_mermaid_bounds.py
python3 -m unittest scripts/tests/test_mermaid_catalog.py
```

Inspector qualification covers floating and pinned evidence, pan correction, scrolling near the canvas boundary, short windows, drawer and expanded-view returns, long relationship notes, repeated labels with distinct record IDs, and cleanup/re-enhancement. Portable-review qualification generates a small current-runtime report, opens a saved note in two file tabs, saves a completed sibling, and keeps the other edit as a stale draft. Its notebook backup, Markdown handoff, and actual reopened HTML must retain the draft's exact earlier saved note and evidence. The original assembly recipe must remain unchanged and reopened controls must not duplicate.

Navigation qualification distinguishes a fitted drawing from a zoomed drawing with scrollable content. It checks real drag and wheel input, page scrolling when the fitted drawing has no overflow, pointer capture and its loss, temporary Space-to-pan in Select and Text modes, Reset, and expansion/return state. The source suite adds a deterministic diagram through the report's public API without changing the supplied file. It compares retained and downloaded source bytes, exercises wrapping and source-reader return, and compares full SVG and decoded PNG exports before and after zoom/pan. Native textarea line-ending normalization is recorded separately from source-byte preservation.

C4 qualification changes the emulated physical screen width to 390, 800, and 1600 pixels while holding its rendering container constant. It asserts the actual `screen.availWidth` change and compares native drawing geometry, catching a dependency that viewport resizing alone misses. The packaged C4 fix has a guarded, offline reproducer in `scripts/patch_mermaid_vendor.py`; `test_mermaid_vendor_patch.py` proves all declared patches are reversible changes in the exact pinned upstream bytes and protects existing inputs and outputs.

The Mermaid export suite requires the exact generated gallery hash, then compares every displayed source with the current fixture before exporting. It downloads a full-context SVG through native controls for each ready case, retaining labels, geometry, captions and declared visual limitations. Journey, C4, Cynefin, Ishikawa and Venn additionally compare complete SVG bytes and decoded PNG pixels at Reset and after native zoom/pan. The saved images remain available for inspection; byte invariance does not by itself establish visual quality.

Use a new output directory for portable-review runs; existing contents are refused, and the dedicated test storage key is derived from that directory. On failure, inspect the retained result and screenshots before rerunning. Existing outputs from a failed test are evidence, not a passing qualification. Rebuild and regenerate after changes to sources or fixtures so the recorded input and report hashes describe the same checkpoint.

The documentation-catalog tests are offline. Live upstream retrieval belongs only to the explicitly invoked `scripts/update_mermaid_catalog.py` maintenance command; it is never part of generation, normal builds, report startup, or these tests.

## Fixture editing rules

Keep fixtures deterministic and offline:

- no current dates, random IDs, live requests, or fetched data;
- retain exact family detector names and layout directives;
- keep repeated labels, missing values, long qualifications, Unicode, and relationship complexity meaningful rather than decorative;
- preserve intentional failures as failures;
- update `index.json` only when coverage/status/provenance actually changes;
- qualify changed sources against the pinned vendor before treating a family as covered.
