# SAITron — Certificates & URLs panels (design export)

Export of the two read-only operator panels in the SAITron orchestrator UI (**Monitoring › Certificates** and
**Monitoring › URLs**), built 2026-11-13 (cert lifecycle phase 3, steps S7/S8). Purpose: a self-contained package to
redesign the visuals ("more modern graphics") without the rest of the app.

**All data in this package is fake** (`*.example.invalid` hosts, invented systems). No secrets, no real hostnames.

## Open the previews

1. Double-click `serve-preview.cmd` (needs Python), or run `python -m http.server 8766` in this folder.
2. Open <http://127.0.0.1:8766/static/preview/certs.html> and <http://127.0.0.1:8766/static/preview/urls.html>.
3. Use the **Theme** buttons (bottom right) or `?theme=brand|dark|light|neon` — the app has four themes and every
   panel must work in all of them.

The previews run the **real** `certs.js` / `urls.js` / CSS; only `fetch` is stubbed with sample data. Opening the
HTML via `file://` also works, except for the brand background photo.

## Contents

| Path | What |
|---|---|
| `static/certs.js`, `static/certs.css` | Certificates panel (`window.CertsApp`, renders into `#cert-body` and the drawer `#cert-panel`) |
| `static/urls.js`, `static/urls.css` | URLs panel (`window.UrlsApp`, renders into `#url-body`) |
| `static/styles.css`, `incidents.css`, `checks.css`, `bg-1.jpg` | Shared app styles the panels build on (theme variables, cards, `.mon-*` shell, pills, drawer, chips). Not to be redesigned here — reuse the variables |
| `static/preview/certs.html`, `urls.html` | Offline previews with fake data + theme switcher + **Look: current / modern dark** |
| `static/modern-dark.css` | Prototype CSS-only "modern dark" overlay (see below) |
| `FABLE_PROMPT.md` | Ready-to-paste prompt to cross-check the design with an external design tool / AI |
| `templates/panels_snippet.html` | The panel markup from `index.html` (Jinja2): menu buttons, the two panes, the detail drawer |
| `api-samples/*.json` | Real response shapes, produced by the backend (`cert_routes.py`) from test fixtures |
| `backend/cert_routes.py` | FastAPI routes = the data contract (reference only) |
| `screenshots/` | Current look: both panels × 4 themes + the certificate drawer |
| `reference/ui-mockup.jpeg` | The original layout mockup (take the layout, not the names) |

## What the panels show today

**Certificates** (`GET /api/certificates`, daily scan at 05:45 + admin "Refresh (scan now)"):
- Summary card: verdict (RED/AMBER/GREEN/UNKNOWN), most urgent certificates, "needs attention" (legacy CA, wrong CA,
  PSE DB mismatch, expired trusted CAs, unreadable), next actions.
- Expiry outlook: 13 weekly buckets, stacked red (≤14 d) / amber (≤30 d) / blue (later).
- PKI strip: last EJBCA `pki-check` (test/prod RA reachable, credential status).
- Filters: category chips with counts, environment, "only due", text search (kept in `sessionStorage`).
- Six section cards in fixed order: SAP ABAP (grouped per system; one row per STRUST PSE), SAP Java, Web Dispatcher,
  BOBJ, GCLB, Non-SAP. Columns: status, system + tier, certificate (source/PSE), subject + endpoint, issuer + CA flag,
  expires, days left, source (TLS/HANA/STRUST), PSE state, details.
- Drawer (`GET /api/certificates/item?key=`): all fields + the PSE's trusted list (expired / legacy CAs highlighted).

**URLs** (`GET /api/urls`, checked every 5 min + admin "Check now"):
- KPI tiles: total, up, down, unreachable/unknown, certificate ≤30 d.
- Filters: tier chips, status chips with counts, kind select, text.
- Table grouped by tier: status, system, kind, access (F5 / PAS / GCLB / RISE…), URL, HTTP code, latency, cert days,
  down since / last up, checked (+ "stale" when older than 15 min → shown as UNKNOWN, never UP).
- Auto-refresh every 5 minutes.

## Rules a redesign must keep

1. **Plain HTML/CSS/vanilla JS, no build step, no framework, no CDN.** Any chart/icon library must be vendored as a
   local file under `static/` (small, MIT/Apache). Inline SVG is preferred for charts.
2. **Same data contract** (`api-samples/`). Anything needing new data (e.g. URL uptime history / sparklines — today
   `url_check` stores only the latest result + `last_up_at` + `fail_count`) is a separate backend change.
3. **Grey is never green:** `UNREACHABLE`, `UNREADABLE`, `UNKNOWN`, stale results and `MISSING` PSEs must never look OK.
4. **Read-only.** The only actions are the admin-only run buttons (`#crt-run`, `#url-run`) — they may be hidden for
   non-admins, so the layout must not depend on them. No other buttons that change anything.
