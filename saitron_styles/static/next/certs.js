// Monitoring > Certificates pane (cert lifecycle S7, UI-1, read-only). Layout after docs/cert-lifecycle/ui-mockup.jpeg
// (layout only - all names come from the inventory): summary card + 13-week expiry outlook, PKI status strip, filter
// bar, six section cards (SAP ABAP, SAP Java, Web Dispatcher, BOBJ, GCLB, Non-SAP), detail drawer. Data from
// GET /api/certificates (+ /item for the drawer); admin Refresh starts the cert-inventory Job. Renewal columns and
// actions come with UI-2. UNKNOWN / UNREACHABLE / UNREADABLE are grey, never green. Exposes window.CertsApp.
//
// "Next level" build (design export 2026-11). Same data contract, same element IDs, same six sections, still
// read-only. What changed against certs.js, each with its reason:
//   - View Transitions for chips / selects / toggles     -> the eye can follow what a filter removed or moved
//   - the drawer is a <dialog> opened with showModal()    -> focus trap, Esc and an inert page for free
//   - chart weeks are buttons with a popover              -> lists the certificates behind a bar (mouse, keys, touch)
//   - summary: verdict + state tiles + state bar          -> numbers instead of a sentence; urgent rows open the drawer
//   - table: 8 columns with <col class>, not 10 with %    -> status, expiry and PSE are never cut off at 1280 px
//   - "last scan" chip with age and data-age              -> a dead scan job is visible (stale data looks like good data)
//   - inline SVG icons, aria-pressed, <search>, role=status -> one icon style on every OS; state exposed to assistive tech
// Every newer API is feature-detected and has a fallback, so one build serves every browser.
(function () {
  "use strict";

  const STORE_KEY = "sapops-certs-filter";
  const saved = (() => { try { return JSON.parse(sessionStorage.getItem(STORE_KEY) || "{}"); } catch (_) { return {}; } })();
  const S = { data: null, cat: saved.cat || "all", tier: saved.tier || "all", due: !!saved.due, q: saved.q || "",
              openMissing: new Set(), notice: null, busy: false, ticker: null };
  const SECTIONS = [
    ["sap_abap", "SAP ABAP systems", "db", "served TLS certificates (ICM, F5, Web Dispatcher) \u00B7 HANA SQL \u00B7 every STRUST PSE from the SSF_ALERT_CERTEXPIRE list"],
    ["sap_java", "SAP Java systems", "cup", "TLS on the Java ports \u00B7 HANA SQL"],
    ["web_dispatcher", "SAP Web Dispatcher", "route", "monitoring only \u00B7 TLS check \u00B7 RISE Web Dispatchers are covered by the GCLB pane"],
    ["bobj", "BOBJ", "chart", "CMC behind the F5 \u00B7 TLS check"],
    ["gclb", "Google Cloud load balancers (GCLB)", "cloud", "front-end certificates \u00B7 see the GCLB pane"],
    ["non_sap", "Non-SAP certificates", "box", "grouped by system"],
  ];
  const CHIP_LABEL = { all: "All", sap_abap: "SAP ABAP", sap_java: "SAP Java", web_dispatcher: "Web Dispatcher", bobj: "BOBJ", gclb: "GCLB", non_sap: "Non-SAP" };
  const TIERS = ["production", "preproduction", "simulation", "development", "sandbox", "service_zone", "infrastructure"];
  const TIER_LABEL = { production: "prod", preproduction: "pre-prod", simulation: "sim", development: "dev", sandbox: "sandbox", service_zone: "service zone", infrastructure: "infra" };
  const STATE_PILL = { OK: ["ok", "GREEN"], WARN: ["warn", "AMBER"], CRITICAL: ["err", "RED"], EXPIRED: ["err", "EXPIRED"],
    UNREACHABLE: ["muted", "UNREACHABLE"], UNREADABLE: ["muted", "UNREADABLE"], UNKNOWN: ["muted", "UNKNOWN"], MISSING: ["muted", "NOT CREATED"] };
  const FLAG_LABEL = { LEGACY_CA: "legacy CA", WRONG_CA: "wrong CA", OTHER_CA: "other CA", DB_MISMATCH: "DB mismatch",
    PSE_CHECK_FAILED: "PSE check failed", LEGACY_CA_TRUSTED: "legacy CA trusted" };
  const SOURCE_LABEL = { tls_scan: "TLS", tls_hana: "HANA", strust: "STRUST", gclb: "GCLB", not_probed: "\u2014" };
  const DUE = new Set(["WARN", "CRITICAL", "EXPIRED"]);
  const GREY = ["UNREACHABLE", "UNREADABLE", "UNKNOWN", "MISSING"];
  const OUTLOOK_DAYS = 13 * 7;   // same horizon as outlook() in cert_routes.py
  const LATE_H = 26, STALE_H = 50;   // daily scan at 05:45: one missed run = overdue, two = stale
  const DT = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  const DD = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "2-digit", month: "short" });
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v) => { if (!v) return "\u2014"; const d = new Date(v); return isNaN(d) ? esc(v) : esc(DT.format(d).replace(",", "")); };
  const day = (v) => { if (!v) return "\u2014"; return esc(String(v).slice(0, 10)); };
  const body = () => document.getElementById("cert-body");
  const tierOf = (r) => String(r.tier || "").toLowerCase();
  const who = (r) => r.sid || r.system || "?";
  const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");
  const daysCls = (d) => (d <= 7 ? "err" : d <= 30 ? "warn" : "ok");

  // ---- progressive enhancement -----------------------------------------------------------------
  const HAS_VT = typeof document.startViewTransition === "function";
  const HAS_POPOVER = "popover" in HTMLElement.prototype;
  const HAS_HINT = (() => { const d = document.createElement("div"); d.setAttribute("popover", "hint"); return d.popover === "hint"; })();
  const HAS_INTEREST = "interestForElement" in HTMLButtonElement.prototype;
  const HAS_ANCHOR = !!(window.CSS && CSS.supports && CSS.supports("position-area", "top"));
  const REDUCED = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };

  // Discrete changes (chips, selects, toggles) move and cross-fade in a View Transition. Typing and the
  // timers render directly: a monitoring screen must not animate on every keystroke or refresh.
  // A transition must never hold back the data. The browser calls back only after it has captured the
  // old picture, and where painting is slow (no GPU: remote desktop, VDI) that can take a second and
  // can even starve timers. So there is a budget: when a transition exceeds it, the pane renders at
  // once where it can, the animation is dropped, and the session stops asking for transitions (the
  // flag is shared by both panes).
  const VT_BUDGET_MS = 150;
  const VT_SLOW_KEY = "sapops-vt-slow";
  let vtOk = HAS_VT && (() => { try { return !sessionStorage.getItem(VT_SLOW_KEY); } catch (_) { return true; } })();
  function update(fn) {
    if (!vtOk || REDUCED.matches) { fn(); return; }
    const t0 = performance.now();
    let done = false;
    const run = () => {
      if (done) return;
      done = true;
      if (performance.now() - t0 > VT_BUDGET_MS) { vtOk = false; try { sessionStorage.setItem(VT_SLOW_KEY, "1"); } catch (_) { /* private mode */ } }
      fn();
    };
    const t = document.startViewTransition(run);
    setTimeout(() => { if (!done) { run(); t.skipTransition(); } }, VT_BUDGET_MS);
    // a skipped transition rejects with AbortError: expected. Anything else is a real error and must surface.
    [t.ready, t.finished].forEach((p) => p.catch((e) => { if (!e || e.name !== "AbortError") throw e; }));
  }

  // Inline SVG instead of emoji: one stroke style on every OS and in every theme (currentColor), no font, no CDN.
  const ICON = {
    db: '<ellipse cx="12" cy="5.5" rx="7" ry="2.8"/><path d="M5 5.5v13c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-13"/><path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8"/>',
    cup: '<path d="M5 9.5h12v4.5a5 5 0 0 1-5 5h-2a5 5 0 0 1-5-5z"/><path d="M17 11h1.2a2.3 2.3 0 0 1 0 4.6H17"/><path d="M8.5 3.5v2.5M11.5 3.5v2.5M14.5 3.5v2.5"/>',
    route: '<path d="M4 7h3c2.2 0 3.6 1.2 4.5 3l1 2c.9 1.8 2.3 3 4.5 3h3"/><path d="M4 17h3c1.2 0 2.2-.4 3-1M20 7h-3c-1.2 0-2.2.4-3 1"/><path d="M17.5 4.5 20 7l-2.5 2.5M17.5 14.5 20 17l-2.5 2.5"/>',
    chart: '<path d="M4 4v16h16"/><path d="M8.5 16v-4M12.5 16V8M16.5 16v-6"/>',
    cloud: '<path d="M7.5 18.5a4 4 0 0 1-.6-7.96 5.5 5.5 0 0 1 10.6 1.2A3.4 3.4 0 0 1 17 18.5z"/>',
    box: '<path d="M12 3.5 4.5 7.5v9L12 20.5l7.5-4v-9z"/><path d="M4.5 7.5 12 11.5l7.5-4M12 11.5v9"/>',
    spark: '<path d="M11 3.5l1.8 4.7 4.7 1.8-4.7 1.8L11 16.5l-1.8-4.7L4.5 10l4.7-1.8z"/><path d="M18 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
    cal: '<rect x="4" y="5.5" width="16" height="14" rx="2.5"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
    shield: '<path d="M12 3.5 5 6.5v5c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9v-5z"/><path d="M9 12l2.2 2.2L15 10.4"/>',
  };
  const icon = (name) => '<svg class="chk-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (ICON[name] || "") + "</svg>";

  async function call(url, opts) {
    const r = await fetch(url, Object.assign({ credentials: "same-origin" }, opts || {}));
    if (r.status === 401) { window.location = "/auth/login"; throw new Error("Not logged in"); }
    let j = null;
    try { j = await r.json(); } catch (_) { /* no body */ }
    if (!r.ok) {
      const d = j && j.detail;
      throw new Error(typeof d === "string" ? d : (d && d.message) || String(r.status));
    }
    return j;
  }
  function saveFilter() {
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify({ cat: S.cat, tier: S.tier, due: S.due, q: S.q })); } catch (_) { /* private mode */ }
  }
  function paneVisible() { const p = document.querySelector('[data-pane="certs"]'); return p && !p.hidden; }
  function onShow() { mount(); }

  async function mount() {
    const el = body();
    if (!el) return;
    if (!S.data) el.innerHTML = '<p class="empty">Loading&hellip;</p>';
    try {
      S.data = await call("/api/certificates");
    } catch (e) {
      el.innerHTML = '<div class="mon-placeholder" role="alert">Could not load the certificates: ' + esc(e.message) + "</div>";
      return;
    }
    render();
    // the age in the "last scan" chip must stay true while the pane is open
    if (!S.ticker) S.ticker = setInterval(() => { if (paneVisible()) freshness(); }, 60000);
  }

  async function runNow() {
    if (S.busy) return;
    S.busy = true;
    render();
    try {
      await call("/api/certificates/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      S.notice = { cls: "info", text: "Certificate scan started \u2013 results in a few minutes. Press Reload then." };
    } catch (e) {
      S.notice = { cls: "err", text: "Could not start the scan: " + e.message };
    }
    S.busy = false;
    render();
  }

  // ---- pieces --------------------------------------------------------------------------------
  function ago(v) {
    const t = new Date(v).getTime();
    if (!v || isNaN(t)) return "";
    const m = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    const h = Math.round(m / 60);
    return h < 48 ? h + " h ago" : Math.round(h / 24) + " d ago";
  }
  // "Last scan" chip: time, age, and a state (data-age) the CSS turns into a dot. A scan that is overdue
  // also says so in words - stale data must never look like fresh data.
  function freshness() {
    const last = document.getElementById("crt-last");
    if (!last || !S.data) return;
    const t = S.data.last_checked ? new Date(S.data.last_checked).getTime() : NaN;
    if (isNaN(t)) { last.dataset.age = "unknown"; last.innerHTML = "daily 05:45"; return; }
    const hours = (Date.now() - t) / 3600000;
    const age = hours > STALE_H ? "stale" : hours > LATE_H ? "late" : "fresh";
    last.dataset.age = age;
    last.innerHTML = "Last scan <b>" + fmt(S.data.last_checked) + '</b> <span class="chk-ago">' + esc(ago(S.data.last_checked)) + "</span>" +
      (age === "fresh" ? "" : ' <b class="chk-age-word">' + (age === "stale" ? "stale" : "overdue") + "</b>") + " &middot; daily 05:45";
  }
  function pill(state) {
    const [cls, txt] = STATE_PILL[state] || ["muted", state || "?"];
    return '<span class="pill ' + cls + ' crt-pill">' + esc(txt) + "</span>";
  }
  function daysCell(r) {
    const d = r.days_left;
    if (d == null || GREY.includes(r.state)) {
      return '<span class="chk-dash" title="' + esc(r.reason || r.error_type || "") + '">&mdash;</span>';
    }
    return '<span class="chk-days ' + daysCls(d) + '">' + esc(d) + "</span>";
  }
  // one cell answers "when": the days left (the number to act on) above the date
  function expiryCell(r) {
    const d = r.days_left;
    if (d == null || GREY.includes(r.state)) {
      return '<span class="chk-dash" title="' + esc(r.reason || r.error_type || "") + '">&mdash;</span>';
    }
    return '<div class="crt-two crt-exp"><span class="chk-days ' + daysCls(d) + '">' + esc(d) + ' d</span><span class="crt-sub">' + day(r.not_after) + "</span></div>";
  }
  function flagPills(flags) {
    return (flags || []).map((f) => '<span class="pill ' + (f === "WRONG_CA" || f === "DB_MISMATCH" || f === "PSE_CHECK_FAILED" ? "err" : "warn") +
      '">' + esc(FLAG_LABEL[f] || f) + "</span>").join(" ");
  }
  function certId(r) {
    if (r.cert_role === "list") return "SSF_ALERT_CERTEXPIRE list";
    if (r.source === "strust") return (r.pse_context || "") + " " + (r.pse_applic || "") + (r.pse_instance ? " \u00B7 " + r.pse_instance : "");
    if (r.source === "tls_hana") return "HANA SQL " + String(r.entry_id || "").split("-").pop();
    const port = String(r.endpoint || "").split(":").pop();
    return "TLS" + (port && /^\d+$/.test(port) ? " :" + port : "");
  }
  function cn(subject) {
    const m = /(?:^|,\s*)CN=([^,]+)/.exec(subject || "");
    return m ? "CN=" + m[1] : (subject || "");
  }
  function issuerCell(r) {
    const ca = r.issuer_ca ? '<span class="crt-sub">' + esc(r.issuer_ca.replace("-legacy", " (legacy)")) + "</span>" : "";
    return '<div class="crt-two"><span title="' + esc(r.issuer || "") + '">' + esc(r.issuer ? cn(r.issuer) : "\u2014") + "</span>" + ca + "</div>" +
      (r.flags && r.flags.length ? '<div class="crt-flags">' + flagPills(r.flags) + "</div>" : "");
  }
  function trustedNote(r) {
    const t = r.trusted;
    if (!t || !t.total) return "";
    const parts = [t.total + " trusted"];
    if (t.expired) parts.push('<b class="crt-bad">' + t.expired + " expired</b>");
    if (t.expiring) parts.push(t.expiring + " expiring");
    if (t.legacy) parts.push(t.legacy + " legacy CA");
    return '<span class="crt-sub crt-note">' + parts.join(" \u00B7 ") + "</span>";
  }
  function pseCell(r) {
    if (r.source !== "strust" || !r.pse_state) return '<span class="chk-dash">&mdash;</span>';
    const cls = { OK: "ok", DB_MISMATCH: "err", CHECK_FAILED: "err", MISSING: "muted", NOT_CHECKED: "muted" }[r.pse_state] || "muted";
    return '<span class="pill ' + cls + '" title="' + esc({ OK: "local PSE identical to the database copy", DB_MISMATCH: "local PSE differs from the database copy", CHECK_FAILED: "the PSE check reported an error", MISSING: "PSE not created (informational)", NOT_CHECKED: "no PSE check in the list (e.g. per-instance SSL server PSE)" }[r.pse_state] || "") + '">' +
      esc({ OK: "OK", DB_MISMATCH: "DB mismatch", CHECK_FAILED: "check failed", MISSING: "not created", NOT_CHECKED: "no check" }[r.pse_state] || r.pse_state) + "</span>";
  }

  function rowHtml(r) {
    const env = TIER_LABEL[tierOf(r)] || tierOf(r);
    const stale = r.error_type === "STALE_LIST" ? ' <span class="pill muted" title="' + esc(r.reason || "") + '">stale list</span>' : "";
    const reason = (["UNREACHABLE", "UNREADABLE", "UNKNOWN"].includes(r.state) && (r.reason || r.error_type))
      ? '<span class="crt-sub crt-reason">' + esc(r.reason || String(r.error_type).toLowerCase().replace(/_/g, " ")) + "</span>" : "";
    return '<tr class="crt-row" data-key="' + esc(r.inventory_key) + '">' +
      "<td>" + pill(r.state) + stale + "</td>" +
      '<td><span class="chk-sid">' + esc(who(r)) + '</span> <span class="crt-sub">' + esc(env) + "</span></td>" +
      '<td><div class="crt-two"><span class="chk-mono" title="' + esc(certId(r)) + '">' + esc(certId(r)) + '</span><span class="crt-sub">' + esc(SOURCE_LABEL[r.source] || r.source || "") + "</span></div></td>" +
      '<td><div class="crt-two"><span title="' + esc(r.subject || "") + '">' + esc(r.subject ? cn(r.subject) : "\u2014") + "</span>" +
      '<span class="chk-mono crt-sub" title="' + esc(r.endpoint || "") + '">' + esc(r.endpoint || "") + "</span>" + trustedNote(r) + reason + "</div></td>" +
      "<td>" + issuerCell(r) + "</td>" +
      "<td>" + expiryCell(r) + "</td><td>" + pseCell(r) + "</td>" +
      '<td class="chk-act"><button type="button" class="ghost crt-det" data-key="' + esc(r.inventory_key) + '" aria-label="Details: ' + esc(who(r) + " " + certId(r)) + '">Details</button></td></tr>';
  }

  function counts(rows) {
    const c = { red: 0, amber: 0, green: 0 };
    rows.forEach((r) => {
      if (r.state === "CRITICAL" || r.state === "EXPIRED") c.red += 1;
      else if (r.state === "WARN") c.amber += 1;
      else if (r.state === "OK") c.green += 1;
    });
    return c;
  }
  // the word is part of the badge: "1 1 6" told the state by colour alone
  function countBadges(rows) {
    const c = counts(rows);
    return (c.red ? '<span class="badge err">' + c.red + " red</span> " : "") + (c.amber ? '<span class="badge crt-amber">' + c.amber + " amber</span> " : "") +
      (c.green ? '<span class="badge ok">' + c.green + " green</span>" : "");
  }
  // Widths live in certs.css (col.c-*): fixed for status, expiry and PSE, the text columns share the rest.
  const COLS = ["st", "sys", "id", "subj", "iss", "exp", "pse", "act"];
  const HEAD = '<thead><tr><th scope="col">Status</th><th scope="col">System</th><th scope="col">Certificate</th><th scope="col">Subject / endpoint</th>' +
    '<th scope="col">Issuer / CA</th><th scope="col">Expires</th><th scope="col">PSE</th><th scope="col"><span class="chk-vh">Details</span></th></tr></thead>';
  const table = (inner) => '<table class="mini chk-table crt-table"><colgroup>' + COLS.map((c) => '<col class="c-' + c + '">').join("") + "</colgroup>" + HEAD + "<tbody>" + inner + "</tbody></table>";

  function sortRows(list) {
    const rank = { EXPIRED: 0, CRITICAL: 1, WARN: 2, UNREACHABLE: 3, UNREADABLE: 3, UNKNOWN: 4, OK: 5, MISSING: 6 };
    return list.slice().sort((a, b) => (a.days_left ?? 1e6) - (b.days_left ?? 1e6) || (rank[a.state] ?? 9) - (rank[b.state] ?? 9));
  }

  function groupedBySystem(list) {
    const groups = new Map();
    list.forEach((r) => { const k = who(r); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(r); });
    let html = "";
    Array.from(groups.keys()).sort((a, b) => {
      const ta = TIERS.indexOf(tierOf(groups.get(a)[0])), tb = TIERS.indexOf(tierOf(groups.get(b)[0]));
      return (ta < 0 ? 99 : ta) - (tb < 0 ? 99 : tb) || a.localeCompare(b);
    }).forEach((k) => {
      const rows = sortRows(groups.get(k));
      const shown = rows.filter((r) => r.state !== "MISSING");
      const missing = rows.filter((r) => r.state === "MISSING");
      const open = S.openMissing.has(k);
      html += '<tr class="crt-group"><td colspan="' + COLS.length + '"><b>' + esc(k) + '</b> <span class="crt-sub">' + esc(TIER_LABEL[tierOf(rows[0])] || "") +
        " \u00B7 " + plural(shown.length, "certificate") + "</span> " + countBadges(shown) +
        (missing.length ? ' <button type="button" class="ghost crt-miss" data-sys="' + esc(k) + '" aria-expanded="' + open + '">' + (open ? "hide" : "show") + " " + missing.length + " PSE" + (missing.length > 1 ? "s" : "") + " not created</button>" : "") +
        "</td></tr>";
      html += shown.map(rowHtml).join("") + (open ? missing.map(rowHtml).join("") : "");
    });
    return html;
  }

  function sectionHtml(cat, title, ic, sub, rows) {
    const inner = rows.length
      ? table(cat === "sap_abap" || cat === "non_sap" ? groupedBySystem(rows) : sortRows(rows).map(rowHtml).join(""))
      : '<p class="crt-empty">No certificates in the inventory for this group.</p>';
    // data-vt: the same section keeps its identity across renders, so it moves instead of blinking
    // (certs.css turns the attribute into a view-transition-name)
    return '<section class="crt-sec" data-cat="' + cat + '" data-vt="crt-sec-' + cat + '"><div class="crt-sec-head"><span class="crt-ic">' + icon(ic) + "</span><h3>" + esc(title) +
      '</h3><span class="crt-sub">(' + sub + ')</span><span class="rhs"><span class="crt-sub">' + plural(rows.filter((r) => r.state !== "MISSING").length, "certificate") +
      "</span> " + countBadges(rows) + "</span></div>" + inner + "</section>";
  }

  function summaryCard(sm) {
    const v = sm.verdict || "UNKNOWN";
    const vcls = { RED: "err", AMBER: "warn", GREEN: "ok", UNKNOWN: "muted" }[v] || "muted";
    const st = sm.states || {}, fl = sm.flags || {};
    const n = { expired: st.EXPIRED || 0, critical: st.CRITICAL || 0, due: st.WARN || 0, ok: st.OK || 0, unknown: sm.unknown || 0 };
    const text = n.expired + " expired, " + n.critical + " critical, " + n.due + " due within 30 days, " + n.ok + " OK, " + n.unknown + " not readable";
    const tile = (count, label, tone) => '<div class="crt-stat" data-tone="' + tone + '"' + (count ? "" : ' data-zero="true"') + "><b>" + esc(count) + "</b><span>" + label + "</span></div>";
    const seg = (count, tone) => count ? '<i data-tone="' + tone + '" style="flex-grow:' + count + '"></i>' : "";
    const urgent = (sm.urgent || []).map((u) => {
      const inner = '<span class="chk-days ' + daysCls(u.days_left) + '">' + (u.days_left < 0 ? "expired" : esc(u.days_left) + " d") + "</span> <b>" + esc(u.sid || "?") +
        '</b> <span class="chk-mono">' + esc(u.endpoint || "") + "</span>";
      return "<li>" + (u.key ? '<button type="button" class="crt-urg crt-det" data-key="' + esc(u.key) + '" title="Open details">' + inner + "</button>" : '<span class="crt-urg">' + inner + "</span>") + "</li>";
    }).join("") || "<li>None.</li>";
    const attn = [];
    if (fl.LEGACY_CA) attn.push(fl.LEGACY_CA + " served certificate" + (fl.LEGACY_CA > 1 ? "s" : "") + " from a legacy UniCERT CA &ndash; replace before end of 2026");
    if (fl.WRONG_CA) attn.push(fl.WRONG_CA + " with the wrong CA for the tier");
    if (fl.DB_MISMATCH) attn.push(fl.DB_MISMATCH + (fl.DB_MISMATCH > 1 ? " PSEs differ" : " PSE differs") + " from the database copy");
    if (sm.trusted_expired) attn.push(sm.trusted_expired + " expired certificate" + (sm.trusted_expired > 1 ? "s" : "") + " in STRUST trusted lists");
    if (sm.unknown) attn.push(sm.unknown + " certificate" + (sm.unknown > 1 ? "s" : "") + " could not be read (unreachable / unknown)");
    const next = [];
    if (st.EXPIRED || st.CRITICAL) next.push("Renew the red certificates first (expired or \u2264 7 days).");
    if (st.WARN) next.push("Plan the renewal of the amber certificates (\u2264 30 days).");
    if (fl.LEGACY_CA) next.push("Request replacements from the new Test / Production CA for the legacy-CA certificates.");
    if (sm.trusted_expired) next.push("Remove expired entries from the STRUST trusted lists.");
    if (sm.unknown) next.push("Check network access for the unreachable endpoints (UNKNOWN is never counted as OK).");
    return '<div class="card crt-card crt-summary" data-verdict="' + esc(v) + '"><div class="crt-card-head"><h3>' + icon("spark") + ' Summary &middot; certificates</h3><span class="crt-sub">deterministic &middot; AI insight follows (UI-4)</span></div>' +
      '<div class="crt-verdict"><span class="crt-verdict-lbl">Verdict</span><span class="pill ' + vcls + '">' + esc(v) + '</span><div class="crt-stats" role="group" aria-label="' + esc(text) + '">' +
      tile(n.expired, "expired", "err") + tile(n.critical, "critical &le; 7 d", "err") + tile(n.due, "due &le; 30 d", "warn") + tile(n.ok, "OK", "ok") + tile(n.unknown, "not readable", "unk") + "</div></div>" +
      '<div class="crt-statebar" aria-hidden="true">' + seg(n.expired + n.critical, "err") + seg(n.due, "warn") + seg(n.ok, "ok") + seg(n.unknown, "unk") + "</div>" +
      '<div class="crt-sum-cols"><div class="crt-sum-col"><h4>Most urgent</h4><ul class="crt-urgent">' + urgent + "</ul></div>" +
      '<div class="crt-sum-col"><h4>Needs attention</h4><ul>' + (attn.map((a) => "<li>" + a + "</li>").join("") || "<li>Nothing.</li>") + "</ul></div>" +
      '<div class="crt-sum-col"><h4>Next actions</h4><ol>' + (next.map((a) => "<li>" + esc(a) + "</li>").join("") || "<li>None.</li>") + "</ol></div></div></div>";
  }

  // certificates behind one bar - the same rule as outlook() in cert_routes.py
  function weekRows(all, i) {
    return all.filter((r) => Number.isInteger(r.days_left) && !GREY.includes(r.state) && r.days_left < OUTLOOK_DAYS && Math.floor(Math.max(0, r.days_left) / 7) === i)
      .sort((a, b) => a.days_left - b.days_left);
  }
  function outlookCard(buckets, all) {
    const max = Math.max(1, ...buckets.map((b) => b.red + b.amber + b.blue));
    const start = new Date();
    let pops = "";
    const cols = buckets.map((b, i) => {
      const d = new Date(start.getTime() + i * 7 * 86400000);
      const seg = (n, cls) => n ? '<span class="crt-seg ' + cls + '" style="height:' + (n / max * 100) + '%"></span>' : "";
      const total = b.red + b.amber + b.blue;
      const label = "week of " + DD.format(d) + ": " + plural(total, "certificate");
      const inner = '<span class="crt-val">' + (total || "") + '</span><span class="crt-stack">' + seg(b.blue, "blue") + seg(b.amber, "amber") + seg(b.red, "red") +
        '</span><span class="crt-lbl">' + (i % 2 ? "" : esc(DD.format(d))) + "</span>";
      const rows = total ? weekRows(all, i) : [];
      if (!rows.length || !HAS_POPOVER) return '<div class="crt-col" title="' + esc(label) + '">' + inner + "</div>";
      // A popover lists what is behind the bar. With interest invokers the browser opens it on hover, focus
      // and long-press; elsewhere a click opens it and the handlers at the end of this file add hover and
      // focus. CSS anchor positioning places it over the bar.
      const id = "crt-wk-" + i;
      pops += '<div class="crt-pop" id="' + id + '" ' + (HAS_HINT ? 'popover="hint"' : "popover") + ' style="position-anchor:--' + id + '"><p><b>Week of ' + esc(DD.format(d)) + "</b> &middot; " +
        plural(rows.length, "certificate") + "</p><ul>" + rows.slice(0, 8).map((r) => '<li><span class="chk-days ' + daysCls(r.days_left) + '">' + esc(r.days_left) + " d</span> <b>" + esc(who(r)) +
        '</b> <span class="chk-mono">' + esc(certId(r)) + "</span></li>").join("") + (rows.length > 8 ? '<li class="crt-sub">+ ' + (rows.length - 8) + " more</li>" : "") + "</ul></div>";
      return '<button type="button" class="crt-col" style="anchor-name:--' + id + '" ' + (HAS_INTEREST ? 'interestfor="' + id + '"' : 'popovertarget="' + id + '" popovertargetaction="show"') +
        ' aria-label="' + esc(label) + '">' + inner + "</button>";
    }).join("");
    return '<div class="card crt-card crt-outlook"><div class="crt-card-head"><h3>' + icon("cal") + ' Expiry outlook</h3><span class="crt-sub">certificates per week, next 13 weeks</span></div>' +
      '<div class="crt-bars">' + cols + "</div>" + pops +
      '<div class="crt-legend"><span><i class="red"></i>&le; 14 days</span><span><i class="amber"></i>&le; 30 days</span><span><i class="blue"></i>later</span></div></div>';
  }

  function pkiStrip(pki) {
    if (!pki) return '<div class="crt-pki"><b>' + icon("shield") + ' PKI (EJBCA)</b> <span class="crt-sub">no pki-check report stored yet &ndash; run the pki-check Job</span></div>';
    const p0 = (pki.p0 || []).map((p) => '<span class="pill ' + (p.outcome === "OK" ? "ok" : "err") + '" title="' + esc(p.layer || p.version || "") + '">' + esc(String(p.env || "").toUpperCase()) + " RA " + esc(p.outcome || "?") + "</span>").join(" ");
    const p1 = (pki.p1 || []).map((p) => '<span class="pill ' + (p.outcome === "OK" ? (p.days_left != null && p.days_left <= 30 ? "warn" : "ok") : p.outcome === "SKIPPED" ? "muted" : "err") + '" title="' + esc(p.error_type || p.layer || "") + '">' +
      esc(p.credential || p.aid || "?") + (p.days_left != null ? " \u00B7 " + esc(p.days_left) + " d" : "") + " " + esc(p.outcome || "") + "</span>").join(" ");
    return '<div class="crt-pki"><b>' + icon("shield") + " PKI (EJBCA)</b> " + p0 + " " + (p1 || '<span class="crt-sub">' + esc(pki.p1_note || "no AID credential configured") + "</span>") +
      ' <span class="crt-sub rhs">report ' + fmt(pki.created_at) + "</span></div>";
  }

  function toolbar(all) {
    const chips = ["all"].concat(SECTIONS.map((s) => s[0])).map((c) => {
      const n = c === "all" ? all.length : all.filter((r) => r.category === c).length;
      return '<button type="button" class="chk-chip crt-cat' + (S.cat === c ? " active" : "") + '" data-cat="' + c + '" aria-pressed="' + (S.cat === c) + '">' + esc(CHIP_LABEL[c]) + ' <span class="url-cnt">' + n + "</span></button>";
    }).join("");
    const tiers = TIERS.filter((t) => all.some((r) => tierOf(r) === t));
    const tierSel = '<select id="crt-tier" class="url-kind" aria-label="Environment"><option value="all">Environment: all</option>' +
      tiers.map((t) => '<option value="' + t + '"' + (S.tier === t ? " selected" : "") + ">" + esc(TIER_LABEL[t] || t) + "</option>").join("") + "</select>";
    return '<search class="chk-toolbar" aria-label="Filter certificates">' + chips + '<span class="rhs">' + tierSel +
      '<label class="chk-bad"><input type="checkbox" id="crt-due"' + (S.due ? " checked" : "") + "> only due</label>" +
      '<input type="search" id="crt-q" placeholder="Search system, subject, endpoint" aria-label="Search system, subject, endpoint" value="' + esc(S.q) + '" /></span></search>';
  }

  function matches(r) {
    if (S.tier !== "all" && tierOf(r) !== S.tier) return false;
    if (S.due && !DUE.has(r.state)) return false;
    const q = S.q.trim().toLowerCase();
    if (q && !(who(r) + " " + (r.subject || "") + " " + (r.endpoint || "") + " " + (r.issuer || "") + " " + certId(r)).toLowerCase().includes(q)) return false;
    return true;
  }

  function render() {
    const el = body();
    if (!el || !S.data) return;
    const all = S.data.certificates || [];
    freshness();
    const btn = document.getElementById("crt-run");
    if (btn) { btn.disabled = S.busy; btn.innerHTML = S.busy ? "&#x23F3; Starting&hellip;" : "&#x25B6; Refresh (scan now)"; }
    const notice = S.notice ? '<div class="chk-notice ' + esc(S.notice.cls) + '" role="status">' + esc(S.notice.text) + "</div>" : "";
    if (!all.length) {
      el.innerHTML = notice + '<div class="mon-placeholder">No certificates yet. The <code>cert-inventory</code> Job runs daily at 05:45 once it is deployed (admins can start it with Refresh).</div>' + pkiStrip(S.data.pki);
      return;
    }
    const top = '<div class="crt-top">' + summaryCard(S.data.summary || {}) + outlookCard(S.data.outlook || [], all) + "</div>";
    const shown = all.filter(matches);
    const secs = SECTIONS.filter((s) => S.cat === "all" || S.cat === s[0])
      .map(([c, t, i, sub]) => sectionHtml(c, t, i, sub, shown.filter((r) => r.category === c))).join("");
    el.innerHTML = notice + top + pkiStrip(S.data.pki) + toolbar(all) + secs + legend();
  }

  function legend() {
    return '<details class="chk-how"><summary>Where the data comes from</summary><ul>' +
      "<li><b>TLS</b>: once a day the <code>cert-inventory</code> Job does one TLS handshake per endpoint of the reviewed catalog and reads the certificate the endpoint serves (no login, no data sent).</li>" +
      "<li><b>HANA SQL</b>: the same handshake on every configured HANA SQL port (tenant and SYSTEMDB).</li>" +
      "<li><b>STRUST</b>: every PSE of an ABAP system from the newest list of the Basis job <code>SSF_ALERT_CERTEXPIRE</code> (weekly), read over RFC. A list older than 8 days is shown as UNKNOWN. The list has no issuer for own certificates, so CA flags come from the TLS rows.</li>" +
      "<li><b>Flags</b>: <i>legacy CA</i> = issued by a legacy UniCERT CA (replace before end of 2026); <i>wrong CA</i> = Test CA on production or Production CA elsewhere; <i>other CA</i> = not a company CA (e.g. a self-signed SAP certificate).</li>" +
      "<li><b>Grey</b> (UNREACHABLE, UNREADABLE, UNKNOWN, NOT CREATED) is never counted as OK. Read-only: nothing is requested, changed or installed here.</li>" +
      "</ul></details>";
  }

  // ---- drawer --------------------------------------------------------------------------------
  // #cert-panel is a <dialog> in the new template: showModal() traps the focus, closes on Esc, makes the
  // page behind inert and gives the focus back to the row that opened it. With the old <div hidden>
  // markup the same code falls back to the hidden attribute.
  function showPanel(p) { if (typeof p.showModal === "function") { if (!p.open) p.showModal(); } else { p.hidden = false; } }
  function hidePanel(p) { if (typeof p.close === "function") { if (p.open) p.close(); } else { p.hidden = true; } }

  async function openDrawer(key) {
    const panel = document.getElementById("cert-panel");
    const out = document.getElementById("cert-panel-body");
    if (!panel || !out) return;
    out.innerHTML = '<p class="empty">Loading&hellip;</p>';
    showPanel(panel);
    let data;
    try {
      data = await call("/api/certificates/item?key=" + encodeURIComponent(key));
    } catch (e) {
      out.innerHTML = '<div class="mon-placeholder" role="alert">Could not load: ' + esc(e.message) + "</div>";
      return;
    }
    const c = data.certificate || {};
    const kv = (k, v) => v == null || v === "" || (Array.isArray(v) && !v.length) ? "" : "<dt>" + esc(k) + "</dt><dd>" + v + "</dd>";
    const t = document.getElementById("cert-panel-title");
    if (t) t.textContent = who(c) + " \u00B7 " + certId(c);
    let html = '<p>' + pill(c.state) + " " + flagPills(c.flags) + "</p><dl class=\"crt-dl\">" +
      kv("Subject", esc(c.subject)) + kv("SANs", esc((c.sans || []).join(", "))) + kv("Issuer", esc(c.issuer)) +
      kv("Issuing CA", esc(c.issuer_ca)) + kv("Expected CA", esc(c.expected_ca)) + kv("Expires", esc(day(c.not_after)) + (c.days_left != null ? " (" + esc(c.days_left) + " days)" : "")) +
      kv("Key profile", esc(c.key_profile)) + kv("AID", esc(c.aid)) + kv("Endpoint", '<span class="chk-mono">' + esc(c.endpoint) + "</span>") +
      kv("Source", esc(SOURCE_LABEL[c.source] || c.source)) + kv("PSE state", c.pse_state ? pseCell(c) : "") + kv("List date", c.list_date ? fmt(c.list_date) : "") +
      kv("Reason", esc(c.reason || (c.error_type ? String(c.error_type).toLowerCase().replace(/_/g, " ") : ""))) + kv("Checked", fmt(c.checked_at)) + "</dl>";
    if ((c.compliance || []).length) {
      html += '<p><b>CL-R3 compliance</b> <span class="crt-sub">(informational until the migration)</span></p><ul>' + c.compliance.map((x) => "<li>" + esc(x) + "</li>").join("") + "</ul>";
    }
    const tr = data.trusted || [];
    if (tr.length) {
      html += "<p><b>Trusted list</b> <span class=\"crt-sub\">" + plural(tr.length, "certificate") + "</span></p>" +
        '<table class="mini crt-trusted"><thead><tr><th scope="col">Status</th><th scope="col">Subject</th><th scope="col">Expires</th><th scope="col">Days</th></tr></thead><tbody>' +
        tr.map((x) => "<tr" + (x.state === "EXPIRED" || (x.flags || []).length ? ' class="crt-hl"' : "") + "><td>" + pill(x.state) + "</td><td>" + esc(x.subject) + " " + flagPills(x.flags) +
          "</td><td>" + day(x.not_after) + "</td><td>" + daysCell(x) + "</td></tr>").join("") + "</tbody></table>";
    }
    out.innerHTML = html;
  }

  // ---- events --------------------------------------------------------------------------------
  document.addEventListener("click", (ev) => {
    if (ev.target.closest("#crt-run")) { runNow(); return; }
    if (ev.target.closest("#refresh-certs")) { S.notice = null; mount(); return; }
    // a click on the dialog itself (not on the sheet inside it) is a click on the dimmed page
    if (ev.target.closest("#cert-panel-close") || ev.target.id === "cert-panel") { const p = document.getElementById("cert-panel"); if (p) hidePanel(p); return; }
    const cat = ev.target.closest("#cert-body .crt-cat");
    if (cat) { S.cat = cat.dataset.cat; saveFilter(); update(render); return; }
    const miss = ev.target.closest("#cert-body .crt-miss");
    if (miss) { const k = miss.dataset.sys; if (S.openMissing.has(k)) S.openMissing.delete(k); else S.openMissing.add(k); update(render); return; }
    const det = ev.target.closest("#cert-body .crt-det") || ev.target.closest("#cert-body tr.crt-row");
    if (det && det.dataset.key) { openDrawer(det.dataset.key); }
  });
  document.addEventListener("keydown", (ev) => {
    // only for the old <div> drawer: a <dialog> closes on Esc by itself
    if (ev.key === "Escape") { const p = document.getElementById("cert-panel"); if (p && typeof p.showModal !== "function" && !p.hidden) p.hidden = true; }
  });
  document.addEventListener("change", (ev) => {
    if (ev.target && ev.target.id === "crt-tier") { S.tier = ev.target.value; saveFilter(); update(render); }
    if (ev.target && ev.target.id === "crt-due") { S.due = ev.target.checked; saveFilter(); update(render); }
  });
  document.addEventListener("input", (ev) => {
    if (ev.target && ev.target.id === "crt-q") {
      S.q = ev.target.value;
      saveFilter();
      const pos = ev.target.selectionStart;
      render();
      const again = document.getElementById("crt-q");
      if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (_) { /* search inputs */ } }
    }
  });
  // Browsers without interest invokers: the same hover / focus behaviour with four listeners.
  if (HAS_POPOVER && !HAS_INTEREST) {
    const target = (ev) => {
      const b = ev.target.closest ? ev.target.closest("#cert-body .crt-col[popovertarget]") : null;
      if (!b || (ev.relatedTarget && b.contains(ev.relatedTarget))) return null;   // moving inside the same bar
      return document.getElementById(b.getAttribute("popovertarget"));
    };
    const show = (ev) => { const p = target(ev); if (p && !p.matches(":popover-open")) p.showPopover(); };
    const hide = (ev) => { const p = target(ev); if (p && p.matches(":popover-open")) p.hidePopover(); };
    document.addEventListener("mouseover", show);
    document.addEventListener("mouseout", hide);
    document.addEventListener("focusin", show);
    document.addEventListener("focusout", hide);
  }
  // Browsers without CSS anchor positioning: place the popover over its bar by hand ("toggle" does not bubble).
  if (!HAS_ANCHOR) {
    document.addEventListener("toggle", (ev) => {
      const pop = ev.target;
      if (!(pop instanceof Element) || !pop.matches(".crt-pop") || ev.newState !== "open") return;
      const btn = document.querySelector('[popovertarget="' + pop.id + '"], [interestfor="' + pop.id + '"]');
      if (!btn) return;
      const b = btn.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
      pop.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, b.left + b.width / 2 - w / 2)) + "px";
      pop.style.top = (b.top - h - 8 < 8 ? b.bottom + 8 : b.top - h - 8) + "px";
    }, true);
  }

  window.CertsApp = { onShow, mount };
})();
