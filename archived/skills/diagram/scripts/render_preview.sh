#!/usr/bin/env bash
# render_preview.sh <file.svg|file.html> [out.png]
# Rasterizes a visual so you can read the PNG and self-critique before
# delivering. Tries every available renderer in order of fidelity and falls
# through on failure — a present-but-broken renderer (e.g. ImageMagick
# without its rsvg delegate) must not block the next one.
#
# SVG inputs are pre-resolved through resolve_css_vars.py before any
# non-browser rasterizer: librsvg/ImageMagick don't implement CSS custom
# properties, so raw var()-styled token files rasterize as solid black
# (eval/failures/002-rsvg-css-variables). Chromium gets the original file.
set -uo pipefail

in="${1:?usage: render_preview.sh <file.svg|file.html> [out.png]}"
out="${2:-${in%.*}-preview.png}"
here="$(cd "$(dirname "$0")" && pwd)"

pre=""
trap '[ -n "$pre" ] && rm -f "$pre" 2>/dev/null' EXIT

ok() { [ -s "$out" ]; }

src="$in"
if [[ "$in" == *.svg ]] && command -v python3 >/dev/null 2>&1; then
  pre="$(mktemp /tmp/preview-XXXXXX.svg)"
  if python3 "$here/resolve_css_vars.py" "$in" "$pre" 2>/dev/null && [ -s "$pre" ]; then
    src="$pre"
  fi
fi

if [[ "$in" == *.svg ]]; then
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 1360 -b '#FCFCFA' "$src" -o "$out" 2>/dev/null && ok && { echo "$out"; exit 0; }
  fi
  if command -v inkscape >/dev/null 2>&1; then
    inkscape "$src" --export-type=png --export-width=1360 -o "$out" >/dev/null 2>&1 && ok && { echo "$out"; exit 0; }
  fi
  if command -v magick >/dev/null 2>&1; then
    magick -density 144 -background '#FCFCFA' "$src" "$out" 2>/dev/null && ok && { echo "$out"; exit 0; }
  fi
  if command -v convert >/dev/null 2>&1; then
    convert -density 144 -background '#FCFCFA' "$src" "$out" 2>/dev/null && ok && { echo "$out"; exit 0; }
  fi
fi

for b in chromium chromium-browser google-chrome google-chrome-stable msedge; do
  if command -v "$b" >/dev/null 2>&1; then
    "$b" --headless=new --disable-gpu --hide-scrollbars \
      --screenshot="$out" --window-size=1360,1600 \
      "file://$(realpath "$in")" >/dev/null 2>&1 && ok && { echo "$out"; exit 0; }
  fi
done

ok || rm -f "$out" 2>/dev/null
echo "no working renderer — install librsvg2-bin (lightweight), inkscape, or chromium; falling back to validate_svg.py only" >&2
exit 2

# Note: SVG rasterizers render the light-mode palette (the resolver bakes in
# the light values). To eyeball dark mode, open the file in a browser with
# the OS in dark mode, or screenshot via chromium with a dark theme.
