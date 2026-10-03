# fringe-listings

The Harbour Fringe listings site: one page per event, named by its slug (`docs/slugs.md`), and an index in date order, built from the events file the programme team exports.

```
python3 -m listings build data/events-2026.csv site/
python3 -m listings slug "Late Night Comedy"
```

Standard library only, Python 3.11 or newer.

## Tests

```
python3 -m pytest
```

Every change to what the site prints comes with tests in `tests/` that pin it.
