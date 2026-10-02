# Pursuit races

The winter series is sailed as pursuit races: every class starts at its own time, slowest class first, so that if every boat sailed exactly to its handicap they would all reach the finish line together. Whoever is in front when the time is up wins, so there is nothing to calculate afterwards; what I need from startline is the start times, to read out at the briefing and to run the start line from.

```
startline pursuit [--minutes N] FILE
```

FILE is a race file (docs/race-file.md). Only its `race` and `start` lines and its boats are used; finish times, if any, are ignored, so the entry list I write up the evening before works as it is.

N is how long the slowest class should take to sail the course, in whole minutes, from 1 to 600. Without `--minutes` it's 60.

Handicaps are the club's Portsmouth Numbers, the same ones results uses. The slowest class is the entered class with the highest number; it starts at the race file's start time. Every other class starts

    N × 60 × (slowest PN − class PN) / slowest PN

seconds after that, rounded to the nearest second (halves round up).

It prints a title line and a table laid out like the results table: columns two spaces apart, numbers right-aligned. One row per entered class, in start order (classes starting at the same second in alphabetical order); `boats` is how many boats of that class are entered. For docs/pursuit-example.race:

```
$ startline pursuit docs/pursuit-example.race
Winter Pursuit 1: 60 minutes for Optimist (PN 1642)
start     class       PN  boats
10:30:00  Optimist  1642      2
10:39:21  Mirror    1386      1
10:40:10  Topper    1364      3
10:48:05  ILCA 6    1147      2
10:48:16  Solo      1142      1
10:49:48  ILCA 7    1100      1
10:55:35  RS400      942      1
```

and with `--minutes 45`:

```
$ startline pursuit --minutes 45 docs/pursuit-example.race
Winter Pursuit 1: 45 minutes for Optimist (PN 1642)
start     class       PN  boats
10:30:00  Optimist  1642      2
10:37:01  Mirror    1386      1
10:37:37  Topper    1364      3
10:43:34  ILCA 6    1147      2
10:43:42  Solo      1142      1
10:44:51  ILCA 7    1100      1
10:49:11  RS400      942      1
```

Errors, on standard error like results gives them:

- a race file that can't be read or has a mistake in it: `startline: ` and the same message results gives, exit status 1;
- a boat whose class has no Portsmouth Number: `startline: line 7: no Portsmouth Number for class "Laser"` (with the boat's line), exit status 1;
- a file with no boats: `startline: no boats entered`, exit status 1;
- no FILE, a second FILE, an unknown option, or an `--minutes` value that isn't a whole number from 1 to 600: a usage error, exit status 2.

Priya (race officer, winter series)
