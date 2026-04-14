# Excel Workbook Sync Review

## Review Goal

Verify whether the Excel Workbook Sync skill's public claims are actually true in runtime use, with emphasis on workbook-agnostic behavior, bounded failure modes, and avoiding conclusions that depend on one curated workbook.

Status model used in this review:

- `Verified`: supported by code inspection plus runtime evidence.
- `Disproven`: contradicted by runtime behavior or implementation.
- `Unproven`: not established by current evidence; this includes universal claims that are too broad to prove from the available corpus.

## Corpus

External workbook corpus under review:

- `C:\Users\E135328\Documents\Templates`
- `C:\Users\E135328\repos\carvana-workflows\excel`

Discovered workbook set:

- 19 workbooks total
- 11 `.xlsx`
- 8 `.xlsm`
- 0 `.xls`
- 0 `.xlsb`

## Baseline Findings In Progress

This file is written incrementally during the review. Evidence sections below are updated as each verification layer completes.

## Layer 1: Shipped Tests

Completed.

Evidence:

- `python -m unittest discover -s skills/excel-workbook-sync/tests -p 'test_*.py'`
- Result: `Ran 54 tests in 67.153s`
- Result: `OK (skipped=6)`
- The skipped tests are explicit live COM tests gated behind `EXCEL_SYNC_LIVE=1`, so the default suite does not prove live write-path reliability.
- Excel COM is available on this host. Direct COM probe succeeded with Excel version `16.0`.

Assessment:

- The skill has meaningful built-in coverage for launcher behavior, package-backed inspect/query/bootstrap, generic pull/compare/audit behavior, and some runtime edge cases such as path spacing and timeouts.
- The built-in suite is not sufficient to verify the broader public claims on its own because the live COM/write cases were skipped and the external workbook corpus is not exercised by default.

## Layer 2: Generic CLI on External Workbooks

Completed.

External sweep root:

- `.local/excel-sync-review/`

Completed generic sweep summary:

- 19 of 19 external workbooks completed `pull` successfully.
- 19 of 19 external workbooks completed `compare` successfully at the process level.
- 0 `pull` timeouts.
- 0 `compare` timeouts.
- 0 non-timeout generic CLI process failures.
- Raw parity failed on all 19 completed compares.
- Normalized parity passed on 18 of 19 completed compares.
- The one normalized-parity failure was `C:\Users\E135328\repos\carvana-workflows\excel\lyft\lyft_invoice_template.xlsx`, where COM extraction failed during compare.
- Every expected generic artifact path was written for all 19 `pull` runs and all 19 `compare` runs:
  - `normalized.json`
  - `workbook_structure/{tables,names,conditional_formatting,formulas,data_validation,protection,charts,pivots}.json`
  - `power_query/{connections,queries}.json`
  - `compare.json`

Observed raw mismatch categories across the real-workbook corpus:

- `nameCount`
- `vbaAccessible`
- `vbaComponentCount`
- `comExtraction`

Concrete completed examples:

- `check_requests_template.xlsx`: raw mismatch on `nameCount`, `vbaAccessible`, `vbaComponentCount`; normalized parity passed.
- `FEDEX BATCH UPLOAD.xlsx`: raw mismatch on `nameCount`, `vbaAccessible`, `vbaComponentCount`; normalized parity passed.
- `T&R CHECKS Template.xlsx`: raw mismatch on `nameCount`, `vbaAccessible`, `vbaComponentCount`; normalized parity passed.
- `T&R CHECKS Template-Modified.xlsx`: raw mismatch on `nameCount`, `vbaAccessible`, `vbaComponentCount`; normalized parity passed.
- `T&R UPLOAD B.xlsx`: raw mismatch on `vbaAccessible`, `vbaComponentCount`; normalized parity passed.
- `T&R UPLOAD TEMPLATE.xlsm`: raw mismatch on `vbaAccessible`, `vbaComponentCount`; normalized parity passed.
- `lyft_invoice_template.xlsx`: normalized parity failed because COM extraction failed with `Unable to get the Open property of the Workbooks class`.

Additional pull observations from completed workbooks:

- Internal-name filtering is active on real workbooks and can be substantial.
- Example counts from finished pulls:
  - `check_requests_template.xlsx`: `1` user-visible name, `4` filtered internal names, `3` tables.
  - `FEDEX BATCH UPLOAD.xlsx`: `0` user-visible names, `46` filtered internal names, `2` tables.
  - `T&R CHECKS Template-Modified.xlsx`: `1` user-visible name, `25` filtered internal names, `2` tables, `1` query.
  - `T&R UPLOAD TEMPLATE-Modified_v2.xlsm`: `23` user-visible names, `200` filtered internal names, `15` tables, `12` queries.

Interim assessment:

