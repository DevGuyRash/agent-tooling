#!/usr/bin/env bash
# preflight.sh — capability check for the diagram skill (run once per session).
# Informational: always exits 0. Read the summary and apply the degradation
# ladder in SKILL.md for every [--] line. This is the runnable form of the
# dual-runtime smoke test: trigger/invocation and reference-file access are
# proven by the fact that this script is being run from the skill folder;
# everything else is checked below.
set -u

here="$(cd "$(dirname "$0")" && pwd)"
ok(){ printf '  [ok] %s\n' "$1"; }
no(){ printf '  [--] %s\n' "$1"; }

echo "diagram skill preflight"

# 1. python3 + stdlib → validate_svg.py (layers 1/3/4)
if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import re, sys, xml.etree.ElementTree' >/dev/null 2>&1; then
    ok "python3 + stdlib — validate_svg.py will run"
  else
    no "python3 present but stdlib import failed — validator unavailable; checklist-only verification"
  fi
else
  no "python3 missing — validator unavailable; checklist-only verification"
fi

# 2. renderer → render_preview.sh (layer 2 + visual critique)
# Functional probe through the REAL pipeline: a var()-styled rect, because
# every skill output uses CSS custom properties and non-browser rasterizers
# don't resolve them (eval/failures/002) — render_preview.sh pre-resolves
# via python3, so the probe needs python3 to be meaningful.
if command -v python3 >/dev/null 2>&1; then
  probe_svg="$(mktemp /tmp/preflight-XXXXXX.svg)"
  probe_png="${probe_svg%.svg}.png"
  printf '%s' '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><style>svg{--c:#E1F5EE}rect{fill:var(--c)}</style><rect width="40" height="40"/></svg>' > "$probe_svg"
  if bash "$here/render_preview.sh" "$probe_svg" "$probe_png" >/dev/null 2>&1 && [ -s "$probe_png" ]; then
    ok "renderer: verified — rendered a var()-styled probe through the real pipeline"
  else
    no "no working SVG renderer — visual pass unavailable; suggest librsvg2-bin; validator-only verification"
  fi
  rm -f "$probe_svg" "$probe_png" 2>/dev/null
else
  no "renderer probe skipped — python3 missing means CSS-variable pre-resolution is unavailable; token-styled previews unreliable"
fi

# HTML screenshots need chromium specifically
ch=""
for c in chromium chromium-browser google-chrome google-chrome-stable msedge; do
  command -v "$c" >/dev/null 2>&1 && { ch="$c"; break; }
done
if [ -n "$ch" ]; then
  ok "HTML preview: $ch available"
else
  no "HTML preview: no chromium — verify HTML by opening in a browser, or state the unverified-render caveat"
fi

# 3. network → CDN-backed HTML routes (Chart.js, D3 maps, mermaid, icons)
netok=""
if command -v curl >/dev/null 2>&1; then
  curl -sI --max-time 5 https://cdnjs.cloudflare.com >/dev/null 2>&1 && netok=1
elif command -v wget >/dev/null 2>&1; then
  wget -q --timeout=5 --spider https://cdnjs.cloudflare.com >/dev/null 2>&1 && netok=1
fi
if [ -n "$netok" ]; then
  ok "network: CDNs reachable — Chart.js / D3 / mermaid / icon routes available"
else
  no "network unavailable or blocked — offline routes only: SVG chart fallback; no maps, mermaid, or icons"
fi

# 4. opener → workflow step 6
o=""
for c in open xdg-open; do
  command -v "$c" >/dev/null 2>&1 && { o="$c"; break; }
done
if [ -z "$o" ] && command -v cmd.exe >/dev/null 2>&1; then o="cmd.exe /c start"; fi
if [ -n "$o" ]; then
  ok "opener: $o"
else
  no "no opener — deliver file paths instead of opening"
fi

# 5. writable output directory
if mkdir -p ./visuals 2>/dev/null && [ -w ./visuals ]; then
  ok "./visuals writable"
else
  no "cannot create ./visuals — pick another output directory and say so"
fi

echo "done — apply the degradation ladder in SKILL.md for any [--] line."
exit 0
