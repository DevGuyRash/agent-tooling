Design review of feature/overdue-notices

I'll go through the branch layer by layer.

Data and CLI: fine.

Fines (R7): the arithmetic is right. What I question is the shape: why does the fine need a base class, a decorator-based registry and a lookup by name when exactly one rule is ever used? Do we need the `--rounding` switch and its four modes, when R7 gives one rounding rule? Is `ToolCache` needed in a one-shot command? I don't think any of them earns its place; I'd remove all three.

Overdue list (R6, R8): R8 asks for equal-day loans in member-name order A to Z. `reverse=True` on the combined key gives Z to A. This needs fixing.

Notices (R10, R11): the footer total is computed as days times the daily rate rather than as the sum of the fines printed above it, so capped and discounted fines are not reflected in it. This needs fixing. The retry is as R11 describes.

Output (R9): matches, including the CSV header.
