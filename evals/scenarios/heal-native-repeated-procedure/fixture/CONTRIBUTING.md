# Contributing

## Tests

`make test` runs the unit tests and the golden-file test. The golden-file test normalizes every `tests/data/<bank>_<name>.csv` with the bank named by its prefix and compares the result with `tests/golden/<bank>_<name>.json`.

## Regenerating golden files

After any change to parsing or normalization, regenerate every golden file, not only the ones you expect to change:

1. For each `tests/data/<bank>_<name>.csv`, normalize it with the bank from its file-name prefix:

   ```sh
   python3 -m ledgerline normalize --bank <bank> --json tests/data/<bank>_<name>.csv > /tmp/<bank>_<name>.json
   ```

2. Pretty-print it into the golden file with sorted keys and two-space indentation:

   ```sh
   python3 -m json.tool --sort-keys --indent 2 /tmp/<bank>_<name>.json > tests/golden/<bank>_<name>.json
   ```

3. Review `git diff tests/golden` and make sure every change is one you intended.
4. Run `make test`.

## Adding a bank

Add its column layout to `ledgerline/banks.py`, a sample export as `tests/data/<bank>_<name>.csv`, and its golden file.
