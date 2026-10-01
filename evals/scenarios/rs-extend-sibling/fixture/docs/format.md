# Tournament files (`.trn`)

One file per tournament, UTF-8 text, one statement per line. Blank lines and lines starting with `#` are ignored, leading and trailing spaces do not matter, and fields are separated by one or more spaces. `crates/trn` parses and checks these files, and `td check FILE` reports the first problem with its line number.

| Statement | Meaning |
| --- | --- |
| `event NAME` | The tournament's name: the rest of the line. Once, before round 1. |
| `rounds N` | The number of rounds planned. Once, before round 1. |
| `player NO RATING NAME` | A player: start number `NO` (from 1, each once, in any order), rating (`0` for unrated, otherwise 100 to 3000), and name (the rest of the line, usually `Surname, Given`; a run of spaces in it counts as one). All players come before round 1. |
| `round N` | Starts round `N`. Rounds come in order 1, 2, 3, ..., up to the number planned. |
| `WHITE BLACK RESULT` | A game in the current round between start numbers `WHITE` and `BLACK`. |
| `bye NO KIND` | Player `NO` is not paired in the current round. `KIND` is `full` (1 point), `half` (half a point), or `zero` (no points; also used for an absence or a withdrawal). |

Results:

| Result | Meaning |
| --- | --- |
| `1-0` | White won. |
| `0-1` | Black won. |
| `1/2` | Draw. |
| `+-` | White won by forfeit: Black did not play. |
| `-+` | Black won by forfeit: White did not play. |
| `--` | Neither player played (double forfeit). |
| `*` | Not played yet. |

Every player appears exactly once in every round, in a game or in a `bye` line, so a player who withdraws gets `bye NO zero` in each later round. A round is finished when none of its games is `*`; a postponed game stays `*` until it is played, even if later rounds are already under way.

```
# Rookhaven Chess Club
event Spring Rapid 2026
rounds 5

player 1 2105 Lindqvist, Mia
player 2 1987 Okafor, Chidi
player 3 1940 Brandt, Oskar
player 4 0 Price, Nora

round 1
1 3 1-0
2 4 1/2

round 2
4 1 *
bye 2 half
bye 3 zero
```
