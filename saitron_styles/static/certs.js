// Monitoring > Certificates pane (cert lifecycle S7, UI-1, read-only). Layout after docs/cert-lifecycle/ui-mockup.jpeg
// (layout only - all names come from the inventory): summary card + 13-week expiry outlook, PKI status strip, filter
// bar, six section cards (SAP ABAP, SAP Java, Web Dispatcher, BOBJ, GCLB, Non-SAP), detail drawer. Data from
// GET /api/certificates (+ /item for the drawer); admin Refresh starts the cert-inventory Job. Renewal columns and
// actions come with UI-2. UNKNOWN / UNREACHABLE / UNREADABLE are grey, never green. Exposes window.CertsApp.
(function () {
  "use strict";

  const STORE_KEY = "sapops-certs-filter";
  const saved = (() => { try { return JSON.parse(sessionStorage.getItem(STORE_KEY) || "{}"); } catch (_) { return {}; } })();
  const S = { data: null, cat: saved.cat || "all", tier: saved.tier || "all", due: !!saved.due, q: saved.q || "",
              openMissing: new Set(), notice: null, busy: false };
  const SECTIONS = [
    ["sap_abap", "SAP ABAP systems", "&#x1F5C4;", "served TLS certificates (ICM, F5, Web Dispatcher) \u00B7 HANA SQL \u00B7 every STRUST PSE from the SSF_ALERT_CERTEXPIRE list"],
    ["sap_java", "SAP Java systems", "&#x2615;", "TLS on the Java ports \u00B7 HANA SQL"],
    ["web_dispatcher", "SAP Web Dispatcher", "&#x1F500;", "monitoring only \u00B7 TLS check \u00B7 RISE Web Dispatchers are covered by the GCLB pane"],
    ["bobj", "BOBJ", "&#x1F4CA;", "CMC behind the F5 \u00B7 TLS check"],
    ["gclb", "Google Cloud load balancers (GCLB)", "&#x2601;", "front-end certificates \u00B7 see the GCLB pane"],
    ["non_sap", "Non-SAP certificates", "&#x1F9E9;", "grouped by system"],
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
  const DT = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  const DD = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "2-digit", month: "short" });
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v) => { if (!v) return "\u2014"; const d = new Date(v); return isNaN(d) ? esc(v) : esc(DT.format(d).replace(",", "")); };
  const day = (v) => { if (!v) return "\u2014"; return esc(String(v).slice(0, 10)); };
  const body = () => document.getElementById("cert-body");
  const tierOf = (r) => String(r.tier || "").toLowerCase();
  const who = (r) => r.sid || r.system || "?";

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
  function onShow() { mount(); }

  async function mount() {
    const el = body();
    if (!el) return;
    if (!S.data) el.innerHTML = '<p class="empty">Loading&hellip;</p>';
    try {
      S.data = await call("/api/certificates");
    } catch (e) {
      el.innerHTML = '<div class="mon-placeholder">Could not load the certificates: ' + esc(e.message) + "</div>";
      return;
    }
    render();
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
  function pill(state) {
    const [cls, txt] = STATE_PILL[state] || ["muted", state || "?"];
    return '<span class="pill ' + cls + ' crt-pill">' + esc(txt) + "</span>";
  }
  function daysCell(r) {
    const d = r.days_left;
    if (d == null || ["UNREACHABLE", "UNREADABLE", "UNKNOWN", "MISSING"].includes(r.state)) {
      return '<span class="chk-dash" title="' + esc(r.reason || r.error_type || "") + '">&mdash;</span>';
    }
    return '<span class="chk-days ' + (d <= 7 ? "err" : d <= 30 ? "warn" : "ok") + '">' + esc(d) + "</span>";
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
    return '<span class="crt-sub">' + parts.join(" \u00B7 ") + "</span>";
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
      '<td class="chk-mono" title="' + esc(certId(r)) + '">' + esc(certId(r)) + "</td>" +
      '<td><div class="crt-two"><span title="' + esc(r.subject || "") + '">' + esc(r.subject ? cn(r.subject) : "\u2014") + "</span>" +
      '<span class="chk-mono crt-sub" title="' + esc(r.endpoint || "") + '">' + esc(r.endpoint || "") + "</span>" + trustedNote(r) + reason + "</div></td>" +
      "<td>" + issuerCell(r) + "</td>" +
      "<td>" + day(r.not_after) + "</td><td>" + daysCell(r) + "</td>" +
      "<td>" + esc(SOURCE_LABEL[r.source] || r.source || "") + "</td><td>" + pseCell(r) + "</td>" +
      '<td class="chk-act"><button type="button" class="ghost crt-det" data-key="' + esc(r.inventory_key) + '">Details</button></td></tr>';
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
  function countBadges(rows) {
    const c = counts(rows);
    return (c.red ? '<span class="badge err">' + c.red + "</span> " : "") + (c.amber ? '<span class="badge crt-amber">' + c.amber + "</span> " : "") +
      (c.green ? '<span class="badge ok">' + c.green + "</span>" : "");
  }
  const HEAD = "<thead><tr><th>Status</th><th>System</th><th>Certificate</th><th>Subject / endpoint</th><th>Issuer / CA</th><th>Expires</th><th>Days left</th><th>Source</th><th>PSE</th><th></th></tr></thead>";
  const COLS = ["9%", "8%", "11%", "20%", "15%", "8%", "5%", "7%", "11%", "6%"];
  const table = (inner) => '<table class="mini chk-table crt-table"><colgroup>' + COLS.map((w) => '<col style="width:' + w + '">').join("") + "</colgroup>" + HEAD + "<tbody>" + inner + "</tbody></table>";

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
      html += '<tr class="crt-group"><td colspan="10">&#x25BE; <b>' + esc(k) + '</b> <span class="crt-sub">' + esc(TIER_LABEL[tierOf(rows[0])] || "") +
        " \u00B7 " + shown.length + " " + (shown.length === 1 ? "certificate" : "certificates") + "</span> " + countBadges(shown) +
        (missing.length ? ' <button type="button" class="ghost crt-miss" data-sys="' + esc(k) + '">' + (open ? "hide" : "show") + " " + missing.length + " PSE" + (missing.length > 1 ? "s" : "") + " not created</button>" : "") +
        "</td></tr>";
      html += shown.map(rowHtml).join("") + (open ? missing.map(rowHtml).join("") : "");
    });
    return html;
  }

  function sectionHtml(cat, title, icon, sub, rows) {
    const inner = rows.length
      ? table(cat === "sap_abap" || cat === "non_sap" ? groupedBySystem(rows) : sortRows(rows).map(rowHtml).join(""))
      : '<p class="crt-empty">No certificates in the inventory for this group.</p>';
    return '<section class="crt-sec" data-cat="' + cat + '"><div class="crt-sec-head"><span class="crt-ic">' + icon + "</span><h3>" + esc(title) +
      '</h3><span class="crt-sub">(' + sub + ')</span><span class="rhs"><span class="crt-sub">' + rows.filter((r) => r.state !== "MISSING").length +
      " certificates</span> " + countBadges(rows) + "</span></div>" + inner + "</section>";
  }

  function summaryCard(sm, rows) {
    const v = sm.verdict || "UNKNOWN";
    const vcls = { RED: "err", AMBER: "warn", GREEN: "ok", UNKNOWN: "muted" }[v] || "muted";
    const st = sm.states || {}, fl = sm.flags || {};
    const urgent = (sm.urgent || []).map((u) => "<li><b>" + esc(u.sid || "?") + "</b> " + esc(u.endpoint || "") + " &ndash; " +
      (u.days_left < 0 ? "expired " + esc(-u.days_left) + " d ago" : "expires in " + esc(u.days_left) + " d") + "</li>").join("") || "<li>None.</li>";
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
    return '<div class="card crt-card crt-summary"><div class="crt-card-head"><h3>&#x2728; Summary &middot; certificates</h3><span class="crt-sub">deterministic &middot; AI insight follows (UI-4)</span></div>' +
      '<p><b>Verdict</b> <span class="pill ' + vcls + '">' + esc(v) + "</span> " + esc((st.EXPIRED || 0) + " expired, " + (st.CRITICAL || 0) + " critical, " + (st.WARN || 0) + " due within 30 days, " + (st.OK || 0) + " OK") + "</p>" +
      "<p><b>Most urgent</b></p><ul>" + urgent + "</ul>" +
      "<p><b>Needs attention</b></p><ul>" + (attn.map((a) => "<li>" + a + "</li>").join("") || "<li>Nothing.</li>") + "</ul>" +
      "<p><b>Next actions</b></p><ol>" + (next.map((a) => "<li>" + esc(a) + "</li>").join("") || "<li>None.</li>") + "</ol></div>";
  }

  function outlookCard(buckets) {
    const max = Math.max(1, ...buckets.map((b) => b.red + b.amber + b.blue));
    const start = new Date();
    const cols = buckets.map((b, i) => {
      const d = new Date(start.getTime() + i * 7 * 86400000);
      const seg = (n, cls) => n ? '<div class="crt-seg ' + cls + '" style="height:' + (n / max * 100) + '%" title="' + n + '"></div>' : "";
      const total = b.red + b.amber + b.blue;
      return '<div class="crt-col" title="week of ' + esc(DD.format(d)) + ": " + total + ' certificate(s)"><span class="crt-val">' + (total || "") + '</span><div class="crt-stack">' +
        seg(b.blue, "blue") + seg(b.amber, "amber") + seg(b.red, "red") + '</div><span class="crt-lbl">' + (i % 2 ? "" : esc(DD.format(d))) + "</span></div>";
    }).join("");
    return '<div class="card crt-card crt-outlook"><div class="crt-card-head"><h3>&#x1F4C5; Expiry outlook</h3><span class="crt-sub">certificates per week, next 13 weeks</span></div>' +
      '<div class="crt-bars">' + cols + "</div>" +
      '<div class="crt-legend"><span><i class="red"></i>&le; 14 days</span><span><i class="amber"></i>&le; 30 days</span><span><i class="blue"></i>later</span></div></div>';
  }

  function pkiStrip(pki) {
    if (!pki) return '<div class="crt-pki"><b>PKI (EJBCA)</b> <span class="crt-sub">no pki-check report stored yet &ndash; run the pki-check Job</span></div>';
    const p0 = (pki.p0 || []).map((p) => '<span class="pill ' + (p.outcome === "OK" ? "ok" : "err") + '" title="' + esc(p.layer || p.version || "") + '">' + esc(String(p.env || "").toUpperCase()) + " RA " + esc(p.outcome || "?") + "</span>").join(" ");
    const p1 = (pki.p1 || []).map((p) => '<span class="pill ' + (p.outcome === "OK" ? (p.days_left != null && p.days_left <= 30 ? "warn" : "ok") : p.outcome === "SKIPPED" ? "muted" : "err") + '" title="' + esc(p.error_type || p.layer || "") + '">' +
      esc(p.credential || p.aid || "?") + (p.days_left != null ? " \u00B7 " + esc(p.days_left) + " d" : "") + " " + esc(p.outcome || "") + "</span>").join(" ");
    return '<div class="crt-pki"><b>PKI (EJBCA)</b> ' + p0 + " " + (p1 || '<span class="crt-sub">' + esc(pki.p1_note || "no AID credential configured") + "</span>") +
      ' <span class="crt-sub rhs">report ' + fmt(pki.created_at) + "</span></div>";
  }

  function toolbar(all) {
    const chips = ["all"].concat(SECTIONS.map((s) => s[0])).map((c) => {
      const n = c === "all" ? all.length : all.filter((r) => r.category === c).length;
      return '<button type="button" class="chk-chip crt-cat' + (S.cat === c ? " active" : "") + '" data-cat="' + c + '">' + esc(CHIP_LABEL[c]) + ' <span class="url-cnt">' + n + "</span></button>";
    }).join("");
    const tiers = TIERS.filter((t) => all.some((r) => tierOf(r) === t));
    const tierSel = '<select id="crt-tier" class="url-kind"><option value="all">Environment: all</option>' +
      tiers.map((t) => '<option value="' + t + '"' + (S.tier === t ? " selected" : "") + ">" + esc(TIER_LABEL[t] || t) + "</option>").join("") + "</select>";
    return '<div class="chk-toolbar">' + chips + '<span class="rhs">' + tierSel +
      '<label class="chk-bad"><input type="checkbox" id="crt-due"' + (S.due ? " checked" : "") + "> only due</label>" +
      '<input type="search" id="crt-q" placeholder="Search system, subject, endpoint" value="' + esc(S.q) + '" /></span></div>';
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
    const last = document.getElementById("crt-last");
    if (last) last.innerHTML = S.data.last_checked ? "Last scan <b>" + fmt(S.data.last_checked) + "</b> &middot; daily 05:45" : "daily 05:45";
    const btn = document.getElementById("crt-run");
    if (btn) { btn.disabled = S.busy; btn.innerHTML = S.busy ? "&#x23F3; Starting&hellip;" : "&#x25B6; Refresh (scan now)"; }
    const notice = S.notice ? '<div class="chk-notice ' + esc(S.notice.cls) + '">' + esc(S.notice.text) + "</div>" : "";
    if (!all.length) {
      el.innerHTML = notice + '<div class="mon-placeholder">No certificates yet. The <code>cert-inventory</code> Job runs daily at 05:45 once it is deployed (admins can start it with Refresh).</div>' + pkiStrip(S.data.pki);
      return;
    }
    const top = '<div class="crt-top">' + summaryCard(S.data.summary || {}, all) + outlookCard(S.data.outlook || []) + "</div>";
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
  async function openDrawer(key) {
    const panel = document.getElementById("cert-panel");
    const out = document.getElementById("cert-panel-body");
    if (!panel || !out) return;
    panel.hidden = false;
    out.innerHTML = '<p class="empty">Loading&hellip;</p>';
    let data;
    try {
      data = await call("/api/certificates/item?key=" + encodeURIComponent(key));
    } catch (e) {
      out.innerHTML = '<div class="mon-placeholder">Could not load: ' + esc(e.message) + "</div>";
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
      html += "<p><b>Trusted list</b> <span class=\"crt-sub\">" + tr.length + " certificates</span></p>" +
        '<table class="mini crt-trusted"><thead><tr><th>Status</th><th>Subject</th><th>Expires</th><th>Days</th></tr></thead><tbody>' +
        tr.map((x) => "<tr" + (x.state === "EXPIRED" || (x.flags || []).length ? ' class="crt-hl"' : "") + "><td>" + pill(x.state) + "</td><td>" + esc(x.subject) + " " + flagPills(x.flags) +
          "</td><td>" + day(x.not_after) + "</td><td>" + daysCell(x) + "</td></tr>").join("") + "</tbody></table>";
    }
    out.innerHTML = html;
  }

  // ---- events --------------------------------------------------------------------------------
  document.addEventListener("click", (ev) => {
    if (ev.target.closest("#crt-run")) { runNow(); return; }
    if (ev.target.closest("#refresh-certs")) { S.notice = null; mount(); return; }
    if (ev.target.closest("#cert-panel-close") || ev.target.id === "cert-panel") { const p = document.getElementById("cert-panel"); if (p) p.hidden = true; return; }
    const cat = ev.target.closest("#cert-body .crt-cat");
    if (cat) { S.cat = cat.dataset.cat; saveFilter(); render(); return; }
    const miss = ev.target.closest("#cert-body .crt-miss");
    if (miss) { const k = miss.dataset.sys; if (S.openMissing.has(k)) S.openMissing.delete(k); else S.openMissing.add(k); render(); return; }
    const det = ev.target.closest("#cert-body .crt-det") || ev.target.closest("#cert-body tr.crt-row");
    if (det && det.dataset.key) { openDrawer(det.dataset.key); }
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { const p = document.getElementById("cert-panel"); if (p && !p.hidden) p.hidden = true; }
  });
  document.addEventListener("change", (ev) => {
    if (ev.target && ev.target.id === "crt-tier") { S.tier = ev.target.value; saveFilter(); render(); }
    if (ev.target && ev.target.id === "crt-due") { S.due = ev.target.checked; saveFilter(); render(); }
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

  window.CertsApp = { onShow, mount };
})();