- The documented distinction between raw parity and normalized parity is supported by real workbook evidence.
- The generic CLI handled the full external corpus without process-level timeout or crash, which is strong evidence for baseline portability.
- The workbook-agnostic claim is still not fully verified because one real workbook (`lyft_invoice_template.xlsx`) failed COM extraction in `compare` under `auto`, leaving normalized parity false for that specimen.
- The generic surface handled that COM failure explicitly in `compare.json` instead of crashing, but the failure still counts against any stronger “reliable in all scenarios” reading.

Copied-workbook audit evidence:

- Single-workbook `audit` completed successfully on `ACV UPLOAD.xlsm` in `46.946s`.
- The single audit reported:
  - `scenarioSet: full`
  - completed mutation scenarios, including table creation, conditional-formatting mutations, and Power Query mutations
  - `regressions: []`
  - post-mutation normalized parity still `true`
- `matrix-audit` completed successfully across a mixed three-workbook subset in `152.122s`:
  - `check_requests_template.xlsx`
  - `ACV UPLOAD.xlsm`
  - `lyft_invoice_template.xlsx`
- All three matrix entries completed with `mutationStatus: changed`.
- The two templates without prior COM-compare issues retained normalized parity after mutation.
- The Lyft workbook remained a special case: baseline and post-mutation normalized parity were both false because of the same COM extraction failure seen in the generic compare sweep, not because `matrix-audit` crashed.

## Layer 3: Manifest CLI and Package Backend

Completed, with one explicit remaining proof gap.

Confirmed so far:

- Package-backed `inspect`, `query`, and `bootstrap` completed successfully on real external workbooks in both formats claimed by the docs:
  - `.xlsm`: `ACV UPLOAD.xlsm`
  - `.xlsm` with spaces in path: `T&R UPLOAD TEMPLATE.xlsm`
  - large `.xlsm`: `T&R UPLOAD TEMPLATE-Modified_v2.xlsm`
  - `.xlsx`: `BLANK LIEN ACH TEMPLATE (DUPLICATE FORMULA).xlsx`
  - `.xlsx` with Power Query content: `lyft_invoice_template.xlsx`
- Representative runtimes on real package-backed commands:
  - `ACV UPLOAD.xlsm`: inspect `6.215s`, query `5.701s`, bootstrap `7.694s`
  - `T&R UPLOAD TEMPLATE.xlsm`: inspect `17.538s`, query `14.296s`, bootstrap `14.177s`
  - `T&R UPLOAD TEMPLATE-Modified_v2.xlsm`: inspect `64.684s`, query `62.515s`, bootstrap `54.824s`
  - `BLANK LIEN ACH TEMPLATE (DUPLICATE FORMULA).xlsx`: inspect `3.767s`, query `3.995s`, bootstrap `2.652s`
  - `lyft_invoice_template.xlsx`: inspect `10.374s`, query `15.280s`, bootstrap `5.173s`
- Completed bundle roots contain:
  - `excel-sync.manifest.json`
  - `workbook_structure/tables.json`
  - `workbook_structure/names.json`
  - `workbook_structure/conditional_formatting.json`
  - `workbook_structure/formulas.json`
  - `workbook_structure/data_validation.json`
  - `workbook_structure/protection.json`
  - `workbook_structure/charts.json`
  - `workbook_structure/pivots.json`

Observed manifest/query shape on completed real-workbook package runs:

- `workbookPath` preserved the original absolute workbook path correctly.
- `structure` included the expected workbook-structure artifact paths.
- `capabilities`, `warnings`, and `unsupported` were present in successful real-workbook responses.
- `canWrite` was `false` in the successful real-workbook package responses examined so far, which matches the documented read-only boundary.
- Real-workbook `unsupported` output correctly reported package backend limits such as unsupported live VBA/project/reference access and unparsed chart/pivot metadata.
- The Lyft `.xlsx` specimen produced Power Query output in successful package-backed query/bootstrap runs, including a query connection and generated query artifacts.
- The completed `.xlsm` examples without Power Query artifacts did not emit `powerQuery` sections in the bootstrapped manifest, which appears consistent with workbook content rather than with launcher failure.

What remains open in this layer:

- Complete return-status evidence for the one remaining specimen in the original mixed subset batch, if needed.
- Prove the stronger bounded-failure claim that slow package reads fail explicitly instead of hanging indefinitely. The successful bounded completions above are good evidence, but they do not by themselves prove explicit timeout/failure behavior under worst-case reads.

## Layer 4: Live COM and Write Flows

Completed with failure.

Current evidence:

- Excel COM is available locally and the COM-gated live test layer has been started with `EXCEL_SYNC_LIVE=1`.
- Live COM-enabled suite result:
  - `Ran 54 tests in 392.975s`
  - `FAILED (failures=1)`
