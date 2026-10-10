# UI mockups — standalone HTML

App screens, dashboards, settings pages, forms, cards, comparison grids. Full .html pages using the token CSS from tokens.md. The aesthetic: flat, clean surfaces, minimal 0.5px borders, generous whitespace, no gradients, no shadows except functional focus rings — with one exception noted under Forms.

## Tokens in practice

- Borders: `0.5px solid var(--b)` (or `var(--b2)` for emphasis/hover).
- Radius: `var(--r-md)` (8px) for most elements, `var(--r-lg)` (12px) for cards.
- Raised card: `background:var(--bg1); border:0.5px solid var(--b); border-radius:var(--r-lg); padding:1rem 1.25rem`.
- Metric card (summary numbers): `background:var(--bg2)`, no border, r-md, padding 1rem; muted 13px label above a 24px/500 number. Grids of 2–4 with 12px gap.
- Buttons: transparent bg, 0.5px var(--b2) border, hover var(--bg2), active scale(0.98).
- No rounded corners with single-sided borders — `border-left` accents get `border-radius:0`; rounding only with full borders.
- Spacing: rem for vertical rhythm (1, 1.5, 2rem); px for component-internal gaps (8, 12, 16px).
- Two font weights (400/500), headings h1 22 / h2 18 / h3 16, all weight 500.
- Sentence case in all UI copy. Realistic content, never lorem ipsum.

## Icons

Online HTML may load Tabler outline icons: `<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/dist/tabler-icons.min.css">` then `<i class="ti ti-home" aria-hidden="true"></i>`. Outline names only (no -filled variants). Size via font-size: 16–20px inline, 24px max decorative. Icon-only buttons need `aria-label`. Offline: skip icons; don't hand-draw icon paths.

## Layout

- Page content max-width ~760px centered (token CSS default). Full-bleed dashboards may widen to ~1100px — set explicitly.
- Responsive columns: `display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap:12px`.
- Grid overflow trap: `1fr` children have min-width:auto and blow out the column — use `minmax(0, 1fr)`.
- Table overflow: many-column tables expand past width:100% — use `table-layout:fixed` with explicit column widths, cut columns, or allow horizontal scroll on a wrapper div.
- Contained mockups (a phone screen, a chat thread, one modal, a single card) sit on a surface: wrap in `background:var(--bg2); border-radius:var(--r-lg); padding:2rem` or a device frame — don't float them naked on the page. Full-width mockups (dashboards, settings, tables) need no wrapper.
- Modal-in-context: a faux viewport block — `min-height:400px; background:rgba(0,0,0,0.45); display:flex; align-items:center; justify-content:center; border-radius:var(--r-lg)` — with the modal card inside. Shows the overlay state without hijacking the whole page.

## Comparison grids (decision making)

Side-by-side option cards: each card gets a leading icon, name, one-line muted subtitle, then differentiating rows or badges. The recommended option is accented with `border:2px solid #378ADD` only (the single exception to 0.5px — used to feature one card) plus a small badge: `background: var(--info-bg); color:var(--info-t); font-size:12px; padding:4px 12px; border-radius:var(--r-md)`. Keep backgrounds identical across cards. Detailed spec-by-spec comparisons belong in a real table or the reply text — the grid is for the at-a-glance choice.

## Data record (bounded object: contact, receipt, ticket)

One raised card wraps the whole record. People get an initials avatar:

```html
<div class="card" style="max-width:420px">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
    <div style="width:44px;height:44px;border-radius:50%;background:var(--info-bg);
      display:flex;align-items:center;justify-content:center;font-weight:500;
      font-size:14px;color:var(--info-t);">MR</div>
    <div>
      <p style="font-weight:500;font-size:15px;margin:0;">Maya Rodriguez</p>
      <p style="font-size:13px;color:var(--s);margin:0;">VP of Engineering</p>
    </div>
  </div>
  <div style="border-top:0.5px solid var(--b);padding-top:12px;">
    <table style="width:100%;font-size:13px;">
      <tr><td style="color:var(--s);padding:4px 0;">Email</td>
          <td style="text-align:right;padding:4px 0;color:var(--info-t);">m.rodriguez@acme.com</td></tr>
      <tr><td style="color:var(--s);padding:4px 0;">Phone</td>
          <td style="text-align:right;padding:4px 0;">+1 (415) 555-0172</td></tr>
    </table>
  </div>
</div>
```

## Forms (static mockups)

Standalone forms don't submit anywhere — they're mockups of a flow, or local state for an interactive page (interactive.md). Conventions:

- Phrase prompts as questions, not field labels: "Which side are you on?" not "Side:". Conversational beats bureaucratic.
- Consistent rhythm: question label (14px/500) → input → next question → footer buttons right-aligned (secondary "Skip", primary "Continue").
- Vary input formats to fit the content — don't render everything as pills: short text-only options ≤4 words → pill buttons; options deserving an icon
  - one-line subtitle → small cards; output/layout pickers → preview tiles (a tiny stroke illustration of the result + label); quantities/scales → range slider with contextual end labels ("Rough draft" ↔ "Polished"); dates → `<input type="date">`; free text → textarea.
- Include an "Other" escape-hatch option revealing a text input when the listed options can't be exhaustive.
- Selection state: light info fill + info border from one ramp (blue unless a real semantic — amber = cost, red = destructive, green = confirm). One accent family per form; no rainbow.
- Forms are the one place a whisper of elevation is allowed: `box-shadow:0 1px 2px rgba(0,0,0,0.04)` on option cards/tiles.
- Toggle pills with JS: flip `aria-pressed` and a selected class; never bake selection into inline styles (it stops visibly toggling).
