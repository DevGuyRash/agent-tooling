# Tokens — color, typography, and the embeddable stylesheet

This file is the default token instance. Forks override the ramp table and hex values for a brand or domain; the class system, stop-selection rules, and stylesheet structure stay unchanged — they are part of the invariant method.

Read this before producing any output. Every file embeds the relevant stylesheet block below so class names (`t`, `ts`, `th`, `box`, `arr`, `leader`, `c-{ramp}`) work identically across outputs and adapt to dark mode automatically via `prefers-color-scheme`.

## Color ramps — 9 families × 7 stops

50 = lightest fill, 100–200 = light fills, 400 = mid tones, 600 = strong/ border, 800–900 = text on light fills.

| Ramp   | 50      | 100     | 200     | 400     | 600     | 800     | 900     |
| ------ | ------- | ------- | ------- | ------- | ------- | ------- | ------- |
| purple | #EEEDFE | #CECBF6 | #AFA9EC | #7F77DD | #534AB7 | #3C3489 | #26215C |
| teal   | #E1F5EE | #9FE1CB | #5DCAA5 | #1D9E75 | #0F6E56 | #085041 | #04342C |
| coral  | #FAECE7 | #F5C4B3 | #F0997B | #D85A30 | #993C1D | #712B13 | #4A1B0C |
| pink   | #FBEAF0 | #F4C0D1 | #ED93B1 | #D4537E | #993556 | #72243E | #4B1528 |
| gray   | #F1EFE8 | #D3D1C7 | #B4B2A9 | #888780 | #5F5E5A | #444441 | #2C2C2A |
| blue   | #E6F1FB | #B5D4F4 | #85B7EB | #378ADD | #185FA5 | #0C447C | #042C53 |
| green  | #EAF3DE | #C0DD97 | #97C459 | #639922 | #3B6D11 | #27500A | #173404 |
| amber  | #FAEEDA | #FAC775 | #EF9F27 | #BA7517 | #854F0B | #633806 | #412402 |
| red    | #FCEBEB | #F7C1C1 | #F09595 | #E24B4A | #A32D2D | #791F1F | #501313 |

Stop selection:

- Light mode: 50 fill + 600 stroke + 800 title / 600 subtitle.
- Dark mode: 800 fill + 200 stroke + 100 title / 200 subtitle.
- Title and subtitle must be two different stops — same stop reads flat.
- Colored connector strokes: any 400-level hex works in both modes.

Assignment philosophy:

- Group by category — all nodes of one type share one ramp (immune cells = purple, pathogens = coral, outcomes = teal).
- Gray for neutral/structural nodes (start, end, generic steps).
- Prefer purple, teal, coral, pink for general categories. Reserve blue, green, amber, red for genuinely informational/success/warning/error meaning — they carry UI connotations. Exception: illustrative diagrams use blue/ amber/red freely for physical properties (cold, heat, pressure).
- Illustrative diagrams: color encodes intensity, not category — warm ramps = heat/energy/active/attended, cool or gray = cold/dormant/ignored.
- Physical-color scenes (sky, water, skin, materials): all hardcoded hex, no theme classes — the scene must not invert in dark mode. Provide an explicit dark variant via the media query only if wanted.

## Embeddable SVG stylesheet

Place this `<style>` as the first child of the root `<svg>` (after `<title>`/`<desc>`). It defines the full class system with automatic dark mode. Most browsers and editors honor `<style>` in standalone SVG; for strict image pipelines that strip it, fall back to inline fill/stroke attributes using the table above.

