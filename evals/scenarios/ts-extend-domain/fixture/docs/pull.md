# shelfwise pull

The morning pull list: the holds a branch's pages need to fetch from the shelves, in the order they walk the stacks.

```
shelfwise pull --branch NAME HOLDS.csv
```

It reads the holds export (the same file `shelfwise holds` reads) and takes the holds of branch NAME (exactly as written in the export) whose status is `waiting`. Other branches and other statuses are left out.

## Output

```
Pull list for Eastside: 5 holds

Adult · 600s
  641.5945 HAZ 2019  The essentials of classic Italian cooking  #2231
  641.6 MCG          On food and cooking  #2245

Adult · Fiction
  FIC O'BRIEN        The country girls  #2250

Children's · 500s
  J 595.789 KIR      Butterflies of the world  #2236

Not pulled, call number needs fixing:
  #2240  "64.5 ABC": bad class number '64.5'
```

The first line is `Pull list for NAME: N holds` (`1 hold` for one), counting every waiting hold of the branch, the ones with a bad call number included.

The holds with a good call number follow in shelf order (docs/callnumbers.md), holds whose call numbers come out equal in order of hold id. A heading line names each section (docs/callnumbers.md, Sections), with an empty line before it. Each hold is two spaces, its call number written out (capitals, single spaces), padded with spaces to the length of the longest written-out call number in the list, two spaces, the title, two spaces, and `#` and the hold id.

Holds whose call number does not follow the scheme come last, after an empty line and the line `Not pulled, call number needs fixing:`, in order of hold id: two spaces, `#` and the hold id, two spaces, the call number exactly as the export has it in double quotes, a colon, a space, and the first thing wrong with it, worded as in docs/callnumbers.md, Mistakes.

With no waiting holds for the branch, the first line (`Pull list for NAME: 0 holds`) is all there is.

## Exit status

0, or 1 when any hold is listed under "Not pulled". Usage errors and an export that cannot be read or does not parse are reported on standard error the way `shelfwise holds` reports them, with exit status 2.
