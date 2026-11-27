# Install note for GitHub Copilot: next-level Certificates and URLs panels

For the person: unpack this package on the workstation, open the `sapopsautomation` repository in VS Code, start
Copilot Chat in agent mode and say: "Read COPILOT_INSTALL.md in <package folder> and follow it." Everything below
the line is written for Copilot.

---

## Task

Install the redesigned **Monitoring > Certificates** and **Monitoring > URLs** panels from this package into the
SAITron orchestrator UI in this repository. Work on a new branch and stop when the change is ready for review.

Done means:

- the app serves the four panel files from `static/next/` plus `modern-dark-v3.css`, and the certificate drawer in
  `index.html` is a `<dialog>`;
- the modern look is on in the dark theme, and the brand, light and neon themes still work;
- the existing tests pass, and only assertions that the new markup changes on purpose were updated;
- there is a release-notes entry and a short summary for the reviewer.

Do not deploy, push or merge. In this repository a UI change needs a plan, an approval and a release-notes entry,
and a person does the deploy (orchestrator image, then `06-cloudrun`).

## What this package is

A design export of two read-only operator panels, made on 2026-11-13. `README.md` describes the export and the
rules a redesign must keep. It was written before the `static/next/` folder existed, so it does not mention it.

- `static/certs.js`, `certs.css`, `urls.js`, `urls.css` are copies of the app's files at export time. This is the
  **baseline**.
- `static/next/` holds the redesigned versions of those four files, the overlay `modern-dark-v3.css`, and
  `next-vs-current.diff` (baseline to next, for review).
- `templates/panels_snippet.next.html` holds the one template change.
- `static/preview/` is an offline harness with fake data. It shows how the result should look: run
  `serve-preview.cmd`, then open `http://127.0.0.1:8766/static/preview/certs.html?theme=dark&look=v3` and
  `urls.html` with the same query.

The header comments of `static/next/certs.js` and `static/next/urls.js` list every change with its reason. Read them
first.

This package was published with company names removed. The sample data therefore uses invented CA names, and one
help sentence in `certs.js` is generic (see step 1).

## Where things go

Paths on the right are relative to the `sapopsautomation` root.

| From the package | To the app | How |
|---|---|---|
| `static/next/certs.js` | `app/sapops/web/static/certs.js` | replace, then restore one line (step 2) |
| `static/next/certs.css` | `app/sapops/web/static/certs.css` | replace |
| `static/next/urls.js` | `app/sapops/web/static/urls.js` | replace |
| `static/next/urls.css` | `app/sapops/web/static/urls.css` | replace |
| `static/next/modern-dark-v3.css` | `app/sapops/web/static/modern-dark-v3.css` | new file |
| `templates/panels_snippet.next.html` | `app/sapops/web/templates/index.html` | edit by hand (step 3) |

Do not copy anything else:

- `static/styles.css`, `incidents.css`, `checks.css`, `bg-1.jpg`: copies of the app's shared files. The app's own
  files are the truth.
- `static/preview/`, `api-samples/`, `backend/`, `screenshots/`, `reference/`: harness and reference material.
- `static/modern-dark.css`, `static/modern-dark-v2.css`: earlier overlays for the old markup. They do not fit the
  new scripts.
- The package folder itself must not be committed to the repository.

## Steps

### 1. Compare the app with the baseline before changing anything

Compare the app's four panel files with the baseline files in `static/`, ignoring line endings.

Expected: identical, except one line in `certs.js`, the help sentence that starts with `<li><b>Flags</b>`. The
package wording is generic because company names were removed. The app's wording is the correct one.

If anything else differs, the app has changed since the export. Do not overwrite it. Apply
`static/next/next-vs-current.diff` on top of the app's files instead, keep the app-side changes, and list them in
your summary. If the diff does not apply cleanly, stop and ask.

### 2. Put the files in place

1. Save the app's `<li><b>Flags</b>` line from the current `certs.js`.
2. Replace the four files and add `modern-dark-v3.css` as in the table.
3. Put the saved line back into the new `certs.js`. It is a single line that the redesign did not touch.

Follow the repository's line-ending convention (the package uses CRLF). The scripts are plain ASCII on purpose:
non-ASCII characters are written as `\uXXXX` escapes. Leave them as they are.

### 3. Edit `index.html`

1. **Drawer.** Replace the block `<div id="cert-panel" class="drawer crt-drawer" hidden>...</div>` with the
   `<dialog>` block from `templates/panels_snippet.next.html`. The IDs stay the same (`cert-panel`,
   `cert-panel-title`, `cert-panel-body`, `cert-panel-close`). The `<dialog>` has no `hidden` attribute: a closed
   dialog is not shown, and `certs.js` opens it with `showModal()`. The menu buttons and the two panes do not
   change.
