# Survey and evidence patterns

An initial capture can expose the next useful question. Preserve the question, observed state, and sources needed to inspect it; choose the next interaction from the application's actual behavior. [The runnable example](examples/survey.mjs) demonstrates a single state with discovery and diagnostics. Extend it with ordinary Playwright code for the assignment.

## Discover and select

`discover(page, options)` inspects the rendered DOM, frames, and open shadow roots. It returns frame identity, URL, title, geometry, links, controls, scroll containers, regions, occurrence information, and locator clues. Meaningful queries and fragments remain intact. The result reports its limits and truncation. Default bounds are 500 items per category per frame, 20,000 inspected nodes, 50 frames, and 2,000 characters per name; callers can change `maxItems`, `maxNodes`, `maxFrames`, `maxTextLength`, `timeout`, and `includeHidden` when more observation is useful. Names preserve their observed length and truncation marker. They are DOM label/text clues rather than a complete accessibility-name computation.

```js
const observed = await discover(page, { maxItems: 200 });
await run.record({ type: 'discovery', state: { url: page.url() }, observed });
const candidates = observed.frames.flatMap(frame => frame.links ?? []);
```

The returned clues locate an occurrence in that observation. Verify identity against the current page when acting after a rerender or navigation. Accessible roles/names and application IDs can establish more durable locators. Frame identities and observed CSS paths support recovery of the capture context; they do not define a permanent site model.

Menus, tabs, dialogs, filters, and virtualized items may reveal states without changing the URL. Record the action and resulting state when that relationship helps reproduce a finding. Inspect relevant repository routes or other source context when available. Newly discovered links are candidates for the authorized survey; their presence alone does not establish that following or submitting them serves the task.

Choose an explicit work bound for broad exploration: for example, the requested journeys, a page count, or an elapsed-time budget. The executor determines which states fit that bound and what to retain as pending. Device and appearance matrices are useful when the comparison needs them; a focused layout defect may only need one transition and its neighboring sizes.

## Readiness and capture

`waitForReadiness(page, options)` makes bounded observations of fonts, images in view, frame documents, and layout. Its `status` distinguishes `ready`, `unsettled`, and `cancelled`, and its checks, limits, samples, and errors remain available. These statuses describe the requested observations. Supply an application check when its state determines the capture:

```js
const observation = await capture(page, {
  run,
  label: 'Completed import',
  state: { url: page.url(), comparisonKey: 'import-complete', actions: ['Start import'] },
  readiness: {
    timeout: 15000,
    check: async page => ({
      ready: await page.getByRole('status').filter({ hasText: 'Import complete' }).isVisible(),
    }),
  },
});
```

A readiness callback returns `true` or `{ ready: true, ...context }` when its condition is met. It receives the page and a context containing the remaining time, observations, and cancellation signal. Keep callback operations bounded and honor cancellation. A callback that only performs an assertion and returns no value leaves the requested readiness condition unmet.

`capture(page, options)` records viewport evidence by default. Supply a Locator or CSS string as `target` for an element, `{ x, y, width, height }` as `region` for a clip, or `scroll` for a bounded scroll sequence. `scroll: true` uses the document; `{ container, axis, maxFrames, overlap }` selects a nested container, axis (`x`, `y`, or `both`), frame bound, and overlap fraction. The default scroll bound is 40 frames with 0.18 overlap. Reaching the observed scroll extent establishes that extent; virtualized backing records may require application-specific exploration. It writes image bytes as they become available and restores tracked scroll positions. Replaced elements or frame navigation can prevent restoration; the capture retains completed evidence and reports unresolved restoration as partial. The record retains label, state, readiness, diagnostics, image references, and supplied context. Use element or region captures where that makes a detail understandable, retaining a broader state capture when the surrounding context matters.

`observeContext(context, { limit })` attaches bounded diagnostics to existing and new pages, including popups. Its `snapshot()` includes retained events and a dropped-event count. `close()` removes its listeners. It preserves expected page errors as observations; the executor decides which events matter to the finding. Select diagnostic content before sharing when URLs or application messages contain private values.

## Evidence ownership and continuation

