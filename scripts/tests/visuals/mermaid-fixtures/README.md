# Mermaid compatibility fixtures

`index.json` maps all 55 sources to the pinned renderer registry and upstream syntax documentation. They cover the 37 ordinary diagram families, error/frontmatter handlers, layout requests, author styling, long Unicode labels and invalid input. The adjacent `../verify_registry.cjs` checks registry coverage and detector dispatch without invoking diagram rendering. Generation and native qualification commands are documented in `../README.md`.

Use these sources in standalone reports when qualifying a renderer update. Inspect native output, layout, keyboard selection, theme changes, export and offline resource behavior. Check each layout request against the family that supports it. Supply embedded fonts, images and registered icon packs when the diagram uses them; keep exact source and useful failures recoverable.

`expectedState` records renderer completion; it is not a visual verdict. Four cases require their exact classified diagnostics. Five optional ELK layouts retain visible limitations for the shared cyclic topology, disclosed above the drawing and in export captions. Critical C4, Journey and Cynefin labels are also checked in the rendered SVG independently of source preservation.