```svg
<style>
svg{
--bg:#FCFCFA;--p:#2C2C2A;--s:#5F5E5A;--t:#888780;--bg2:#F1EFE8;--b:#D3D1C7;
--purple-f:#EEEDFE;--purple-s:#534AB7;--purple-t:#26215C;--purple-sub:#534AB7;
--teal-f:#E1F5EE;--teal-s:#0F6E56;--teal-t:#04342C;--teal-sub:#0F6E56;
--coral-f:#FAECE7;--coral-s:#993C1D;--coral-t:#4A1B0C;--coral-sub:#993C1D;
--pink-f:#FBEAF0;--pink-s:#993556;--pink-t:#4B1528;--pink-sub:#993556;
--gray-f:#F1EFE8;--gray-s:#5F5E5A;--gray-t:#2C2C2A;--gray-sub:#5F5E5A;
--blue-f:#E6F1FB;--blue-s:#185FA5;--blue-t:#042C53;--blue-sub:#185FA5;
--green-f:#EAF3DE;--green-s:#3B6D11;--green-t:#173404;--green-sub:#3B6D11;
--amber-f:#FAEEDA;--amber-s:#854F0B;--amber-t:#412402;--amber-sub:#854F0B;
--red-f:#FCEBEB;--red-s:#A32D2D;--red-t:#501313;--red-sub:#A32D2D;
}
@media (prefers-color-scheme: dark){svg{
--bg:#1A1A18;--p:#EDEDEA;--s:#B4B2A9;--t:#888780;--bg2:#2C2C2A;--b:#444441;
--purple-f:#3C3489;--purple-s:#AFA9EC;--purple-t:#CECBF6;--purple-sub:#AFA9EC;
--teal-f:#085041;--teal-s:#5DCAA5;--teal-t:#9FE1CB;--teal-sub:#5DCAA5;
--coral-f:#712B13;--coral-s:#F0997B;--coral-t:#F5C4B3;--coral-sub:#F0997B;
--pink-f:#72243E;--pink-s:#ED93B1;--pink-t:#F4C0D1;--pink-sub:#ED93B1;
--gray-f:#444441;--gray-s:#B4B2A9;--gray-t:#F1EFE8;--gray-sub:#B4B2A9;
--blue-f:#0C447C;--blue-s:#85B7EB;--blue-t:#B5D4F4;--blue-sub:#85B7EB;
--green-f:#27500A;--green-s:#97C459;--green-t:#C0DD97;--green-sub:#97C459;
--amber-f:#633806;--amber-s:#EF9F27;--amber-t:#FAC775;--amber-sub:#EF9F27;
--red-f:#791F1F;--red-s:#F09595;--red-t:#F7C1C1;--red-sub:#F09595;
}}
text{font-family:Inter,system-ui,sans-serif;fill:var(--p)}
.t{font-size:14px}.ts{font-size:12px;fill:var(--s)}.th{font-size:14px;font-weight:500}
.box{fill:var(--bg2);stroke:var(--b);stroke-width:0.5}
.arr{stroke:var(--s);stroke-width:1.5;fill:none}
.leader{stroke:var(--t);stroke-width:0.5;stroke-dasharray:3 3;fill:none}
.c-purple>rect,.c-purple>circle,.c-purple>ellipse{fill:var(--purple-f);stroke:var(--purple-s)}
.c-purple .th,.c-purple .t{fill:var(--purple-t)}.c-purple .ts{fill:var(--purple-sub)}
.c-teal>rect,.c-teal>circle,.c-teal>ellipse{fill:var(--teal-f);stroke:var(--teal-s)}
.c-teal .th,.c-teal .t{fill:var(--teal-t)}.c-teal .ts{fill:var(--teal-sub)}
.c-coral>rect,.c-coral>circle,.c-coral>ellipse{fill:var(--coral-f);stroke:var(--coral-s)}
.c-coral .th,.c-coral .t{fill:var(--coral-t)}.c-coral .ts{fill:var(--coral-sub)}
.c-pink>rect,.c-pink>circle,.c-pink>ellipse{fill:var(--pink-f);stroke:var(--pink-s)}
.c-pink .th,.c-pink .t{fill:var(--pink-t)}.c-pink .ts{fill:var(--pink-sub)}
.c-gray>rect,.c-gray>circle,.c-gray>ellipse{fill:var(--gray-f);stroke:var(--gray-s)}
.c-gray .th,.c-gray .t{fill:var(--gray-t)}.c-gray .ts{fill:var(--gray-sub)}
.c-blue>rect,.c-blue>circle,.c-blue>ellipse{fill:var(--blue-f);stroke:var(--blue-s)}
.c-blue .th,.c-blue .t{fill:var(--blue-t)}.c-blue .ts{fill:var(--blue-sub)}
.c-green>rect,.c-green>circle,.c-green>ellipse{fill:var(--green-f);stroke:var(--green-s)}
.c-green .th,.c-green .t{fill:var(--green-t)}.c-green .ts{fill:var(--green-sub)}
.c-amber>rect,.c-amber>circle,.c-amber>ellipse{fill:var(--amber-f);stroke:var(--amber-s)}
.c-amber .th,.c-amber .t{fill:var(--amber-t)}.c-amber .ts{fill:var(--amber-sub)}
.c-red>rect,.c-red>circle,.c-red>ellipse{fill:var(--red-f);stroke:var(--red-s)}
.c-red .th,.c-red .t{fill:var(--red-t)}.c-red .ts{fill:var(--red-sub)}
</style>
<rect width="680" height="100%" fill="var(--bg)"/>
```

