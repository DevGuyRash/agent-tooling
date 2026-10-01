# td standings

Requested by Mia Lindqvist (arbiter), for the winter league. Between rounds I need the standings with the tiebreaks we announce in the league rules, straight from the tournament file on the laptop at the board, and I need to be able to look back at the standings after an earlier round when a result is disputed.

## Usage

```
td standings [--after-round N] [--tiebreaks LIST] FILE
```

Options may come before or after `FILE`, each at most once.

- `--after-round N`: the standings after round `N`, a whole number from 1 up. Rounds 1 to `N` are counted, and all of them must be finished (no `*` games). Without the option, `N` is the largest number for which rounds 1 to `N` are all in the file and finished; a postponed game in round 3 keeps the default at round 2 even when round 4 is complete.
- `--tiebreaks LIST`: which tiebreaks to apply, in order: `none`, or one or more of `bh1`, `bh`, `sb`, `wins` separated by commas (no spaces), each at most once. The default is `bh1,bh,sb,wins`.

## What counts

Only rounds 1 to `N` count, for every number below: a player's points, and the points of the opponents that the tiebreaks use, are all the points after round `N`.

Points for one round:

| In the round | Points |
| --- | --- |
| won (`1-0` as White, `0-1` as Black) | 1 |
| won by forfeit (`+-` as White, `-+` as Black) | 1 |
| drew (`1/2`) | 1/2 |
| lost, lost by forfeit, or double forfeit (`--`) | 0 |
| `bye full` | 1 |
| `bye half` | 1/2 |
| `bye zero` | 0 |

A game is played over the board when its result is `1-0`, `0-1`, or `1/2`. Forfeits, double forfeits, and byes are not.

Tiebreaks:

- `bh`, Buchholz: one contribution per counted round, added up. For a round in which the player played over the board, the contribution is that opponent's points; for any other round (a bye of any kind, a forfeit won or lost, a double forfeit), it is the player's own points.
- `bh1`, Buchholz Cut 1: Buchholz minus the smallest of its contributions.
- `sb`, Sonneborn-Berger: for each game the player won over the board, the opponent's points; for each game drawn, half the opponent's points. Losses, forfeits, and byes add nothing.
- `wins`: the number of games won over the board. Forfeit wins and byes do not count.

## Order and places

Players are ordered by points, higher first, then by each tiebreak in the order given, higher first. Players equal on points and on every tiebreak in the list share a place, written `first-last` (for example `7-8`), and among them the lower start number comes first. With `--tiebreaks none`, equal points share a place. Players who withdrew or were absent are listed like everyone else.

## Output

The first line is `EVENT - standings after round N of PLANNED`, where `EVENT` is the event name and `PLANNED` the number of rounds planned; then an empty line; then a table with the columns `Place`, `No` (start number), `Name`, `Rating`, `Pts`, and one column per tiebreak, in the order given, headed `BH1`, `BH`, `SB`, and `Wins`.

The table is laid out the way `td players` lays out its table: columns separated by two spaces, each column as wide as its widest entry (header included, counting characters), `Name` left-aligned and every other column right-aligned, headers aligned like their column, and no spaces at the end of a line. Rating is `-` for an unrated player. Points and tiebreak values are written in their shortest decimal form: `0`, `3`, `3.5`, `8.25`.

`td standings tournaments/spring-rapid-2026.trn` prints:

```
Spring Rapid 2026 - standings after round 5 of 5

Place  No  Name            Rating  Pts   BH1    BH     SB  Wins
    1   1  Lindqvist, Mia    2105    4  11.5    13  10.25     3
    2   2  Okafor, Chidi     1987  3.5  11.5    13   7.75     3
    3   8  Price, Nora          -    3    12  13.5   5.25     0
    4   6  Fenwick, Sam      1710  2.5  13.5  14.5   4.75     1
    5   5  Moreau, Élise     1795  2.5    12    13      5     1
    6   4  Šimić, Luka       1862  2.5  11.5    13    5.5     1
    7   3  Brandt, Oskar     1940  1.5    13    14    2.5     1
    8   7  Haddad, Rami      1650    1   7.5   8.5      0     0
```

`td standings --after-round 2 --tiebreaks sb,wins tournaments/spring-rapid-2026.trn` prints:

```
Spring Rapid 2026 - standings after round 2 of 5

Place  No  Name            Rating  Pts    SB  Wins
    1   1  Lindqvist, Mia    2105    2   1.5     2
    2   2  Okafor, Chidi     1987  1.5     1     1
    3   3  Brandt, Oskar     1940    1     1     1
    4   6  Fenwick, Sam      1710    1  0.75     0
    5   8  Price, Nora          -    1   0.5     0
    6   7  Haddad, Rami      1650    1     0     0
  7-8   4  Šimić, Luka       1862  0.5   0.5     0
  7-8   5  Moreau, Élise     1795  0.5   0.5     0
```

## Errors

Like td's other commands: a message on standard error starting with `td: `, nothing on standard output, and

- exit status 2 for a usage error: an unknown option, an option without its value or given twice, an `--after-round` value that is not a whole number from 1 up, a `--tiebreaks` list with an unknown or repeated name (or `none` together with other names), or not exactly one `FILE`;
- exit status 1 when the file cannot be read or is not a valid tournament file (the same messages as `td check`); when `--after-round N` names a round beyond the last round in the file (`td: FILE: round N has not been paired`, whatever the earlier rounds hold); when, otherwise, a round from 1 to `N` is not finished (`td: FILE: round K is not finished`, for the first such round `K`); and when there is no finished round to show without `--after-round` (`td: FILE: no finished rounds`).
