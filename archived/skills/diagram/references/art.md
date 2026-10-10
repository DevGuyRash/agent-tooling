# Art and illustration — SVG

Decorative scenes, patterns, generative compositions. Same technical mechanics as every SVG (computed viewBox, background rect, no raster effects), but the aesthetic rules invert:

- Fill the canvas — art should feel rich, not sparse. Whitespace discipline is for diagrams.
- Freestyle color: art is exempt from the ramp system. Hardcode any palette. Physical scenes (sky, water, skin, materials) must NOT invert in dark mode — if you want a dark variant, write it explicitly inside `@media (prefers-color-scheme: dark)`; otherwise pick one palette and keep the background rect opaque.
- Depth via layered opaque shapes — later in source paints on top. Build back-to-front: sky, far ground, mid shapes, foreground.
- Organic forms with `<path>` curves, `<ellipse>`, `<circle>`; geometry with `<polygon>` and `<rect>`.
- Texture through repetition — parallel lines, dot fields, hatching — never filters, blur, or noise images.
- Radial symmetry via `<g transform="rotate(angle, cx, cy)">` around a copied motif; vary angle/scale slightly for organic feel.
- Gradients are permitted in art (the diagram restriction doesn't apply), but flat layered shapes usually age better — use gradients for skies and light, not as a substitute for composition.
- Keep individual paths simple; complexity comes from arrangement and repetition, not from any single virtuoso path.
- Still no text below 11px if the piece includes labels or a caption.
