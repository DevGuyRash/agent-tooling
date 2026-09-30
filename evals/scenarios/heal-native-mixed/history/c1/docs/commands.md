# Commands

Every command accepts `--catalog PATH` (default `~/.shelfmark.json`).

## add

`shelfmark add ISBN --title TITLE --author AUTHOR`

Adds a book. ISBN-10 and ISBN-13 are accepted with or without hyphens; ISBN-10 may end in an `X` check digit. Exits with status 2 on an invalid ISBN.

## list

`shelfmark list`

Prints one line per book: ISBN, title, and author.

## export

`shelfmark export [--fromat csv|json]`

Writes the whole catalogue to standard output. CSV (the default) has a header row; JSON is the same list of records the catalogue file holds.
