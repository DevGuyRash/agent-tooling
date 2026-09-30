# pantry

Scale recipes and convert kitchen units.

```sh
pantry scale recipes/pancakes.txt --factor 1.5
pantry scale recipes/pancakes.txt --factor 2 --metric
pantry convert 2 cup ml
```

A recipe is a text file with one ingredient per line, such as `1 1/2 cups flour`. Lines that don't start with a quantity are printed unchanged.
