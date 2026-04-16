# Power Query

This skill treats Power Query as a first-class workbook surface.

Owned artifacts:

- query source files under `power_query/queries/*.pq`
- query metadata in `power_query/queries.json`
- safe workbook connection metadata in `power_query/connections.json`
- model-load metadata in `power_query/model.json`
- explicit refresh defaults and refreshable connection metadata in `power_query/refresh.json`

Behavior:

- `pull` exports workbook query definitions and safe metadata to repo artifacts.
- `push` applies query definitions and safe connection refresh flags without managing credentials.
- `refresh` explicitly refreshes Mashup-backed workbook connections and reports per-connection results.
- `roundtrip` syncs Power Query artifacts in both directions but does not auto-refresh.
- `plan` and per-surface `compare` can include `pq`, `connections`, and `model`
  in the package path so callers can see capability and drift without invoking
  COM mutation.
- Package-backed `sync` currently treats `pq`, `connections`, and `model` as
  unsupported write surfaces and reports them as plan or compare only.

Credential boundary:

- credentials, privacy settings, prompts, and provider auth are preserved in Excel
- repo artifacts do not store secrets

File format:

- `.pq` is the canonical export format
- `.m` is accepted on import as a compatibility alias when a referenced `.pq` file is absent
