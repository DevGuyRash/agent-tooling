# repo-summary

A summary of a repository's history for the monthly engineering report. The report job runs it in each service's checkout and pastes the output into the report, and the report's parser reads it, so the format below is exact.

    repo-summary [-n N] [DIR]

DIR is the repository (default: the current directory). `-n` is how many entries to list under "top authors" and "top files" (default 5).

Example:

```
commits: 128
authors: 4
first: 2025-11-03
last: 2026-09-14
top authors:
    61  Ana Lima
    40  Ben Okafor
    20  Chen Wei
     7  Dana Kim
top files:
    52  src/main.rs
    31  Cargo.toml
    18  README.md
    11  src/config.rs
     9  docs/ops.md
```

- **commits**: every commit reachable from HEAD.
- **authors**: how many different author names those commits have. An author is identified by name only, so one person committing from two email addresses counts once. It is the author, not the committer, that counts.
- **first** and **last**: the earliest and the latest author date among those commits, as YYYY-MM-DD.
- **top authors**: author names by number of commits, most first.
- **top files**: paths by the number of commits that added, changed, or deleted them, most first. The first commit counts for every file it adds.
- In both lists, equal counts are listed in byte order of the name (so `Zoe` comes before `adam`), and each entry is printed with `devtools::count_line`. With `-n 0` the headings are printed with no entries.
- If DIR is not a git repository, print an error on stderr and exit with status 1, with nothing on stdout. Bad usage exits with status 2.
