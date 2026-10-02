# Call numbers

How the library writes call numbers, and the order items stand on the shelves. Cataloguing keeps the export to this scheme; `catalog/catalog_tool.py check` flags anything that strays.

## Writing

A call number is a sequence of words separated by spaces or tabs. Case and spacing do not matter (`j 595.789  kir` is `J 595.789 KIR`); written out, it is in capitals with single spaces.

1. **Collection** (optional): `J` (children's), `YA` (young adult), `REF` (reference), or `OS` (oversize). Without one, the item is in the adult collection.
2. **Class**: a Dewey number, three digits with an optional decimal fraction (`641`, `641.5945`), or one of the word classes `B` (biography), `GN` (graphic novels), and `FIC` (fiction).
3. **Mark** (required): after a Dewey number, a Cutter: one to three letters, then any number of digits (`HAZ`, `S637`, `M4`). After a word class, a name (the author's, or for a biography the subject's): a letter, then letters, hyphens, and apostrophes (`O'BRIEN`, `SMITH-JONES`).
4. Then, in this order and each at most once, any of: a **year** from 1500 to 2099 (`2019`), a **volume** `V.` and a number from 1 to 999 without leading zeros (`V.3`), and a **copy** `C.` and a number written the same way (`C.2`).

## Shelf order

Items stand by collection first: adult, then children's, young adult, reference, and oversize. Within a collection, every Dewey number comes before the word classes, which follow in the order biography, graphic novels, fiction.

Dewey numbers stand in numeric order, the fraction read as a decimal: `641` < `641.502` < `641.59` < `641.5945` < `641.6`. Trailing zeros change nothing (`641.50` stands with `641.5`).

Within a class, items stand by mark. Cutters compare by their letters first (`S` < `S637` < `SM`), and Cutters with the same letters by their digits, read as a decimal fraction after the letters: `S6` < `S637` < `S64`, and no digits come first. Names compare letter by letter, ignoring hyphens and apostrophes: `O'BRIEN` stands between `OATES` and `OKAFOR`.

Then by year (no year first), volume (no volume first), and copy (no copy first), each in numeric order.

Call numbers that come out equal by these rules (`641.50 HAZ` and `641.5 HAZ`) stand together in no particular order.

## Sections

Shelf lists put a heading over each section: the collection's name (Adult, Children's, Young adult, Reference, Oversize), a middle dot, and the Dewey hundreds (`000s` to `900s`) or the word class's name (Biography, Graphic novels, Fiction): `Adult · 600s`, `Children's · Fiction`.

## Mistakes

`catalog/catalog_tool.py check` reports the first thing wrong with a call number, as one of these messages; a word a message quotes is in capitals, as the call number is read (`FIC smith extra` gives `unexpected 'EXTRA'`):

| Message | For example |
| --- | --- |
| `no call number` | an empty field |
| `no class after 'J'` | a collection and nothing else |
| `bad class number '64.5'` | a class starting with a digit that is not a Dewey number |
| `unknown class 'XYZ'` | any other class |
| `no cutter after '641.5'`, `no name after 'FIC'` | a class and nothing else |
| `bad cutter 'S6X'`, `bad name '0KEEFFE'` | a mark that does not fit its class |
| `unexpected 'V.1'` | a word after the mark that is not a year, volume, or copy in that order |
