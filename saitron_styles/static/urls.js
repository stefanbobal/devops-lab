// Monitoring > URLs pane (cert lifecycle S8): availability of every URL of the reviewed catalog, checked every
// 5 minutes by the read-only "url-check" Job (GET /api/urls). Admin "Check now" starts that Job
// (POST /api/urls/run). Certificate days come from the daily "cert-inventory" scan. A row with no fresh
// check is UNKNOWN, never UP. Reuses the chk-* classes of the Checks pane. Exposes window.UrlsApp.
(function () {
  "use strict";

  const STORE_KEY = "sapops-urls-filter";
  const saved = (() => { try { return JSON.parse(sessionStorage.getItem(STORE_KEY) || "{}"); } catch (_) { return {}; } })();
  const S = { data: null, tier: saved.tier || "all", status: saved.status || "all", kind: saved.kind || "all",
              q: saved.q || "", timer: null, notice: null, busy: false };
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
  const DTT = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v) => { if (!v) return "\u2014"; const d = new Date(v); return isNaN(d) ? esc(v) : esc(DTT.format(d).replace(",", "")); };
  const body = () => document.getElementById("url-body");
  const tierOf = (r) => String(r.tier || "").toLowerCase();

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
      el.innerHTML = '<div class="mon-placeholder">Could not load the URLs: ' + esc(e.message) + "</div>";
      return;
    }
    render();
    clearTimeout(S.timer);
    S.timer = setTimeout(() => { if (paneVisible()) mount(); }, REFRESH_MS);
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
    return '<div class="kpis">' +
      '<div class="kpi"><div class="k-top"><span class="k-ic b">&#x1F517;</span> URLs</div><div class="k-val">' + rows.length + '</div><div class="k-sub">from the reviewed catalog</div></div>' +
      '<div class="kpi"><div class="k-top"><span class="k-ic g">&#x2714;</span> Up</div><div class="k-val">' + n.UP + '</div><div class="k-sub">2xx / 3xx / 401 / 403</div></div>' +
      '<div class="kpi"><div class="k-top"><span class="k-ic r">&#x26A0;</span> Down</div><div class="k-val">' + n.DOWN + '</div><div class="k-sub">answered with an error code</div></div>' +
      '<div class="kpi"><div class="k-top"><span class="k-ic b">&#x2754;</span> Unreachable / unknown</div><div class="k-val">' + (n.UNREACHABLE + n.UNKNOWN) + '</div><div class="k-sub">no answer or no fresh check &ndash; never counted as up</div></div>' +
      '<div class="kpi"><div class="k-top"><span class="k-ic o">&#x1F512;</span> Certificate &le; 30 d</div><div class="k-val">' + certWarn + '</div><div class="k-sub">served certificate expiring</div></div>' +
      "</div>";
  }

  function toolbar(rows) {
    const present = new Set(rows.map(tierOf));
    const tierChips = [["all", "All"]].concat(TIERS.filter((t) => present.has(t)).map((t) => [t, TIER_LABEL[t] || t]))
      .map(([v, l]) => '<button type="button" class="chk-chip url-tier' + (S.tier === v ? " active" : "") + '" data-tier="' + esc(v) + '">' + esc(l) + "</button>").join("");
    const statusChips = STATUS_CHIPS.map(([v, l]) => {
      const cnt = v === "all" ? rows.length : v === "notup" ? rows.filter((r) => r.verdict !== "UP").length : rows.filter((r) => r.verdict === v).length;
      return '<button type="button" class="chk-chip url-status' + (S.status === v ? " active" : "") + '" data-status="' + esc(v) + '">' + esc(l) + ' <span class="url-cnt">' + cnt + "</span></button>";
    }).join("");
    const kinds = Array.from(new Set(rows.map((r) => r.kind).filter(Boolean))).sort();
    const kindSel = '<select id="url-kind" class="url-kind"><option value="all">All kinds</option>' +
      kinds.map((k) => '<option value="' + esc(k) + '"' + (S.kind === k ? " selected" : "") + ">" + esc(KIND_LABEL[k] || k) + "</option>").join("") + "</select>";
    return '<div class="chk-toolbar"><span class="subtle">Tier:</span>' + tierChips + "</div>" +
      '<div class="chk-toolbar"><span class="subtle">Status:</span>' + statusChips +
      '<span class="rhs">' + kindSel + '<input type="search" id="url-q" placeholder="Filter system / URL" value="' + esc(S.q) + '" /></span></div>';
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
    const since = r.last_up_at ? "last up " + fmt(r.last_up_at) : "never seen up";
    const text = since + (n ? " \u00B7 " + n + "\u00D7 in a row" : "");
    return '<span class="subtle url-down" title="' + esc(text) + '">' + esc(text) + "</span>";
  }

  function rowHtml(r) {
    const who = r.sid || r.system || "?";
    const pill = '<span class="pill ' + (VERDICT_CLS[r.verdict] || "muted") + '" title="' +
      esc(r.stale ? "no check in the last " + (S.data.stale_minutes || 15) + " min (last result: " + (r.last_verdict || "-") + ")" : (r.error_type || r.verdict)) + '">' + esc(r.verdict) + "</span>";
    const access = ACCESS_LABEL[r.access] || r.access || "";
    const gclb = r.access === "gclb" ? ' <span class="badge b-rise" title="RISE system reached through the GCLB">RISE</span>' : "";
    const http = r.http_status == null ? '<span class="chk-dash" title="' + esc(r.error_type || "") + '">' + esc(r.error_type ? r.error_type.toLowerCase().replace(/_/g, " ") : "\u2014") + "</span>" : esc(r.http_status);
    const ms = r.latency_ms == null ? "&mdash;" : esc(Math.round(r.latency_ms)) + " ms";
    const href = /^https?:\/\//i.test(r.url || "") ? esc(r.url) : "#";
    const kind = KIND_LABEL[r.kind] || r.kind || "";
    const checked = fmt(r.checked_at) + (r.stale ? ' <span class="pill muted" title="no check in the last ' + esc(S.data.stale_minutes || 15) + ' min">stale</span>' : "");
    return "<tr><td>" + pill + '</td><td class="chk-sid" title="' + esc(who) + '">' + esc(who) + '</td><td title="' + esc(kind) + '">' + esc(kind) +
      "</td><td>" + esc(access) + gclb + '</td><td class="chk-mono url-link"><a href="' + href + '" target="_blank" rel="noopener noreferrer" title="' + esc(r.url) + '">' + esc(r.url) + "</a></td>" +
      "<td>" + http + "</td><td>" + ms + '</td><td class="url-wrap">' + certCell(r) + "</td><td>" + downCell(r) + '</td><td class="url-wrap">' + checked + "</td></tr>";
  }

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
      html += '<table class="mini chk-table url-table"><colgroup>' +
        ["11%", "8%", "10%", "9%", "20%", "6%", "6%", "11%", "10%", "9%"].map((w) => '<col style="width:' + w + '">').join("") +
        "</colgroup><thead><tr><th>Status</th><th>System</th><th>Kind</th><th>Access</th><th>URL</th><th>HTTP</th><th>Time</th><th>Cert</th><th>Down since</th><th>Checked</th></tr></thead><tbody>" +
        list.map(rowHtml).join("") + "</tbody></table>";
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
    const last = document.getElementById("url-last");
    if (last) last.innerHTML = S.data.last_checked ? "Last check <b>" + fmt(S.data.last_checked) + "</b> &middot; every 5 min" : "every 5 min";
    const btn = document.getElementById("url-run");
    if (btn) { btn.disabled = S.busy; btn.innerHTML = S.busy ? "&#x23F3; Starting&hellip;" : "&#x25B6; Check now"; }
    const notice = S.notice ? '<div class="chk-notice ' + esc(S.notice.cls) + '">' + esc(S.notice.text) + "</div>" : "";
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
    if (tier) { S.tier = tier.dataset.tier; saveFilter(); render(); return; }
    const st = ev.target.closest("#url-body .url-status");
    if (st) { S.status = st.dataset.status; saveFilter(); render(); }
  });
  document.addEventListener("change", (ev) => {
    if (ev.target && ev.target.id === "url-kind") { S.kind = ev.target.value; saveFilter(); render(); }
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
