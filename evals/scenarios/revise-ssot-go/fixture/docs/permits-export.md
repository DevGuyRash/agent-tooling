# The permit system's export

Every night the permit system writes `permits.csv` to the parking services share: one row per live resident permit. It is comma-separated UTF-8 with a byte-order mark and a header row, with Windows line endings; columns may come in any order and values may have spaces around them.

| Column | Meaning |
| --- | --- |
| `permit_id` | `FV-` and a number |
| `address` | the address the permit is for |
| `vrm` | the vehicle's registration, in any case |
| `co2` | the vehicle's CO2 emissions in g/km, from its V5C; 0 for an electric vehicle |
| `fuel` | `petrol`, `diesel`, `hybrid`, or `electric`, in any case |
| `household_permit` | 1 for the address's first permit, 2 for its second, and so on |
| `expires` | the day the permit runs out, `YYYY-MM-DD`; it renews for a year from then |
