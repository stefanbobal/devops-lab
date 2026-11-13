// Monitoring > URLs pane (cert lifecycle S8): availability of every URL of the reviewed catalog, checked every
// 5 minutes by the read-only "url-check" Job (GET /api/urls). Admin "Check now" starts that Job
// (POST /api/urls/run). Certificate days come from the daily "cert-inventory" scan. A row with no fresh
// check is UNKNOWN, never UP. Reuses the chk-* classes of the Checks pane. Exposes window.UrlsApp.
//
// "Next level" build (design export 2026-11). Same data contract, same element IDs, still read-only.
// What changed against urls.js, each with its reason:
//   - View Transitions for chips / select               -> tiles and tier tables move instead of blinking
//   - KPI tiles carry data-tone / data-zero             -> "Down 1" can be loud and "Down 0" quiet (CSS cannot read numbers)
//   - table: 8 columns with <col class>, not 10 with %  -> service = kind + access, response = HTTP code + time
//   - relative times in <time>, refreshed every 30 s    -> "last up 25 min ago" answers the on-call question directly
//   - "last check" chip with age and data-age           -> a dead url-check job is visible
//   - inline SVG icons, aria-pressed, <search>, role=status
(function () {
  "use strict";

  const STORE_KEY = "sapops-urls-filter";
  const saved = (() => { try { return JSON.parse(sessionStorage.getItem(STORE_KEY) || "{}"); } catch (_) { return {}; } })();
  const S = { data: null, tier: saved.tier || "all", status: saved.status || "all", kind: saved.kind || "all",
              q: saved.q || "", timer: null, ticker: null, notice: null, busy: false };
  const TIERS = ["production", "preproduction", "simulation", "development", "sandbox", "service_zone", "infrastructure"];
  const TIER_LABEL = { production: "Production", preproduction: "Pre-production", simulation: "Simulation",
    development: "Development", sandbox: "Sandbox", service_zone: "Service zone", infrastructure: "Infrastructure" };
  const KIND_LABEL = { webgui: "WebGUI", fiori: "Fiori Launchpad", java_start: "Java start page", java_nwa: "Java NWA",
    bobj_cmc: "BOBJ CMC", cloud_connector: "Cloud Connector", hana_cockpit: "HANA Cockpit",
    hana_cockpit_manager: "HANA Cockpit Manager", onapsis: "Onapsis", sac: "SAP Analytics Cloud", start_page: "Start page" };
  const ACCESS_LABEL = { instance_pas: "PAS", instance_aas: "AAS", instance: "Instance", f5: "F5 LB",
    web_dispatcher: "Web Dispatcher", gclb: "GCLB", saas: "SaaS", lb: "Load balancer" };
  const VERDICT_CLS = { UP: "ok", DOWN: "err", UNREACHABLE: "muted", UNKNOWN: "muted" };
  const STATUS_CHIPS = [["all", "All"], ["notup", "Not UP"], ["UP", "UP"], ["DOWN", "DOWN"], ["UNREACHABLE", "Unreachable"], ["UNKNOWN", "Unknown"]];
  const REFRESH_MS = 5 * 60 * 1000;
  const TICK_MS = 30 * 1000;
  const LATE_MIN = 10;   // two missed 5-minute runs = overdue; stale_minutes (15) from the API = stale
  const DTT = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v) => { if (!v) return "\u2014"; const d = new Date(v); return isNaN(d) ? esc(v) : esc(DTT.format(d).replace(",", "")); };
  const body = () => document.getElementById("url-body");
  const tierOf = (r) => String(r.tier || "").toLowerCase();

  // ---- progressive enhancement -----------------------------------------------------------------
  const HAS_VT = typeof document.startViewTransition === "function";
  const REDUCED = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  // Discrete changes (chips, select) move and cross-fade in a View Transition. Typing and the
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
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    alert: '<path d="M12 4.5 3.5 19h17z"/><path d="M12 10v4.5M12 16.9v.1"/>',
    help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.6a2.5 2.5 0 1 1 3.6 2.2c-.8.5-1.2 1-1.2 1.9M12 16.6v.1"/>',
    lock: '<rect x="5" y="10.5" width="14" height="9.5" rx="2.5"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
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

  function paneVisible() { const p = document.querySelector('[data-pane="urls"]'); return p && !p.hidden; }
  function saveFilter() {
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify({ tier: S.tier, status: S.status, kind: S.kind, q: S.q })); } catch (_) { /* private mode */ }
  }
  function onShow() { mount(); }

  async function mount() {
    const el = body();
    if (!el) return;
    if (!S.data) el.innerHTML = '<p class="empty">Loading&hellip;</p>';
    try {
      S.data = await call("/api/urls");
    } catch (e) {
      el.innerHTML = '<div class="mon-placeholder" role="alert">Could not load the URLs: ' + esc(e.message) + "</div>";
      return;
    }
    render();
    clearTimeout(S.timer);
    S.timer = setTimeout(() => { if (paneVisible()) mount(); }, REFRESH_MS);
    if (!S.ticker) S.ticker = setInterval(tick, TICK_MS);
  }

  async function runNow() {
    if (S.busy) return;
    S.busy = true;
    render();
    try {
      await call("/api/urls/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      S.notice = { cls: "info", text: "Check started \u2013 new results in about 1 minute. Press Refresh then." };
    } catch (e) {
      S.notice = { cls: "err", text: "Could not start the check: " + e.message };
    }
    S.busy = false;
    render();
  }

  // ---- time ------------------------------------------------------------------------------------
  function ago(v) {
    const t = new Date(v).getTime();
    if (!v || isNaN(t)) return "";
    const m = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    const h = Math.round(m / 60);
    return h < 48 ? h + " h ago" : Math.round(h / 24) + " d ago";
  }
  // relative time for the eye, exact time in the tooltip and in datetime=""; tick() keeps the text true
  const rel = (v) => '<time datetime="' + esc(v) + '" data-rel title="' + fmt(v) + '">' + esc(ago(v)) + "</time>";
  // "Last check" chip: time, age, and a state (data-age) the CSS turns into a dot. A check that is overdue
  // also says so in words - stale data must never look like fresh data.
  function freshness() {
    const last = document.getElementById("url-last");
    if (!last || !S.data) return;
    const t = S.data.last_checked ? new Date(S.data.last_checked).getTime() : NaN;
    if (isNaN(t)) { last.dataset.age = "unknown"; last.innerHTML = "every 5 min"; return; }
    const min = (Date.now() - t) / 60000;
    const age = min > (S.data.stale_minutes || 15) ? "stale" : min > LATE_MIN ? "late" : "fresh";
    last.dataset.age = age;
    last.innerHTML = "Last check <b>" + fmt(S.data.last_checked) + '</b> <span class="chk-ago">' + esc(ago(S.data.last_checked)) + "</span>" +
      (age === "fresh" ? "" : ' <b class="chk-age-word">' + (age === "stale" ? "stale" : "overdue") + "</b>") + " &middot; every 5 min";
  }
  function tick() {
    if (!paneVisible() || !S.data) return;
    document.querySelectorAll("#url-body time[data-rel]").forEach((t) => { t.textContent = ago(t.dateTime); });
    freshness();
  }

  // ---- rendering -----------------------------------------------------------------------------
  function matches(r) {
    if (S.tier !== "all" && tierOf(r) !== S.tier) return false;
    if (S.kind !== "all" && r.kind !== S.kind) return false;
    if (S.status === "notup" && r.verdict === "UP") return false;
    if (S.status !== "all" && S.status !== "notup" && r.verdict !== S.status) return false;
    const q = S.q.trim().toLowerCase();
    if (q && !(String(r.sid || r.system || "") + " " + String(r.url || "") + " " + String(r.kind || "")).toLowerCase().includes(q)) return false;
    return true;
  }

  function kpis(rows) {
    const n = { UP: 0, DOWN: 0, UNREACHABLE: 0, UNKNOWN: 0 };
    rows.forEach((r) => { n[r.verdict] = (n[r.verdict] || 0) + 1; });
    const certWarn = rows.filter((r) => r.cert_days != null && r.cert_days <= 30).length;
    // data-tone says what the number means, data-zero that there is nothing to report: the CSS needs both
    const tile = (i, tone, cls, ic, label, val, sub) => '<div class="kpi" data-tone="' + tone + '"' + (val ? "" : ' data-zero="true"') + ' data-vt="url-kpi-' + i + '">' +
      '<div class="k-top"><span class="k-ic ' + cls + '">' + icon(ic) + "</span> " + label + '</div><div class="k-val">' + val + '</div><div class="k-sub">' + sub + "</div></div>";
    return '<div class="kpis">' +
      tile(1, "info", "b", "link", "URLs", rows.length, "from the reviewed catalog") +
      tile(2, "ok", "g", "check", "Up", n.UP, "2xx / 3xx / 401 / 403") +
      tile(3, "err", "r", "alert", "Down", n.DOWN, "answered with an error code") +
      tile(4, "unk", "u", "help", "Unreachable / unknown", n.UNREACHABLE + n.UNKNOWN, "no answer or no fresh check &ndash; never counted as up") +
      tile(5, "warn", "o", "lock", "Certificate &le; 30 d", certWarn, "served certificate expiring") +
      "</div>";
  }

  function toolbar(rows) {
    const present = new Set(rows.map(tierOf));
    const tierChips = [["all", "All"]].concat(TIERS.filter((t) => present.has(t)).map((t) => [t, TIER_LABEL[t] || t]))
      .map(([v, l]) => '<button type="button" class="chk-chip url-tier' + (S.tier === v ? " active" : "") + '" data-tier="' + esc(v) + '" aria-pressed="' + (S.tier === v) + '">' + esc(l) + "</button>").join("");
    const statusChips = STATUS_CHIPS.map(([v, l]) => {
      const cnt = v === "all" ? rows.length : v === "notup" ? rows.filter((r) => r.verdict !== "UP").length : rows.filter((r) => r.verdict === v).length;
      return '<button type="button" class="chk-chip url-status' + (S.status === v ? " active" : "") + '" data-status="' + esc(v) + '" aria-pressed="' + (S.status === v) + '">' + esc(l) + ' <span class="url-cnt">' + cnt + "</span></button>";
    }).join("");
    const kinds = Array.from(new Set(rows.map((r) => r.kind).filter(Boolean))).sort();
    const kindSel = '<select id="url-kind" class="url-kind" aria-label="Kind"><option value="all">All kinds</option>' +
      kinds.map((k) => '<option value="' + esc(k) + '"' + (S.kind === k ? " selected" : "") + ">" + esc(KIND_LABEL[k] || k) + "</option>").join("") + "</select>";
    return '<search class="chk-toolbar" aria-label="Filter by tier"><span class="subtle">Tier:</span>' + tierChips + "</search>" +
      '<search class="chk-toolbar" aria-label="Filter by status, kind and text"><span class="subtle">Status:</span>' + statusChips +
      '<span class="rhs">' + kindSel + '<input type="search" id="url-q" placeholder="Filter system / URL" aria-label="Filter system / URL" value="' + esc(S.q) + '" /></span></search>';
  }

  function certCell(r) {
    if (!/^https:/i.test(r.url || "") || r.cert_state == null && r.cert_days == null) {
      return '<span class="chk-dash" title="' + (/^https:/i.test(r.url || "") ? "no certificate result yet (daily scan)" : "HTTP only") + '">&mdash;</span>';
    }
    if (r.cert_days == null) {
      return '<span class="pill muted" title="' + esc(r.cert_state || "") + '">' + esc(r.cert_state || "?") + "</span>";
    }
    const d = r.cert_days;
    const flags = (r.cert_flags || []).map((f) => ({ LEGACY_CA: "legacy CA", WRONG_CA: "wrong CA", OTHER_CA: "other CA" }[f] || f));
    const flagHtml = flags.length ? ' <span class="pill warn" title="' + esc((r.cert_flags || []).join(", ")) + '">' + esc(flags.join(", ")) + "</span>" : "";
    return '<span class="chk-days ' + (d <= 7 ? "err" : d <= 30 ? "warn" : "ok") + '" title="' + esc(r.cert_state || "") + '">' + esc(d) + " d</span>" + flagHtml;
  }

  function downCell(r) {
    if (r.verdict === "UP") return '<span class="chk-dash">&mdash;</span>';
    const n = r.fail_count || 0;
    return '<div class="url-two url-down"><span>' + (r.last_up_at ? "last up " + rel(r.last_up_at) : "never seen up") + "</span>" +
      (n ? '<span class="url-sub">' + n + "\u00D7 in a row</span>" : "") + "</div>";
  }

  // code and time are one answer ("302 in 41 ms"); without a code the error text takes its place
  function responseCell(r) {
    const ms = r.latency_ms == null ? "" : ' <span class="url-sub">' + esc(Math.round(r.latency_ms)) + " ms</span>";
    if (r.http_status == null) {
      return '<span class="url-err" title="' + esc(r.error_type || "") + '">' + esc(r.error_type ? r.error_type.toLowerCase().replace(/_/g, " ") : "\u2014") + "</span>" + (r.error_type ? "" : ms);
    }
    return '<span class="url-code">' + esc(r.http_status) + "</span>" + ms;
  }

  function rowHtml(r) {
    const who = r.sid || r.system || "?";
    const pill = '<span class="pill ' + (VERDICT_CLS[r.verdict] || "muted") + '" title="' +
      esc(r.stale ? "no check in the last " + (S.data.stale_minutes || 15) + " min (last result: " + (r.last_verdict || "-") + ")" : (r.error_type || r.verdict)) + '">' + esc(r.verdict) + "</span>";
    const access = ACCESS_LABEL[r.access] || r.access || "";
    const gclb = r.access === "gclb" ? ' <span class="badge b-rise" title="RISE system reached through the GCLB">RISE</span>' : "";
    const href = /^https?:\/\//i.test(r.url || "") ? esc(r.url) : "#";
    const kind = KIND_LABEL[r.kind] || r.kind || "";
    const checked = (r.checked_at ? rel(r.checked_at) : "\u2014") + (r.stale ? ' <span class="pill muted" title="no check in the last ' + esc(S.data.stale_minutes || 15) + ' min">stale</span>' : "");
    return "<tr><td>" + pill + '</td><td class="chk-sid" title="' + esc(who) + '">' + esc(who) + "</td>" +
      '<td><div class="url-two"><span title="' + esc(kind) + '">' + esc(kind) + '</span><span class="url-sub">' + esc(access) + gclb + "</span></div></td>" +
      '<td class="chk-mono url-link"><a href="' + href + '" target="_blank" rel="noopener noreferrer" title="' + esc(r.url) + '">' + esc(r.url) + "</a></td>" +
      '<td class="url-wrap">' + responseCell(r) + '</td><td class="url-wrap">' + certCell(r) + '</td><td class="url-wrap">' + downCell(r) + '</td><td class="url-wrap">' + checked + "</td></tr>";
  }

  // Widths live in urls.css (col.c-*): fixed for everything with a known size, the URL takes the rest.
  const COLS = ["st", "sys", "svc", "url", "resp", "cert", "down", "chk"];
  const HEAD = "<thead><tr>" + ["Status", "System", "Service", "URL", "Response", "Cert", "Down since", "Checked"].map((h) => '<th scope="col">' + h + "</th>").join("") + "</tr></thead>";

  function tables(rows) {
    const rank = { DOWN: 0, UNREACHABLE: 1, UNKNOWN: 2, UP: 3 };
    let html = "";
    TIERS.concat([""]).forEach((tier) => {
      const list = rows.filter((r) => (tier ? tierOf(r) === tier : !TIERS.includes(tierOf(r))));
      if (!list.length) return;
      list.sort((a, b) => (rank[a.verdict] ?? 9) - (rank[b.verdict] ?? 9) || String(a.sid || a.system).localeCompare(String(b.sid || b.system)) || String(a.url).localeCompare(String(b.url)));
      const bad = list.filter((r) => r.verdict !== "UP").length;
      html += '<div class="chk-env">' + esc(TIER_LABEL[tier] || "Other") + ' <span class="badge muted">' + list.length + "</span>" +
        (bad ? ' <span class="badge err">' + bad + " not up</span>" : "") + "</div>";
      // data-vt: the same tier table keeps its identity across renders, so it moves instead of blinking
      html += '<table class="mini chk-table url-table" data-vt="url-tier-' + (tier || "other") + '"><colgroup>' + COLS.map((c) => '<col class="c-' + c + '">').join("") +
        "</colgroup>" + HEAD + "<tbody>" + list.map(rowHtml).join("") + "</tbody></table>";
    });
    return html;
  }

  function legend() {
    return '<details class="chk-how"><summary>What is checked and how</summary><ul>' +
      "<li><b>Source:</b> the reviewed URL catalog (<code>cert_url_catalog.json</code>) &ndash; every URL of the operator&rsquo;s landscape list plus the admin endpoints SAITron already knows.</li>" +
      "<li><b>Every 5 minutes</b> the <code>url-check</code> Job sends one <code>GET</code> per URL from the SZ VPC: no login, no POST, redirects are not followed, the page is not downloaded.</li>" +
      "<li><b>UP</b> = HTTP 2xx / 3xx or 401 / 403 (the service answers a login challenge). <b>DOWN</b> = any other HTTP code. <b>UNREACHABLE</b> = no answer (DNS, timeout, refused, TLS error) &ndash; a network problem is not &ldquo;system down&rdquo;. <b>UNKNOWN</b> = no check in the last 15 minutes or not probed from SZ.</li>" +
      "<li><b>Cert</b> = days left of the certificate the URL serves, from the daily certificate scan (05:45). HTTP-only and SaaS URLs have none.</li>" +
      "<li>RISE systems marked <i>RISE</i> are reached through the GCLB; their Web Dispatchers are covered by the GCLB pane.</li>" +
      "</ul></details>";
  }

  function render() {
    const el = body();
    if (!el || !S.data) return;
    const all = S.data.urls || [];
    freshness();
    const btn = document.getElementById("url-run");
    if (btn) { btn.disabled = S.busy; btn.innerHTML = S.busy ? "&#x23F3; Starting&hellip;" : "&#x25B6; Check now"; }
    const notice = S.notice ? '<div class="chk-notice ' + esc(S.notice.cls) + '" role="status">' + esc(S.notice.text) + "</div>" : "";
    if (!all.length) {
      el.innerHTML = notice + '<div class="mon-placeholder">No URL results yet. The <code>url-check</code> Job runs every 5 minutes once it is deployed.</div>' + legend();
      return;
    }
    const shown = all.filter(matches);
    const t = tables(shown);
    el.innerHTML = notice + kpis(all) + toolbar(all) + (t || '<div class="mon-placeholder">No URLs match the filter.</div>') + legend();
  }

  // ---- events --------------------------------------------------------------------------------
  document.addEventListener("click", (ev) => {
    if (ev.target.closest("#url-run")) { runNow(); return; }
    if (ev.target.closest("#refresh-urls")) { S.notice = null; mount(); return; }
    const tier = ev.target.closest("#url-body .url-tier");
    if (tier) { S.tier = tier.dataset.tier; saveFilter(); update(render); return; }
    const st = ev.target.closest("#url-body .url-status");
    if (st) { S.status = st.dataset.status; saveFilter(); update(render); }
  });
  document.addEventListener("change", (ev) => {
    if (ev.target && ev.target.id === "url-kind") { S.kind = ev.target.value; saveFilter(); update(render); }
  });
  document.addEventListener("input", (ev) => {
    if (ev.target && ev.target.id === "url-q") {
      S.q = ev.target.value;
      saveFilter();
      const pos = ev.target.selectionStart;
      render();
      const again = document.getElementById("url-q");
      if (again) { again.focus(); try { again.setSelectionRange(pos, pos); } catch (_) { /* search inputs */ } }
    }
  });

  window.UrlsApp = { onShow, mount };
})();
