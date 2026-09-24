# Mermaid compatibility fixtures

`index.json` maps the sources to the pinned renderer registry and upstream syntax documentation. They cover ordinary diagram families, error/frontmatter handlers, layout requests, author styling, long Unicode labels and invalid input. The adjacent `../verify_registry.cjs` checks registry coverage and detector dispatch without invoking diagram rendering. Generation and native qualification commands are documented in `../README.md`.

Use these sources in standalone reports when qualifying a renderer update. Inspect native output, layout, keyboard selection, theme changes, export and offline resource behavior. Check each layout request against the family that supports it. Supply embedded fonts, images and registered icon packs when the diagram uses them; keep exact source and useful failures recoverable.

`expectedState` records renderer completion; it is not a visual verdict. Invalid source and incompatible family/layout requests require their exact classified diagnostics. Valid renderer regressions expect success. Numerical layout checks exercise group membership, overlap removal, unobstructed relationships, repeated links and label placement; native inspection separately establishes the rendered typography and controls. Critical C4, Journey and Cynefin labels are also checked in the rendered SVG independently of source preservation.
