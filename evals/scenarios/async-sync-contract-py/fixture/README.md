# shelftag

Shelf-label text for the Marktgasse co-op's three stores in Basel. shelftag turns an item (name, price, net weight, origin) into the few lines printed on its shelf label. It is a library first: the label printer service, the web shop, and the POS sync import it (see [docs/api.md](docs/api.md) for the stable API and who calls it), and it has a small command of its own for one-off printing.

Standard library only: the store machines and the printer service run stock Python 3.10 or newer, with nothing installed beside it.

## Use

```bash
python3 -m shelftag print ITEMS.csv [--width N]   # every item's label, a blank line between labels
python3 -m shelftag preview NAME PRICE             # one label, for a quick look
```

`ITEMS.csv` has the columns `name,price,net_grams,origin`, with the price in francs (`4.90`) and the last two optional; `tests/data/items.csv` is an example.

```python
from shelftag import Item, label_text

print(label_text(Item("Bio Bergkäse", 490, net_grams=200, origin="Schweiz")))
```

## Layout

- `shelftag/label.py`: `Item`, `label_text`, `LabelError`.
- `shelftag/money.py`: Rappen formatting, parsing, and rounding.
- `shelftag/cli.py`: the command.
- `docs/api.md`: the API other systems rely on. `docs/fxd.md`: the store machines' exchange-rate daemon.

## Tests

```bash
python3 -m unittest
```

Releases are tagged from `main`; see [CHANGELOG.md](CHANGELOG.md).
