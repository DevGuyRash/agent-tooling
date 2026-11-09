# Discovery and transfer

## Identify the application that consumes the data

Open the exact target URL and establish the selected map, active overlays, origin, and browser capabilities. Similar names and forks can expose different formats. The PZmap home page is a discovery starting point, not a permanent import contract: [pzmap.org](https://pzmap.org/).

Inspect the live controls and loaded application resources using the available authorized browser tools. Follow the source/contact links the deployment itself exposes when source inspection helps. Record resource URLs or hashes in task-local evidence. Establish deployment parity by matching served resources or observed behavior to the source being inspected.

Record the capabilities the request needs: point/area/line geometry, world coordinates and floors, native icons, colors and labels, groups/categories, filters, custom images, native file import/export, share codes or URLs, and saved-state storage. Mark each supported, unsupported, or unverified from its observed operation, including which transfer inputs a control accepts.

## Learn a native record with controlled edits

Use disposable markers in an isolated browser profile when possible. When inspecting the user's profile, back it up first and track the exact test objects for cleanup.

Create a simple point, then change one field at a time. Compare native exports and the active application state after changing coordinates, floor, title, notes, symbol, color, and group. A second point distinguishes collection framing from per-record encoding. Include Unicode and reserved URL characters when the actual input uses them. Test shared-coordinate markers on distinct floors when floors matter.

Keep appearance separate from identity. Generated IDs, timestamps, group memberships, and caches may change alongside an edit. Confirm a suspected field by editing it through the UI and observing the intended rendering; a similarly named field is not enough.

For coordinates, inspect a recognizable location at a known world coordinate and floor. Distinguish tile/world coordinates, cells or chunks, projected image pixels, and viewport coordinates. Confirm any axes, scale, tile-center rounding, origin offset, or floor transform from the target's implementation. Preserve fractional precision where the consumer supports it.

## Keep a task-local canonical collection

Use a lossless working record to separate the user's intent from a particular native schema. At minimum retain:

- Stable collection and marker identity, with ownership separated from native IDs.
- Geometry, coordinate reference, coordinates, and a known floor or explicit unknown.
- Name, description, semantic category, tags/groups, and requested appearance.
- Source and evidence type, plus native fields needed for a lossless round trip.

This is an internal contract, not a JSON format advertised as uploadable to PZmap. The adapter supplies the actual native representation. Validate finite numeric coordinates, meaningful identities, supported geometry, and text encoding. Reject malformed coordinates and preserve an unknown floor explicitly until it can be resolved or represented by the target.

Map evidence retains its limits: a static placement, possible spawn, source report, and observed object are different. Preserve these distinctions in descriptions or a companion reference even when the native marker format lacks structured fields.

## Choose the least invasive transfer

Prefer, in order, the working native importer, the deployment's share/export mechanisms, and an observed application API. Use a browser helper only when these do not meet the requested operation and its effects are understood.

For a share link, reuse the deployed encoder when accessible. Otherwise derive a codec from the verified implementation and independent examples. Validate field order, lengths, version framing, signed values, text encoding, compression wrapper, base encoding, checksums where present, and URL escaping. Verify collection framing as well as individual record fields.

Exercise an empty collection if supported, one point, multiple points, varied symbols, and the fields the request uses. Round-trip through the consumer's decoder, then through its importer. Check count, coordinates, floors, names, metadata, and styles against the source records. Confirm link length and browser/transport limits using the actual delivery path. Shorten or split with the user's understanding when necessary; retain a unified source and never truncate records silently.

On rejection, identify the failing boundary: URL parsing, decoding, schema validation, ingestion, persistence, or rendering. Correct that boundary before retrying the same case.

## Fallback adapters

Build a task-specific, auditable adapter for the observed API or store. Identify the authoritative store through the running application or an explicit user-provided export. Confirm the store's ownership and write path from that evidence before mutation.

A helper checks the exact authorized origin, active dataset, expected schema, and baseline before writing. It exposes a preview and backup, touches only the scoped marker collection, applies verified field mappings, and reports counts and failures. User text is written as text, not interpolated into executable HTML or JavaScript. Remote script loading, telemetry, unrelated storage enumeration, and secrets are outside this operation.

A browser console, bookmarklet, downloaded page, and mobile preview have different capabilities. Test the proposed launch path with browser security protections enabled. Label a temporary overlay as temporary; persistence requires a reload check.

When no supported mutation surface is accessible, provide the prepared collection, a human-readable coordinate/legend reference, and the minimal native example or browser action needed to continue. This preserves useful work without representing an untested transfer as complete.
