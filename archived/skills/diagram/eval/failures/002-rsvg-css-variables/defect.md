# 002 — librsvg doesn't resolve CSS custom properties; token SVGs preview black

Layer: 2 (render), corrupting the layer-5/6 critique downstream. Latent in the reviewed artifact — every SVG this skill produces is affected, not one prompt family.

Symptom: a validator-clean, browser-correct SVG rasterizes as a solid black canvas via rsvg-convert. An agent following the verification loop would then "repair" a correct file based on a lying preview.

Evidence (rsvg-convert 2.58.0, Ubuntu 24): identical 40×40 rect filled `#1D9E75` directly → srgb(29,158,117); filled via `var(--c)` with the same value → srgb(0,0,0). Fixture center pixel srgb(0,0,0); see evidence-black.png (raw rsvg render of output.svg).

Cause: librsvg (and ImageMagick's SVG path) don't implement CSS custom properties. An unresolved var() invalidates the declaration; fill computes to its initial value — black. Browsers resolve the variables, so delivered files always looked right, masking the broken preview path.

Fix shipped: scripts/resolve_css_vars.py substitutes light-mode values (custom-property definitions outside any @media block) into a temp copy; render_preview.sh feeds that copy to every non-browser rasterizer (chromium still gets the original); preflight.sh probes with a var()-styled rect through the real pipeline so the capability report can't false-positive.

Recurrence: 2026-06-11 (build container). Applies to any runtime whose preview path is rsvg/inkscape/magick rather than a real browser.
