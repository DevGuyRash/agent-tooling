# normalize_name

`normalize_name(s)` turns a display name into a lookup key for the customer index:

- lowercase;
- collapse runs of whitespace to one space and trim both ends;
- fold accented Latin letters to their base letter ("José" and "Jose" must produce the same key), because customers type names both ways and duplicate records are the bug this function exists to prevent.

It runs once per signup, a few thousand times a day.