- The failing shipped live test was:
  - `test_live_cf_push_then_pull_roundtrips_new_rule`
- Failure details:
  - file: `skills/excel-workbook-sync/tests/test_excel_workbook_sync.py`
  - assertion: after pushing a new conditional-formatting rule into a copied fixture workbook and pulling back, no matching pulled rule with sheet `AP_INVOICES_INTERFACE`, address `$C$5:$C$9`, and formula `=TRUE` was found.
- The push step in that test still reported `PUSH CF CF-LIVE-TEST-0001`, so this is not a launcher-startup failure. It is a real roundtrip-behavior failure in the conditional-formatting path.
- A direct standalone reproduction of the same push/pull scenario outside the full suite did surface the expected pulled rule with sheet `AP_INVOICES_INTERFACE`, address `$C$5:$C$9`, and formula `=TRUE`.
- That means the conditional-formatting failure is at least state-dependent or flaky, not obviously a simple “always broken” deterministic repro. It still counts as a reliability defect because the shipped live suite failed on a supported path.

## Claim Ledger

Interim statuses:

- `The generic Python surface is workbook-agnostic.`  
  Status: `Unproven`  
  Reason: the full external sweep completed successfully at the process level, but one real workbook still failed COM extraction in `compare`, and no finite corpus can prove a universal claim.

- `Generic workbook audit on safe copied workbooks.`  
  Status: `Verified`  
  Reason: shipped tests cover copied-workbook audit semantics, a real-workbook `audit` completed successfully on a copied `.xlsm`, and `matrix-audit` completed successfully on a mixed real-workbook subset using copied workbooks under `.local`.

- `Raw and normalized parity both matter` / normalized parity filters internal names and excludes live-VBA-only differences.  
  Status: `Verified`  
  Reason: completed real-workbook compares show raw mismatches while normalized parity passes, with mismatches exactly in the documented categories.

- `Windows Excel COM is required for live mutation, .xls and .xlsb, and manifest-driven write flows.`  
  Status: `Unproven`  
  Reason: COM is available and built-in live tests exist for write flows, but `.xls` and `.xlsb` were not present in the supplied corpus, so the full combined claim is not yet established.

- `OOXML/package pull, query, and bootstrap work portably for .xlsx and .xlsm, but remain read-only.`  
  Status: `Verified`  
  Reason: successful real-workbook package-backed `inspect`, `query`, and `bootstrap` runs were observed on both `.xlsx` and `.xlsm` specimens, including a spaced-path `.xlsm` and a large `.xlsm`, and the responses reported `canWrite: false`.

- `Manifest query/bootstrap payloads include capabilities, warnings, and unsupported fields.`  
  Status: `Verified`  
  Reason: built-in tests assert these fields and successful real-workbook package responses on the external subset included them.

- `Manifest read flows use bounded package-helper execution.`  
  Status: `Unproven`  
  Reason: real `.xlsx` and `.xlsm` package-backed reads completed successfully on the tested subset, including a large `.xlsm`, but that does not by itself prove the stronger documented timeout/fail-explicitly behavior under worst-case slow reads.

- `.xls and .xlsb remain COM-dependent.`  
  Status: `Unproven`  
  Reason: no `.xls` or `.xlsb` files were supplied in the requested external corpus.

- `Manifest-driven write flows` / live roundtrip behavior are reliable on the shipped fixture workspace.  
  Status: `Disproven`  
  Reason: the shipped live COM test `test_live_cf_push_then_pull_roundtrips_new_rule` failed on this host using the bundled fixture, demonstrating that at least one write-path roundtrip claim is currently false.

## Final Assessment

- The skill is materially real and broadly functional. Read-only package-backed flows on `.xlsx` and `.xlsm`, generic `pull`, generic `compare`, and copied-workbook audit flows all worked across substantial real-workbook coverage.
- Several public claims are verified: normalized parity semantics, output artifact presence, package-backed read-only boundaries, and manifest payload capability diagnostics.
- Two important stronger claims do not hold at the level implied by “works reliably in all scenarios”:
  - generic `compare --engine auto` is not uniformly reliable across the tested corpus because `lyft_invoice_template.xlsx` failed COM extraction;
  - live manifest write-path reliability is disproven by the failing shipped conditional-formatting roundtrip test.
- Format-support claims for `.xls` and `.xlsb`, and the stronger timeout/fail-explicitly promise for worst-case package reads, remain unproven because this review did not include suitable specimens or forced-timeout scenarios.
- Net verdict: the skill does not justify an “everything it claims is fully true and reliable in all scenarios” conclusion. It supports a narrower conclusion: the read-oriented surfaces are strong on the tested corpus, but at least one live write-path and one real-workbook COM compare path are not currently reliable enough to support the broader claim.
