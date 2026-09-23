# Mermaid distribution notices

This is the full Mermaid 12.0.0 browser distribution with local layout compatibility patches. Its copyright and MIT permission notice are in LICENSE. The distribution retains its upstream bundled third-party notice block verbatim.

C4 uses the measured SVG rendering container width with the upstream fallback when no width is available. Ishikawa allocates branches from measured wrapped-label heights and leaves clearance between category groups. Venn measures connected name and note rows and places them within their semantic regions, preserving source, identities, values and circle geometry; unsuccessful placement retains an actionable diagnostic.

The original distribution SHA-256 is 28fca7ae6ebc7ed7bb63bde63136a74bfef14f296a57e403657eeb8b32836073. The local artifact SHA-256 is 5d0da1e481c6c29902b4dcb4dad8e6e641decf3486a4609e904a404b0154170a. The repository maintenance command scripts/patch_mermaid_vendor.py applies exact reversible replacements from scripts/mermaid-vendor-patches.json; the Venn implementation is maintained in scripts/mermaid-patches/venn-labels.js. Normal report builds and assembly use the packaged artifact without fetching or patching it.

The bundled ELK JavaScript distribution is elkjs 0.9.3, licensed under EPL-2.0. Its license is included in licenses/elkjs-EPL-2.0.txt. Corresponding publicly available source and distribution are at https://github.com/kieler/elkjs and https://registry.npmjs.org/elkjs/-/elkjs-0.9.3.tgz; the upstream Eclipse Layout Kernel source is at https://github.com/eclipse/elk. The bundled elkjs code is unmodified.

The bundled DOMPurify 3.4.12 is offered under MPL-2.0 OR Apache-2.0. Its upstream license statement and MPL-2.0 text are retained in licenses/DOMPurify-LICENSE.txt and licenses/DOMPurify-MPL-2.0.txt. Corresponding source is at https://github.com/cure53/DOMPurify/tree/3.4.12 and https://registry.npmjs.org/dompurify/-/dompurify-3.4.12.tgz. This distribution uses the MPL-2.0 option.

The standalone assembler carries these notices and the Mermaid license into reports that include the renderer. The embedded runtime retains the additional upstream attributions bundled with it.
