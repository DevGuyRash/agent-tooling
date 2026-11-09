# Appearance and visibility

## Use the native catalogue deliberately

Start with the deployed editor's symbol/icon picker, category controls, and available style options. Inspect an actual styled marker or the loaded catalogue when the UI does not reveal identifiers. Native icon names, numeric indices, sprite offsets, asset paths, and category keys are deployment-specific values.

Build a task-local style map from each user category to a native icon identifier, supported size/color/label behavior, and optional group membership. Explain the visual choices with a short legend. Category names are arbitrary user data, not a fixed inventory of resources.

Distinguish a user-selectable marker symbol from a system POI's appearance. A sprite that the renderer uses for built-in locations may not be allowed for custom markers, and a visible icon may require more than an icon field. Test through the custom-marker editor, persistence, and sharing before promising equivalence.

Copy verified appearance fields, not a whole sample object. Some deployments couple category to the rendered symbol; others derive style from the group or a default. Establish precedence with one-field edits. Reusing a sample's identity or coordinates can replace a user marker instead of restyling the intended one.

Use labels or shapes as well as color so categories remain distinguishable under color-vision differences, small-screen rendering, and low zoom. Test contrast against the actual map and its light/dark modes where supported. Keep native clustering and zoom-visibility behavior distinct from missing data.

## Optional custom assets

Check whether the custom-marker renderer accepts a chosen asset type and whether the format survives export/import, reload, and sharing. Consider dimensions, scaling, transparency, accessible contrast, same-origin and content-security restrictions, remote availability, and licensing.

A custom asset that only renders in a transient DOM overlay is not a persisted native icon. Externally hosted assets may require network access and disclose requests to their host. Use user-approved assets and locations, and disclose those dependencies. Prefer a supported native symbol when it communicates the category adequately.

## Category-wide restyling

Preview the affected IDs and style changes. Limit selection to the requested collection and semantic category. Matching a common word in all saved marker titles can capture unrelated personal pins.

Apply styles only to selected records and reconcile field-by-field afterward. Keep native IDs, geometry, coordinates, floors, names, descriptions, notes, and unrelated groups unchanged unless the user requests those changes. Preserve a user's individually overridden style or surface it as a conflict according to the agreed update policy.

## Diagnose a missing marker at the correct layer

Compare these layers in order:

1. **Expected records:** Does the source collection include the target and its intended floor, category, and coordinates?
2. **Accepted and stored records:** Did the importer accept it, assign an identity, and persist the record without replacement, truncation, or cross-floor deduplication?
3. **Search/index:** Is the query using the custom-marker source rather than built-in POIs? Are labels or categories indexed as expected?
4. **Visibility:** Check marker/group toggles, selected floor, map/build selection, spoiler or visited state, zoom thresholds, clustering, viewport, and other filters.
5. **Renderer:** Confirm the selected native symbol resolves, its style is supported, and its position is not obscured by another marker or map geometry.

Clear a visibility restriction or repair the rendering at its source. Reimport only when the stored record is genuinely absent and identity reconciliation confirms adding it is appropriate. Nearby markers or a symbol that resembles another category do not establish that data is missing.

Preserve the true floor. Where the user needs an easily discoverable surface anchor for a lower-floor destination, add a separately identified and clearly labeled entrance marker with the user's agreement. Do not silently relabel the underground destination as ground level.

Finish by checking counts by category and floor, visually inspecting every distinct style, and testing the search terms the user is likely to use. Diagnose a floor or filter problem separately from an unsupported icon.
