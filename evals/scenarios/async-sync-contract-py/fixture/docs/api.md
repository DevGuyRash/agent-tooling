# shelftag API

shelftag 1.x keeps this API compatible: the systems listed at the end import it directly and upgrade on their own schedule.

## `label_text(item, *, width=32) -> str`

The text of one shelf label: lines separated by `\n`, no trailing newline.

```
Bio Bergkäse              the name, cut to `width` with "…"
CHF 4.90                  the price
CHF 2.45 / 100 g          the unit price, when net_grams is set: per 100 g, or per kg from 1000 g up
Herkunft: Schweiz         the origin, when set, cut to `width`
```

Unit prices are rounded to the Rappen, halves up. Raises `LabelError` (a `ValueError`) for a width under 16 or a negative price.

## `Item(name, price_rappen, net_grams=None, origin=None)`

A frozen dataclass. Prices are in Rappen: `490` is CHF 4.90.

## `LabelError`

Raised for labels that cannot be made.

## Who calls it

- **labeld**, the label printer service, renders each print batch in a pool of worker threads, one `label_text` call per label.
- **The web shop** (an aiohttp app) calls `label_text` inline in its product-page handler to show the label preview.
- **The POS sync**, a nightly cron script, sends every item's label text to the tills so their display matches the shelf.
- `python3 -m shelftag print`, this package's own command, for one-off printing in the back office.