`createEvidenceRun({ outputDir, metadata, resume, durability })` opens an owned writer. The default `durability: 'process'` retains completed writes through process interruption. Optional `durability: 'disk'` requests filesystem synchronization for each write; the filesystem and hardware determine power-loss behavior. The chosen mode is recorded and preserved on resumption. Its asynchronous methods append records and store artifacts. `record(observation)` preserves JSON-serializable caller fields and assigns an identity if absent. `storeBlob(bytes, { extension, mime })` and `storeArtifact(filePath)` return content-addressed references. Identical bytes share storage while each capture keeps its original context.

```js
const run = await createEvidenceRun({ outputDir, resume: true });
try {
  for (const task of await run.pendingTasks()) {
    // Reconstruct the task's starting state and complete its authorized work.
    // await run.complete(task.id, { observationId });
  }
} finally {
  await run.close();
}
```

Queue useful continuation state with `enqueue({ id, ...context })`; call `complete(taskId, result)` when that work is complete. Re-enqueuing the same task identity and context is idempotent. A changed task needs a distinct identity. Resumption exposes pending tasks to the executor; it does not replay external effects automatically.

`finish()` records the end of an evidence pass and its pending-task count. `close()` drains writes and releases ownership without implying completion. Use `finally` for writer closure. After a failed write, reopen with `resume: true`; completed records and original trailing bytes remain recoverable. A concurrent writer receives an ownership conflict. Choose separate runs for independent workers and compare their outputs afterward.

## Review and comparison

`renderGallery(runDir)` produces a portable local index. `readEvidenceRun(runDir, options)` returns a compact summary and a bounded record page; choose `type`, `taskId`, `id`, `query`, `offset`, `limit`, or `fields` for the material needed. The JavaScript API accepts `limit: Infinity` for an explicit full read. Retain originals when extracting a smaller review set.

`importCaptureCollection(inputDir, { outputDir })` accepts a native evidence run or the screenshot collection produced by the `capture.mjs` collection format. It keeps original bytes and source metadata while removing duplicate byte storage. `compareRuns(leftDir, rightDir, { outputDir })` retains matched observations and exposes ambiguous or unmatched states. Automatic correspondence uses recorded state and capture scope, including selected frame identity. Measured element geometry remains observation data. Supply `state.comparisonKey` when the same meaningful state will recur across runs. Exact equality of image bytes establishes equality of those captures; a visual difference needs interpretation in its recorded environment.

Record observed transitions as `{ type: 'transition', from: first.id, to: second.id, label: 'Open details' }` when a navigation map helps review. Link a finding to its observation IDs and original state, so a fresh consumer can inspect the evidence without the authoring conversation.

## Traces and video

Playwright's native context APIs compose with the run. Start tracing before the relevant actions and stop it before closing the context:

```js
await context.tracing.start({ screenshots: true, snapshots: true });
try {
  // Execute the journey and collect relevant captures.
} finally {
  await context.tracing.stop({ path: tracePath });
  const trace = await run.storeArtifact(tracePath, { mime: 'application/zip' });
  await run.record({ type: 'trace', state, artifact: trace });
}
```

For video, pass `recordVideo` through `contextOptions`, retain each relevant `page.video()` handle, and close the context to flush recording. The shared runtime uses a browser connection, so copy the completed recording with `saveAs()` while that browser connection remains open:

```js
const video = page.video();
// Execute and capture the relevant interaction.
await context.close();
if (video) {
  await video.saveAs(videoPath);
  const recording = await run.storeArtifact(videoPath, { mime: 'video/webm' });
  await run.record({ type: 'video', state, artifact: recording });
}
// Close the owning session after saving the recording.
```

`video.path()` is unavailable for a connected remote browser. `saveAs()` preserves the file through Playwright's transport. Traces and videos add context and volume; use them for interactions or failures they help explain. See [tracing](https://playwright.dev/docs/api/class-tracing) and [video](https://playwright.dev/docs/videos).

CLI captures use a stable comparison key from the requested URL, capture selection, viewport/device, browser/channel and color preference. Execution-specific paths remain in separate environment provenance. `capture --comparison-key KEY` supplies an explicit correspondence for a deliberate cross-configuration comparison. The `compare` command prints a compact summary and paths to the complete comparison JSON and gallery.
