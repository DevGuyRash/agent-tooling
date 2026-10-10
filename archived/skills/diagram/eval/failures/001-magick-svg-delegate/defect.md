# 001 — ImageMagick present, SVG delegate missing

Layer: 2 (render) — infrastructure failure, not an output failure.

Symptom: preflight reported "renderer: convert" but render_preview.sh exited 2 on a valid SVG; convert-im6 emitted "delegate failed 'rsvg-convert'".

Cause: ImageMagick 6 delegates SVG rasterization to rsvg-convert, which was absent in the runtime. Binary presence is not capability — exactly the second-runtime fracture the dual-runtime smoke test (verdict condition 2) exists to catch.

Fix shipped: preflight.sh now performs a functional render probe (rasterize a one-rect SVG end-to-end) instead of a presence check, and render_preview.sh tries every available renderer in order, falling through on failure instead of stopping at the first binary found.

Recurrence: 2026-06-10 (build container). Re-check in every new runtime via scripts/preflight.sh.
