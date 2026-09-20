# Mermaid compatibility fixtures

`index.json` maps sources to the pinned renderer registry and upstream syntax documentation. The registry-derived fixtures cover ordinary diagram families, error/frontmatter handlers, layout requests, author styling, long Unicode labels and invalid input. `mermaid-contract.cjs` checks registry coverage and detector dispatch without invoking diagram rendering.

Use these sources in standalone reports when qualifying a renderer update. Inspect native output, layout, keyboard selection, theme changes, export and offline resource behavior. Check each layout request against the family that supports it. Supply embedded fonts, images and registered icon packs when the diagram uses them; keep exact source and useful failures recoverable.
