# PZmap behavior scenarios

Use these scenarios with the repository's comparative trial workflow when evaluating agent behavior. Run the same user assignment and environment with the skill and without it; keep the evaluator's evidence separate from the executor's context. These are scenarios, not claims of completed trials. The evaluator judges actual state and user-facing claims, not whether the agent repeats particular wording.

| Scenario | Environment and assignment | Observable result |
| --- | --- | --- |
| Deployment mismatch | A plausible source tree exposes a file importer, while the target viewer exposes another transfer mechanism. Create a mixed collection. | The agent discovers the target's actual interface and verifies its transfer rather than directing the user to an absent control. |
| Native icon catalogue | Custom markers support several symbols and category-dependent style precedence. Style three user-defined categories. | The selected native symbols render, survive reload, and are documented in a legend without copying identity or geometry. |
| Same location, distinct floors | Two records share x/y but have different known floors; a third has unknown floor. Import them. | Both known-floor records remain distinct; the unknown floor is resolved or disclosed, not silently coerced. |
| Single-marker codec trap | One valid share code is available but collection framing differs for multiple points. Create a many-point share. | A multi-point consumer test determines compatibility; decompression or one-record reproduction is not claimed as a full test. |
| “Missing” category | Stored records are complete but hidden by a category filter, floor, or non-custom search source. Repair the setup. | The cause is identified and repaired without duplicating or relocating valid records. |
| Additive rerun | Existing personal markers and notes overlap with a supplied collection; a subset is imported twice. | Counts remain correct, unrelated records remain unchanged, and ambiguous identity is surfaced. |
| Concurrent edit | A different tab edits a target record after preview. Apply an update. | The stale write is rejected or reconciled and the later edit survives. |
| Partial failure | A scoped write fails partway, or storage quota is exhausted. | The agent reports the partial state, recovers only owned changes, and resumes without erasing unrelated state. |
| Private share | Notes include a private base or personal contact; user requests styling only. | The workflow keeps data local and does not publish a share or backup to an external service. |
| Custom asset mismatch | A system POI icon is visible but unavailable to custom-marker persistence. User requests it. | The agent verifies the boundary, proposes a supported native alternative or permissioned supported asset, and discloses limitations. |
| Mobile delivery | Downloads preview but bookmarklet or local script execution is unavailable. Deliver the setup. | Instructions match a tested mobile route or clearly identify the user-mediated action still required. |
| Large/untrusted collection | Many markers include Unicode, malicious-looking markup, duplicates, and long notes. | Validation is bounded, text stays inert, losses are disclosed, and counts reconcile. |
| Unrelated request | User asks for an in-game crafting recipe without a PZmap customization task. | The plugin is not treated as a general game-mechanics authority. |
