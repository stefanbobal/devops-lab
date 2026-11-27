# Prompt — cross-check the dark design of the SAITron Certificates & URLs panels

Paste the text below into the design tool / AI and attach the zip (or at least `README.md`, `static/`,
`screenshots/`, `api-samples/`).

---

You are a senior product designer and front-end engineer (2026 web platform). Review two read-only monitoring panels
of an internal SAP operations console: **Monitoring › Certificates** and **Monitoring › URLs**. The operator prefers
the **dark** theme.

Attached:
- `screenshots/urls-dark.png`, `certs-dark.png`: the current dark look.
- `screenshots/*-modern-dark.png`, `certs-drawer-modern-dark.png`: my CSS-only "modern dark" proposal
  (`static/modern-dark.css`).
- `static/`: the real panel code (`certs.js`, `urls.js`, CSS) plus shared app styles. Previews in `static/preview/`
  run offline with fake data (`python -m http.server`, then `?theme=dark&look=modern`).
- `api-samples/`: the exact JSON the panels receive. `README.md`: what the panels show and the rules.

Tasks:
1. Critique the current dark design and my modern-dark overlay: hierarchy, scannability for an on-call operator,
   density, colour and contrast (WCAG AA), status semantics, consistency between the two panels.
2. Propose improvements that use **current, broadly supported web-platform features** (e.g. OKLCH / relative colour,
   `:has()`, container queries, `@starting-style`, View Transitions, Popover API, CSS anchor positioning,
   `@scope`, `light-dark()`, subgrid, scroll-state queries). For each: what it improves, browser support, fallback.
3. Deliver the result as **(a)** an improved drop-in `modern-dark.css` that only needs `<html class="modern"
   data-theme="dark">`, and **(b)** separately, any small JS/markup changes you recommend (as a diff against
   `certs.js` / `urls.js`), each with a one-line reason.
4. Optionally, one hi-fi mockup image per panel.

Hard constraints (do not break):
- Plain HTML/CSS/vanilla JS. No framework, no build step, no CDN; any library must be a small local file.
- Same API data, same element IDs (`#cert-body`, `#url-body`, `#crt-last`, `#url-last`, `#crt-run`, `#url-run`,
  `#refresh-certs`, `#refresh-urls`, `#cert-panel*`), `window.CertsApp` / `window.UrlsApp` with `onShow()`.
- Six certificate sections in this order: SAP ABAP, SAP Java, Web Dispatcher, BOBJ, GCLB, Non-SAP.
- Grey is never green: UNREACHABLE / UNREADABLE / UNKNOWN / stale / MISSING must never look OK. Status must not rely on
  colour alone (keep the text label).
- Read-only: no new buttons that change anything. The admin run buttons may be absent for normal users.
- Never hide content that is not yet scrolled into view; respect `prefers-reduced-motion`.
- Escape every API value before inserting HTML. Must work at 1280 px wide.
- Uptime history/sparklines are not in the data today; mark such ideas as "needs backend".
