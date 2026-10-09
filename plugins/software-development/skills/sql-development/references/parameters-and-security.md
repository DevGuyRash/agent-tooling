# SQL Parameters and Security

Load this reference for embedded SQL, query builders, dynamic identifiers, stored code, privileges, tenant boundaries, secrets, or sensitive data.

## Separate Data from SQL Structure

- Pass untrusted data through the repository driver's bind or prepared-statement API.
- Do not build values into SQL with interpolation, concatenation, manual escaping, or generic string quoting.
- Match placeholder style, binding order/names, and driver type conversion to the detected adapter.
- Bind the intended database type when overloaded operators, implicit casts, collation, precision, or index selection can change with parameter inference; inspect the sent type rather than assuming a host-language annotation controls it.
- Remember that parameters usually cannot represent identifiers, keywords, operators, sort direction, or arbitrary clauses.
- Map structural choices from a closed allowlist, then use the dialect's identifier-quoting facility where identifiers remain dynamic.
- Treat stored-procedure or server-side dynamic SQL with the same separation rules.

## Preserve Authorization Boundaries

- Parameterization prevents a class of injection; it does not establish who may see or change a row.
- Apply authorization and tenant scope at every relevant read and write boundary using the repository's established model.
- Treat row-level security, views, roles, definer/invoker rights, search paths, and ownership as vendor-specific security behavior.
- Use least-privileged runtime roles and separate migration/administration authority where the deployment supports it.
- Avoid granting broad privileges to compensate for one migration or query failure.

## Handle Sensitive Data

- Keep credentials and connection strings out of source, fixtures, command lines, generated SQL, and logs.
- Redact bind values or query text when they can contain secrets or personal data.
- Build local fixtures from synthetic or privacy-preserving data rather than raw production copies.
- Consider whether errors, constraint names, row counts, timing, or existence checks reveal unauthorized information.

## Verify

- Test representative hostile values, including quotes, comment markers, delimiters, Unicode, and empty input, through the actual driver.
- Test structural allowlists separately from value binding.
- Verify tenant/authorization behavior with allowed and denied principals, not only malformed input.
- Inspect the effective database role and connection behavior in the test environment.

For an example of a value-binding API and its separation from identifier escaping, see PostgreSQL [`PQexecParams`](https://www.postgresql.org/docs/current/libpq-exec.html).
