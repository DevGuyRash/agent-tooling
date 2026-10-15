# stallbook

The weekly sales book for our market stall. Sales are logged in `data/sales.csv`; `stallbook report` totals one week per item.

```
python3 -m stallbook --data data report --week 2026-W14
```

- `--format` chooses the output; `text` is the only format so far.
- `data/stallbook.ini` holds the settings (`[report]`: `currency`, `title`).
- `docs/` has the specs and the rough roadmap.

Run `make check` before handing work back: it runs the tests and byte-compiles the package. Python 3.10 or newer, standard library only.