2. **Stylesheets.** Link `modern-dark-v3.css` after `certs.css`. The order must be `urls.css`, `certs.css`,
   `modern-dark-v3.css`, because `certs.css` reuses pieces of `urls.css` and the overlay sits on both. Use the
   template's existing way of building static URLs and cache-busting. If the template links `modern-dark.css` or
   `modern-dark-v2.css`, remove that link: all three overlays use the same switch.
3. **Switch.** The overlay applies only when `<html>` has the class `modern` and `data-theme="dark"`. Add `modern`
   to the class list of `<html>`. Check that the app's theme switcher only sets `data-theme` and does not
   overwrite the whole `class` attribute.

This makes the modern look the dark theme for every user. If the person wants it to be optional, stop and ask. Do
not invent a toggle.

### 4. Tests

Run the repository's tests for `app/sapops/tests/test_cert_routes.py`. They also check the UI wiring: element IDs,
`onShow`, the section order and balanced `<div>` tags.

Assertions that may fail because of intended changes:

- the drawer is a `<dialog>`, not a `<div hidden>`;
- each table has 8 columns, not 10, with `<col class="c-...">` instead of percentage widths;
- the filter bars are `<search class="chk-toolbar">`, and the active chip is exposed with `aria-pressed`.

Update only those. Do not loosen or delete a test to make it pass. If a test fails for another reason, stop and
report it.

### 5. Check in a browser

Start the app the way the repository documents and open both panels. If you cannot drive a browser, say so and
hand this list to the person. Do not report it as checked.

- Both panels load their data and the console shows no errors.
- The dark theme shows the modern look. Brand, light and neon are readable and complete.
- Clicking a filter chip moves the sections smoothly. Typing in the search field does not animate.
- "Details" and a row under "Most urgent" open the drawer. Esc, the close button and a click outside close it, and
  the focus returns to the button that opened it.
- Hovering or focusing a bar in the expiry outlook lists the certificates of that week.
- The "last scan" and "last check" chips show an age.
- At 1280 px wide, status pills, expiry dates and the PSE state are not cut off.
- As a non-admin user the run buttons are absent and the header still looks right.
- UNKNOWN, UNREACHABLE, UNREADABLE, stale and MISSING never look green.
- Other screens of the app in the dark theme still look right (see "Known limits").

### 6. Release notes and summary

Add a release-notes entry in the file's existing format. Then stop and report:

- the result of the baseline comparison in step 1;
- the files you changed;
- the tests you ran and their results, and which assertions you updated;
- what you could not check;
- open questions for the person.

## What does not change

- No backend change. Same endpoints (`/api/certificates`, `/api/certificates/item`, `/api/certificates/run`,
  `/api/urls`, `/api/urls/run`) and the same data.
- Same element IDs, the same six certificate sections in the same order, `window.CertsApp` and `window.UrlsApp`
  with `onShow()`.
- Still read-only. The only actions are the admin run buttons `#crt-run` and `#url-run`.
- No library, no build step, no request to another host.
- Every API value is still escaped before it is inserted as HTML.
- Storage: the same `sessionStorage` filter keys, plus one new key, `sapops-vt-slow`. It records that animated
  filter changes were too slow in this browser session, so they are switched off until the tab is closed.
- The generated HTML uses a few inline `style` attributes, as before. If the app sends a Content-Security-Policy
  that forbids them, report it. Do not loosen the policy.

## Known limits (tell the reviewer)

- Checked on 2026-11-13 in the Playwright builds of Chromium 158, Firefox 159 and WebKit 27.2, against the offline
  preview with fake data. Not checked: the real app, real data, the browsers on the operator machines.
- The overlay's colours are global for `html.modern[data-theme="dark"]`. It feeds the app's own variables
  (`--bg`, `--card`, `--fg`, `--accent`, `--ok`, `--warn`, `--err`, `--radius` and others), restyles the Monitoring
  shell and its navigation, and paints a faint gradient on `body::before`. So every screen in the dark theme gets
  the new palette, not only these two panels. Only the two panels were looked at. If another screen looks wrong,
  report it. Do not patch other screens in this change.
- Newer browser features are detected and have fallbacks: without View Transitions a filter change is instant,
  without popovers the chart bars keep their `title` text, and a browser without CSS nesting ignores the overlay
  and shows the normal dark theme.
- Relative times ("12 min ago") use the browser clock.
- While the drawer is open the page keeps its scrollbar gutter, about 15 px with classic scrollbars, so the layout
  does not jump.

## Rollback

Revert the commit. Nothing in the backend or the data changes.