Usage notes:

- The ramp classes use direct-child selectors for shapes. Apply `c-{ramp}` to the `<g>` that directly holds the rect/circle/ellipse and its text — a nested inner `<g>` makes shapes grandchildren and they render black.
- Never apply ramp classes to `<path>` — paths don't get ramp fill; style paths inline.
- Every `<text>` carries `t`, `ts`, or `th`. An unclassed text is the tell you forgot.
- The background rect height should match the viewBox height exactly (replace 100% with the computed H if a viewer mishandles percentages).

## Standard defs — include in every SVG, right after the stylesheet

```svg
<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6"
 markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none"
 stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"
 stroke-linejoin="round"/></marker></defs>
```

`context-stroke` makes the head inherit each line's color (modern browsers). For maximum portability, duplicate the marker with a hardcoded stroke per line color. `<defs>` may additionally hold one `<clipPath>`, subtle `<pattern>` fills used as a secondary cue alongside color for categorical data, and — in illustrative diagrams only — a single two-stop `<linearGradient>`. No filters.

## HTML token CSS

For HTML outputs (charts, interactive, mockups), embed in `<head>`:

```html
<style>
:root{--bg:#FCFCFA;--bg1:#FFFFFF;--bg2:#F1EFE8;--p:#2C2C2A;--s:#5F5E5A;
--t:#888780;--b:rgba(95,94,90,.25);--b2:rgba(95,94,90,.4);
--info-bg:#E6F1FB;--info-t:#0C447C;--ok-bg:#EAF3DE;--ok-t:#27500A;
--warn-bg:#FAEEDA;--warn-t:#633806;--bad-bg:#FCEBEB;--bad-t:#791F1F;
--r-md:8px;--r-lg:12px}
@media (prefers-color-scheme: dark){:root{--bg:#1A1A18;--bg1:#232321;
--bg2:#2C2C2A;--p:#EDEDEA;--s:#B4B2A9;--t:#888780;--b:rgba(180,178,169,.25);
--b2:rgba(180,178,169,.4);--info-bg:#0C447C;--info-t:#B5D4F4;
--ok-bg:#27500A;--ok-t:#C0DD97;--warn-bg:#633806;--warn-t:#FAC775;
--bad-bg:#791F1F;--bad-t:#F7C1C1}}
body{background:var(--bg);color:var(--p);font:16px/1.7 Inter,system-ui,sans-serif;
margin:0;padding:2rem;max-width:760px;margin-inline:auto}
h1{font-size:22px;font-weight:500}h2{font-size:18px;font-weight:500}
h3{font-size:16px;font-weight:500}
</style>
```

Mental test for every color decision: if the background were near-black, would every element still read? If the background were white, same question.

## Typography calibration

Reference widths for a grotesque sans at these sizes (Inter tracks within ~5% — keep the margins):

| text                                  | chars | weight | size | width |
| ------------------------------------- | ----- | ------ | ---- | ----- |
| Authentication Service                | 22    | 500    | 14px | 167px |
| Background Job Processor              | 24    | 500    | 14px | 201px |
| Detects and validates incoming tokens | 37    | 400    | 14px | 279px |
| forwards request to                   | 19    | 400    | 12px | 123px |
| データベースサーバー接続              | 12    | 400    | 14px | 181px |

Rule of thumb: 8px/char at 14px-500, 7px/char at 12px-400; CJK ~15px/char; formulas, sub/superscripts, and unicode symbols +30–50%. Before placing any text in a box: (text width + 2×24 padding) ≤ box width, or shorten the label.
