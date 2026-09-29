# shelfmark

Catalogue a home library from the command line.

```sh
shelfmark add 0-8044-2957-X --title "The Dispossessed" --author "Ursula K. Le Guin"
shelfmark list
shelfmark export --format json > books.json
```

The catalogue lives in `~/.shelfmark.json` unless you pass `--catalog PATH`.

## Development

```sh
git config core.hooksPath .githooks
make check
```