5. Keep the element IDs used by the template and JS (`#cert-body`, `#url-body`, `#crt-last`, `#url-last`, `#crt-run`,
   `#url-run`, `#refresh-certs`, `#refresh-urls`, `#cert-panel*`), the six certificate sections and their order, and
   the `window.CertsApp` / `window.UrlsApp` `onShow()` entry points.
6. All four themes (brand / dark / light / neon) via the existing CSS variables in `styles.css`; WCAG AA contrast;
   status must not rely on colour alone (keep the text pill).
7. Escape every value from the API before inserting HTML (the current code uses an `esc()` helper).
8. Must stay usable at 1280 px wide; the drawer is 900 px.

## Modern dark prototype (`static/modern-dark.css`)

You liked the **dark** theme most, so this package adds a CSS-only overlay on top of it. Open a preview and press
**Look › modern dark** (or `?theme=dark&look=modern`); **Look › current** switches back. Compare
`screenshots/*-dark.png` with `screenshots/*-modern-dark.png`. It changes no JS, markup or data; it is active only with
`<html class="modern" data-theme="dark">`. Older browsers just show today's dark theme.

| Modern feature | Used for | Support |
|---|---|---|
| OKLCH colours + relative colour syntax `oklch(from var(--x) l c h / .14)` | Even status tints for every pill and tile from one base colour; `color-mix()` fallback | Baseline 2024 |
| CSS nesting | The overlay is one nested block under `:root.modern[data-theme="dark"]` | Baseline 2023 |
| `:has()` | Red/amber stripe on rows with a RED/DOWN pill, red edge on certificate sections containing a problem, KPI tile colour from its icon | Baseline 2023 |
| `@starting-style` (+ `transition-behavior`) | Drawer slides in from `display:none`; sections fade in on every render | Baseline 2024 |
| `@property` | Animated conic-gradient ring around the primary button | Baseline 2024 |
| `overflow: clip` + `position: sticky` | Sticky table headers inside the rounded, clipped card (`hidden` would break sticky) | Baseline |
| Container queries | Summary/outlook stack by **panel** width, not window width | Baseline 2023 |
| `interpolate-size` + `::details-content` | Animated open/close of "What is checked and how" | Chrome/Edge 131+ (others: instant) |
| `backdrop-filter`, `text-wrap: balance/pretty`, `tabular-nums`, `color-scheme`, `accent-color`, `scrollbar-color`, `:focus-visible`, `prefers-reduced-motion` | Glass cards, tidy headings, aligned numbers, native dark controls, keyboard focus, motion off on request | Baseline |

Tried and **dropped**: scroll-driven entrance (`animation-timeline: view()`). Content below the fold stays invisible
until scrolled, which is wrong for a monitoring screen.

Next level (needs small JS/markup changes, not in the overlay): **View Transitions** (`document.startViewTransition`)
for filter changes; **Popover API + CSS anchor positioning** for real tooltips instead of `title=`; SVG outlook chart
with hover/click-to-filter; uptime sparklines (needs a URL history table in the backend).

Cross-check with an external design tool or AI: paste `FABLE_PROMPT.md` and attach this zip.

## Improvement ideas (starting points)

- **Certificates summary:** replace the text-heavy card with a state donut / ring (OK · warn · critical · expired ·
  unknown) + 3–4 KPI tiles like the URLs panel; keep "most urgent" as a short list with countdown chips.
- **Expiry outlook:** fill the card height; rounded stacked bars or an area/timeline chart with a "today" marker,
  hover tooltips listing the certificates per week, click a bar to filter the table.
- **Per-system heatmap** (systems × categories, coloured by worst state) as an overview above the sections.
- **Tables:** sticky headers, compact density toggle, row hover with left status stripe, monospaced days-left
  countdown with a small progress bar (days left vs. validity), copy-to-clipboard on endpoints.
- **URLs:** status dots with a pulse for DOWN, latency mini-bars, a "last up" relative time ("12 min ago"),
  grouping toggle (tier / system / kind).
- **Drawer:** certificate "card" header (CN, issuer chain as a small vertical timeline, validity bar), trusted list
  with search.
- Subtle motion only (`prefers-reduced-motion` respected), skeleton loaders instead of "Loading…".

## Where it lives in the repo

`TFE/GCP/SZ/sapopsautomation/app/sapops/web/static/{certs,urls}.{js,css}`, markup in
`app/sapops/web/templates/index.html`, routes in `app/sapops/cert_routes.py`, tests in
`app/sapops/tests/test_cert_routes.py` (they also check the UI wiring: IDs, `onShow`, section order, balanced
`<div>`s). A redesign comes back as a normal UI change with its own plan, approval and RELEASE_NOTES entry; deploy =
orchestrator image → apply `06-cloudrun`.
