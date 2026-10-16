# Review notes

## What is wrong

| What | Spec | Observed |
|---|---|---|
| Order of loans with equal days | R8: member name A-Z, then loan id | `reverse=True` makes both descending |
| Total at the foot of a notice | R10: sum of the listed fines | days * 50, so cap and discount are lost |

## What is extra

| What | Spec | Verdict |
|---|---|---|
| FineRule + registry | none | extra, remove |
| `--rounding` | R7 has one rule | extra, remove |
| ToolCache | none | extra, remove |

## What is required, so stays

| What | Spec | Verdict |
|---|---|---|
| Retry when a notice file is locked | R11 | required |
| `--format csv` | R9 | required |
