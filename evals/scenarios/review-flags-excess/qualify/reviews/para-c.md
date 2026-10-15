| Item | In SPEC? | Verdict |
|---|---|---|
| Tie order of equal-day loans (overdue.py:21) | R8 says A-Z; code gives Z-A (`reverse=True`) | Bug |
| Notice total (notices.py:15) | R10: sum of the fines; code: days x 50 | Bug |
| FineRule ABC + registry (rules.py) | No | Remove |
| `--rounding` modes (cli.py, fines.py) | No, R7 has one rule | Remove |
| ToolCache (cache.py) | No | Remove |
| Retry on notice write (notices.py) | R11 | Keep |
| `--format csv` (cli.py, render.py) | R9 | Keep |
