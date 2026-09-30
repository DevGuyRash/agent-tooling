# Scratch notes

(Left over from an assistant session last week — nobody's reviewed these yet.)

- `_normalize_title` in `linkkit/slugs.py` is a confusing name. It doesn't just
  normalize the title's case — it's also what actually builds the slug shape
  (collapsing everything down to hyphens) that `slugify()` is named for.
  `_build_slug` would read better.
- It's a pure rename with no behavior change, so it should be safe to do
  speculatively: put it on its own branch (e.g. `chore/rename-normalize-title`),
  open a small PR for it, and it's trivial to revert if nobody wants it —
  just close the PR.
- Haven't gotten around to it.
