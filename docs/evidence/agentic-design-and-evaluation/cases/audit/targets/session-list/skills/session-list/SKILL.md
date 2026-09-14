---
name: session-list
description: Generate a participant-facing workshop list from event JSON, excluding cancelled events.
compatibility: Python 3 standard library.
---

# Session List

Create a participant-facing workshop list from the supplied event JSON. The adopted contract requires excluding cancelled events, retaining each confirmed event's title and date, and using the packaged label settings. Run `python3 <skills-file-root>/scripts/list_events.py INPUT_JSON OUTPUT_TXT`; both paths are supplied by the user. The command supports an unrelated caller working directory. Only the selected output file may be written. This skill adopts the portable Agent Skills format. It does not publish messages.
