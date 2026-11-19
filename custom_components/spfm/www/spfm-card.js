/*
 * SPFM card for Home Assistant: one card per unit, with bill, visitors,
 * announcements and notices. Shipped and auto-registered by the spfm
 * integration. No build step and no dependencies: a plain web component.
 */
const CARD_VERSION = "0.9.5";
const ALL_SECTIONS = ["visitors", "announcements", "notices", "bill"];
const SECTION_LABELS = {
  visitors: "Visitors",
  announcements: "Announcements",
  notices: "Notices",
  bill: "Bill",
};
const KEYS = {
  balance: "outstanding_balance",
  due: "next_due_date",
  notices: "active_announcements",
  feed: "latest_announcement",
  pending: "pending_visitors",
  upcoming: "upcoming_visitors",
};
// Labels come from SPFM's backend and differ between web and app wording.
const VISITOR_ICONS = {
  CONTRACTOR: "mdi:hammer-wrench",
  CONTRACTORS: "mdi:hammer-wrench",
  "RELATIVES & FRIENDS": "mdi:account-heart",
  DELIVERY: "mdi:package-variant-closed",
  "DROP OFF/PICKUP": "mdi:car-arrow-right",
  "DROPOFF / PICKUP": "mdi:car-arrow-right",
  "VISITOR PARKING": "mdi:parking",
  "OVERNIGHT PARKING": "mdi:weather-night",
  OTHERS: "mdi:account",
};
const DAY = 86400000;
const LAYOUTS = ["tabs", "stacked"];
const SECTION_ICONS = {
  visitors: "mdi:account-group",
  announcements: "mdi:bullhorn",
  notices: "mdi:file-document-multiple",
  bill: "mdi:cash-clock",
};
// SPFM wordmark, from the integration's brand/icon.png.
const SPFM_MARK = "data:image/png;base64,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";

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const toDate = (v) => {
  if (!v) return null;
  const d = new Date(v);
  return isNaN(d) ? null : d;
};

// Title-case words, but leave codes like "2A" or "WXX1234" as they are.
const titleCase = (s) =>
  String(s || "")
    .split(/(\s+)/)
    .map((w) => (/\d/.test(w) ? w.toUpperCase() : w.toLowerCase().replace(/(^|[(/&-])(\p{L})/gu, (m, a, b) => a + b.toUpperCase())))
    .join("");

// "JERNIH RESIDENCE – NOTICE OF ..." -> "Notice Of ..."
const cleanTitle = (t) => {
  let s = String(t || "").replace(/^[^–—]{3,40}?\s*[–—]\s+/, "").trim();
  if (s && s === s.toUpperCase()) s = titleCase(s);
  return s || String(t || "");
};



class SpfmCard extends HTMLElement {
  static getConfigElement() {
    const ed = document.createElement("spfm-card-editor");
    ed.fixed = !!this.FIXED;
    return ed;
  }

  static getStubConfig(hass) {
    const dev = SpfmCard.devices(hass)[0];
    return dev ? { device: dev } : {};
  }

  static devices(hass) {
    const out = new Set();
    for (const e of Object.values(hass?.entities || {})) {
      if (e.platform === "spfm" && e.device_id) out.add(e.device_id);
    }
    return [...out];
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._busy = new Set();
    this._sig = "";
  }

  setConfig(config) {
    const fixed = this.constructor.FIXED;
    if (fixed) config = { title: "", ...config, sections: fixed.sections, layout: fixed.layout };
    const sections = (config.sections && config.sections.length ? config.sections : ALL_SECTIONS).filter((s) =>
      ALL_SECTIONS.includes(s)
    );
    const layout = LAYOUTS.includes(config.layout) ? config.layout : "tabs";
    this._config = { max_items: 5, this_month: false, ...config, layout, sections };
    if (!sections.includes(this._tab)) this._tab = sections.includes(config.default_tab) ? config.default_tab : sections[0];
    this._sig = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._resolve();
    const sig = Object.values(this._ents || {})
      .map((id) => {
        const s = hass.states[id];
        return s ? s.last_updated + s.state : "-";
      })
      .join("|") + [...this._busy].join(",") + (hass.themes?.darkMode ? "d" : "l");
    if (sig !== this._sig) {
      this._sig = sig;
      this._render();
    }
  }

  getCardSize() {
    return this._tabbed() ? 6 : 2 + 2 * (this._config?.sections?.length || 4);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _resolve() {
    const hass = this._hass;
    const device = this._config?.device || SpfmCard.devices(hass)[0];
    if (this._device === device && this._entsRef === hass.entities && this._ents) return;
    this._device = device;
    this._entsRef = hass.entities;
    const ents = {};
    for (const e of Object.values(hass.entities || {})) {
      if (e.platform !== "spfm" || e.device_id !== device) continue;
      for (const [k, key] of Object.entries(KEYS)) {
        if (e.translation_key === key || e.entity_id.endsWith(`_${key}`)) ents[k] = e.entity_id;
      }
    }
    this._ents = ents;
  }

  _st(k) {
    const id = this._ents?.[k];
    return id ? this._hass.states[id] : undefined;
  }

  _attr(k, a) {
    return this._st(k)?.attributes?.[a];
  }

  _fmtDate(d, withTime = false) {
    const lang = this._hass?.locale?.language || this._hass?.language || "en";
    const opts = { day: "numeric", month: "short" };
    if (d.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
    if (withTime) Object.assign(opts, { hour: "2-digit", minute: "2-digit" });
    return d.toLocaleString(lang, opts);
  }

  _fmtTime(d) {
    const lang = this._hass?.locale?.language || "en";
    return d.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
  }

  _dayLabel(d) {
    const today = new Date();
    const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
    const diff = Math.floor((new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() - t0) / DAY);
    if (diff === 0) return "Today";
    if (diff === 1) return "Tomorrow";
    const lang = this._hass?.locale?.language || "en";
    return d.toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "short" });
  }

  /* ------------------------------------------------------------ sections */

  _money(n) {
    return `RM ${Number(n || 0).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  _bill() {
    const bal = this._st("balance");
    if (!bal) return "";
    const amount = parseFloat(bal.state);
    const due = toDate(this._st("due")?.state);
    const bills = bal.attributes?.bills || [];
    const payUrl = bal.attributes?.pay_url;
    let body;
    if (isNaN(amount)) body = `<div class="muted">Unavailable</div>`;
    else if (amount <= 0) body = `<div class="bill-sum ok"><ha-icon icon="mdi:check-circle"></ha-icon><span>All paid up</span></div>`;
    else {
      const overdue = due && due.getTime() < Date.now() - DAY;
      body = `<div class="bill-sum"><span class="amount">${this._money(amount)}</span>${
        due ? `<span class="chip ${overdue ? "bad" : ""}">${overdue ? "Overdue since" : "Due"} ${esc(this._fmtDate(due))}</span>` : ""
      }</div>`;
      body += bills
        .map((b) => {
          const d = toDate(b.date);
          const items = (b.items || [])
            .map((i) => `<div class="line"><span>${esc(titleCase(i.item || "Charge"))}</span><span>${this._money(i.amount)}</span></div>`)
            .join("");
          const head = [b.reference_no, d && this._fmtDate(d)].filter(Boolean).join(" · ");
          const pdf = b.pdf_path
            ? `<button class="link" data-pdf="${esc(b.pdf_path)}"><ha-icon icon="mdi:file-pdf-box"></ha-icon>${b.type === "BILL" || !b.type ? "Invoice" : "PDF"}</button>`
            : "";
          return `<div class="doc"><div class="doc-head"><span>${esc(head)}</span>${pdf}</div>${items}</div>`;
        })
        .join("");
      if (payUrl)
        body += `<div class="pay"><a class="btn approve" href="${esc(payUrl)}" target="_blank" rel="noreferrer"><ha-icon icon="mdi:credit-card-outline"></ha-icon>Pay ${this._money(amount)}</a></div>`;
    }
    return this._section("bill", "mdi:cash-clock", "Bill", body, this._ents.balance);
  }

  async _openPdf(path) {
    // The PDF is proxied by HA with the SPFM token; sign the path so a new tab can open it.
    const win = window.open("", "_blank");
    try {
      const res = await this._hass.callWS({ type: "auth/sign_path", path, expires: 60 });
      const url = res.path.startsWith("http") ? res.path : this._hass.hassUrl ? this._hass.hassUrl(res.path) : res.path;
      if (win) win.location.href = url;
      else window.open(url, "_blank");
    } catch (err) {
      if (win) win.close();
      alert(`SPFM: ${err?.message || err}`);
    }
  }

  _visitors() {
    if (!this._st("pending") && !this._st("upcoming")) return "";
    const max = this._config.max_items;
    const pending = this._attr("pending", "visitors") || [];
    const upcoming = this._attr("upcoming", "visitors") || [];
    const inside = upcoming.filter((v) => v.scan_in && !v.scan_out);
    const later = upcoming.filter((v) => !v.scan_in).slice(0, max);
    const unit = this._attr("pending", "unit_id");
    let html = "";

    if (pending.length) {
      html += `<div class="sub warn"><ha-icon icon="mdi:bell-ring"></ha-icon>Waiting at the guardhouse</div>`;
      html += pending
        .map((v) => {
          const busy = this._busy.has(String(v.id));
          return `<div class="row pending">
            ${v.image_url ? `<img class="avatar" src="${esc(v.image_url)}" alt="">` : this._icon(v)}
            <div class="main"><div class="title">${esc(titleCase(v.name) || "Visitor")}</div>
              <div class="meta">${esc([titleCase(v.type), v.company, v.vehicle].filter(Boolean).join(" · "))}</div></div>
            <div class="actions">
              <button class="btn approve" data-act="approve" data-id="${esc(v.id)}" data-unit="${esc(unit ?? "")}" ${busy ? "disabled" : ""}>
                <ha-icon icon="mdi:check"></ha-icon>${busy ? "…" : "Approve"}</button>
              <button class="btn reject" data-act="reject" data-id="${esc(v.id)}" data-unit="${esc(unit ?? "")}" ${busy ? "disabled" : ""}>
                <ha-icon icon="mdi:close"></ha-icon></button>
            </div></div>`;
        })
        .join("");
    }
    if (inside.length) {
      html += `<div class="sub ok"><ha-icon icon="mdi:map-marker-check"></ha-icon>Here now</div>`;
      html += inside
        .map((v) => {
          const t = toDate(v.scan_in);
          return this._row(this._icon(v), titleCase(v.name), [t && `In since ${this._fmtTime(t)}`, v.vehicle].filter(Boolean).join(" · "), v.link);
        })
        .join("");
    }
    if (later.length) {
      if (pending.length || inside.length) html += `<div class="sub"><ha-icon icon="mdi:calendar-clock"></ha-icon>Upcoming</div>`;
      html += later
        .map((v) => {
          const t = toDate(v.datetime);
          const late = t && Date.now() - t.getTime() > 2 * 3600000;
          const when = t ? `${this._dayLabel(t)}, ${this._fmtTime(t)}` : "";
          const badge = late ? `<span class="chip muted">no-show?</span>` : "";
          return this._row(this._icon(v), titleCase(v.name), [when, v.company || v.purpose].filter(Boolean).join(" · "), v.link, badge);
        })
        .join("");
    }
    if (!html) html = `<div class="empty">No visitors expected</div>`;
    const count = pending.length ? `<span class="count warn">${pending.length}</span>` : "";
    return this._section("visitors", "mdi:account-group", "Visitors", html, this._ents.upcoming, count);
  }

  _filterMonth(items) {
    if (!this._config.this_month) return items;
    const now = new Date();
    return items.filter((a) => {
      const d = toDate(a.published);
      return d && d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
    });
  }

  _announcements() {
    if (!this._st("feed")) return "";
    const items = this._filterMonth(this._attr("feed", "announcements") || []).slice(0, this._config.max_items);
    const html = items.length
      ? items
          .map((a) => {
            const d = toDate(a.published);
            const link = a.pdf_url || (a.notice ? a.url : null);
            const isNew = d && Date.now() - d.getTime() < 3 * DAY;
            const meta = [d && this._fmtDate(d, true), a.notice ? null : "App only"].filter(Boolean).join(" · ");
            return this._row(
              `<ha-icon class="lead" icon="${a.pdf_url ? "mdi:file-pdf-box" : "mdi:bullhorn-outline"}"></ha-icon>`,
              cleanTitle(a.title),
              meta,
              link,
              isNew ? `<span class="chip new">New</span>` : ""
            );
          })
          .join("")
      : `<div class="empty">${this._config.this_month ? "No announcements this month" : "No announcements"}</div>`;
    return this._section("announcements", "mdi:bullhorn", "Announcements", html, this._ents.feed);
  }

  _notices() {
    if (!this._st("notices")) return "";
    const all = (this._attr("notices", "announcements") || []).filter((a) => a.active);
    const items = this._filterMonth(all).slice(0, this._config.max_items);
    const html = items.length
      ? items
          .map((a) => {
            const d = toDate(a.published);
            const isNew = d && Date.now() - d.getTime() < 3 * DAY;
            return this._row(
              `<ha-icon class="lead" icon="mdi:file-document-outline"></ha-icon>`,
              cleanTitle(a.title),
              d ? this._fmtDate(d) : "",
              a.pdf_url || a.url,
              isNew ? `<span class="chip new">New</span>` : ""
            );
          })
          .join("")
      : `<div class="empty">No active notices</div>`;
    const more = all.length - items.length;
    const listUrl = this._attr("notices", "list_url");
    const foot =
      more > 0 || listUrl
        ? `<div class="foot">${more > 0 ? `${more} more active` : ""}${more > 0 && listUrl ? " · " : ""}${
            listUrl ? `<a href="${esc(listUrl)}" target="_blank" rel="noreferrer">All notices</a>` : ""
          }</div>`
        : "";
    const count = all.length ? `<span class="count">${all.length}</span>` : "";
    return this._section("notices", "mdi:file-document-multiple", "Notices", html + foot, this._ents.notices, count);
  }

  /* ------------------------------------------------------------- helpers */

  _icon(v) {
    const icon = VISITOR_ICONS[String(v.type || "").toUpperCase().trim()] || "mdi:account";
    return `<ha-icon class="lead" icon="${icon}" title="${esc(titleCase(v.type))}"></ha-icon>`;
  }

  _row(lead, title, meta, link, badge = "") {
    const t = link
      ? `<a href="${esc(link)}" target="_blank" rel="noreferrer">${esc(title)}</a>`
      : `<span>${esc(title)}</span>`;
    return `<div class="row">${lead}<div class="main"><div class="title">${t}${badge}</div>${
      meta ? `<div class="meta">${esc(meta)}</div>` : ""
    }</div></div>`;
  }

  _section(key, icon, label, body, entityId, extra = "") {
    if (this._tabbed()) return `<section class="${key} tabbed">${body}</section>`;
    return `<section class="${key}"><div class="head" data-more="${esc(entityId || "")}">
      <ha-icon icon="${icon}"></ha-icon><span>${label}</span>${extra}</div>${body}</section>`;
  }

  _tabbed() {
    return this._config?.layout === "tabs" && (this._config?.sections?.length || 0) > 1;
  }

  // Small badge per tab: what needs attention, never a plain total.
  _badge(key) {
    const fresh = (rows) => rows.filter((a) => {
      const d = toDate(a.published);
      return d && Date.now() - d.getTime() < 3 * DAY;
    }).length;
    if (key === "visitors") {
      const n = (this._attr("pending", "visitors") || []).length;
      return n ? `<span class="badge warn">${n}</span>` : "";
    }
    if (key === "announcements") {
      const n = fresh(this._attr("feed", "announcements") || []);
      return n ? `<span class="badge new">${n}</span>` : "";
    }
    if (key === "notices") {
      const n = fresh((this._attr("notices", "announcements") || []).filter((a) => a.active));
      return n ? `<span class="badge new">${n}</span>` : "";
    }
    if (key === "bill") {
      const amount = parseFloat(this._st("balance")?.state);
      if (!(amount > 0)) return "";
      const due = toDate(this._st("due")?.state);
      const overdue = due && due.getTime() < Date.now() - DAY;
      return `<span class="badge dot ${overdue ? "bad" : "warn"}"></span>`;
    }
    return "";
  }

  _tabBar() {
    const inline = this._config.sections.length <= 2;
    return `<div class="tabs ${inline ? "inline" : ""}" role="tablist">${this._config.sections
      .map((k) => {
        const badge = this._badge(k);
        return `<button class="tab ${k === this._tab ? "on" : ""}" role="tab" aria-selected="${k === this._tab}" data-tab="${k}">
          <span class="ti"><ha-icon icon="${SECTION_ICONS[k]}"></ha-icon>${inline ? "" : badge}</span><span class="tl">${SECTION_LABELS[k]}</span>${inline ? badge : ""}</button>`;
      })
      .join("")}</div>`;
  }

  async _act(btn) {
    const id = btn.dataset.id;
    const approve = btn.dataset.act === "approve";
    if (!approve && !confirm("Reject this visitor?")) return;
    this._busy.add(id);
    this._sig = "";
    this._render();
    try {
      const data = { visitor_id: id };
      if (btn.dataset.unit) data.unit_id = btn.dataset.unit;
      await this._hass.callService("spfm", approve ? "approve_visitor" : "reject_visitor", data);
    } catch (err) {
      alert(`SPFM: ${err?.message || err}`);
    } finally {
      this._busy.delete(id);
      this._sig = "";
      this._render();
    }
  }

  _more(entityId) {
    if (!entityId) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }

  _render() {
    if (!this._config || !this._hass) return;
    const c = this._config;
    let body;
    if (!this._device) {
      body = `<div class="empty pad">No SPFM unit found. Set up the SPFM integration first.</div>`;
    } else {
      const parts = { bill: () => this._bill(), visitors: () => this._visitors(), announcements: () => this._announcements(), notices: () => this._notices() };
      body = this._tabbed()
        ? this._tabBar() + (parts[this._tab]() || `<div class="empty pad">No data for this section yet.</div>`)
        : c.sections.map((s) => parts[s]()).join("") || `<div class="empty pad">No SPFM entities for this unit.</div>`;
    }
    const devName = this._hass.devices?.[this._device]?.name_by_user || this._hass.devices?.[this._device]?.name;
    const title = c.title === undefined ? devName || "SPFM" : c.title;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>
      ${title ? `<div class="card-title"><img class="mark" src="${SPFM_MARK}" alt="SPFM"><span>${esc(title)}</span></div>` : ""}
      <div class="content">${body}</div></ha-card>`;
    this.shadowRoot.querySelectorAll("button[data-act]").forEach((b) => b.addEventListener("click", () => this._act(b)));
    this.shadowRoot.querySelectorAll("button[data-pdf]").forEach((b) => b.addEventListener("click", () => this._openPdf(b.dataset.pdf)));
    this.shadowRoot.querySelectorAll("button[data-tab]").forEach((b) =>
      b.addEventListener("click", () => {
        this._tab = b.dataset.tab;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll(".head[data-more]").forEach((h) => h.addEventListener("click", () => this._more(h.dataset.more)));
  }
}

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .card-title { display: flex; align-items: center; gap: 10px; padding: 16px 16px 0; font-size: var(--ha-card-header-font-size, 20px); font-weight: 500; color: var(--ha-card-header-color, var(--primary-text-color)); }
  .card-title span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mark { height: 16px; flex: none; }
  .content { padding: 4px 16px 12px; }
  .tabs { display: flex; margin: 6px -16px 4px; padding: 0 8px; border-bottom: 1px solid var(--divider-color); }
  .tab { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 2px 7px; background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; color: var(--secondary-text-color); font: inherit; font-size: 12px; font-weight: 500; cursor: pointer; }
  .tab:hover { color: var(--primary-text-color); }
  .tab.on { color: var(--primary-color); border-bottom-color: var(--primary-color); }
  .tab .tl { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ti { position: relative; display: inline-flex; }
  .ti ha-icon { --mdc-icon-size: 22px; }
  .badge { position: absolute; top: -4px; left: 15px; min-width: 16px; height: 16px; padding: 0 4px; box-sizing: border-box; border-radius: 8px; font-size: 10px; line-height: 16px; text-align: center; color: #fff; background: var(--primary-color); }
  .badge.warn { background: var(--warning-color, #ffa600); }
  .badge.bad { background: var(--error-color, #db4437); }
  .badge.dot { min-width: 10px; width: 10px; height: 10px; padding: 0; top: -1px; left: 17px; }
  .tabs.inline .badge { position: static; }
  .tabs.inline .badge.dot { margin-left: -2px; }
  .tabs.inline .tab { flex-direction: row; justify-content: center; gap: 8px; font-size: 14px; padding: 12px 4px 10px; }
  section.tabbed { padding-top: 6px; }
  section { padding: 10px 0 6px; }
  section + section { border-top: 1px solid var(--divider-color); }
  .head { display: flex; align-items: center; gap: 8px; font-weight: 500; font-size: 14px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; cursor: pointer; margin-bottom: 4px; }
  .head ha-icon { --mdc-icon-size: 18px; color: var(--state-icon-color, var(--primary-color)); }
  .count { margin-left: auto; min-width: 20px; height: 20px; padding: 0 6px; box-sizing: border-box; border-radius: 10px; background: var(--secondary-background-color); color: var(--primary-text-color); font-size: 12px; display: inline-flex; align-items: center; justify-content: center; }
  .count.warn { background: var(--warning-color, #ffa600); color: #fff; }
  .sub { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; color: var(--secondary-text-color); margin: 8px 0 2px; }
  .sub ha-icon { --mdc-icon-size: 16px; }
  .sub.warn, .sub.warn ha-icon { color: var(--warning-color, #ffa600); }
  .sub.ok ha-icon { color: var(--success-color, #43a047); }
  .row { display: flex; align-items: center; gap: 12px; padding: 6px 0; }
  .row.pending { background: color-mix(in srgb, var(--warning-color, #ffa600) 10%, transparent); margin: 2px -8px; padding: 8px; border-radius: 10px; }
  .lead { --mdc-icon-size: 22px; color: var(--state-icon-color, var(--paper-item-icon-color, #44739e)); flex: none; }
  .avatar { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; flex: none; }
  .main { flex: 1; min-width: 0; }
  .title { font-size: 14px; color: var(--primary-text-color); line-height: 1.35; display: flex; align-items: baseline; gap: 6px; }
  .title a, .title span:first-child { overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .title a { color: var(--primary-color); text-decoration: none; }
  .title a:hover { text-decoration: underline; }
  .meta { font-size: 12px; color: var(--secondary-text-color); margin-top: 1px; }
  .chip { flex: none; font-size: 11px; padding: 1px 7px; border-radius: 9px; background: var(--secondary-background-color); color: var(--secondary-text-color); white-space: nowrap; }
  .chip.new { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .chip.bad { background: var(--error-color, #db4437); color: #fff; }
  .actions { display: flex; gap: 6px; flex: none; }
  .btn { display: inline-flex; align-items: center; gap: 4px; border: none; border-radius: 18px; padding: 6px 12px; font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; }
  .btn ha-icon { --mdc-icon-size: 16px; }
  .btn.approve { background: var(--success-color, #43a047); color: #fff; }
  .btn.reject { background: transparent; color: var(--error-color, #db4437); border: 1px solid var(--error-color, #db4437); padding: 6px 8px; }
  .btn[disabled] { opacity: .6; cursor: default; }
  .bill-sum { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
  .doc { margin: 6px 0 2px; padding: 8px 10px; border-radius: 10px; background: var(--secondary-background-color); }
  .doc-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--secondary-text-color); margin-bottom: 4px; }
  .line { display: flex; justify-content: space-between; font-size: 13px; color: var(--primary-text-color); padding: 1px 0; }
  .link { display: inline-flex; align-items: center; gap: 3px; background: none; border: none; color: var(--primary-color); font: inherit; font-size: 12px; cursor: pointer; padding: 0; }
  .link ha-icon { --mdc-icon-size: 16px; }
  .pay { display: flex; justify-content: flex-end; padding-top: 8px; }
  .pay .btn { text-decoration: none; }
  .bill-sum .amount { font-size: 22px; font-weight: 500; color: var(--primary-text-color); }
  .bill-sum.ok { color: var(--success-color, #43a047); font-size: 15px; }
  .empty { font-size: 13px; color: var(--secondary-text-color); padding: 4px 0; font-style: italic; }
  .empty.pad { padding: 16px 0; }
  .muted { color: var(--secondary-text-color); }
  .foot { font-size: 12px; color: var(--secondary-text-color); padding-top: 4px; }
  .foot a { color: var(--primary-color); text-decoration: none; }
`;

/* ---------------------------------------------------------------- editor */

class SpfmCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _update() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) =>
        ({ device: "Unit", title: "Title (leave empty to use the unit name)", layout: "Layout", default_tab: "Tab to open first", sections: "Sections, in order", max_items: "Max rows per section", this_month: "Only this month's announcements and notices" })[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...ev.detail.value };
        for (const k of Object.keys(config)) if (config[k] === "" || config[k] === undefined) delete config[k];
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { layout: "tabs", sections: ALL_SECTIONS, max_items: 5, this_month: false, ...this._config };
    const fixed = this.fixed;
    this._form.schema = [
      { name: "device", selector: { device: { integration: "spfm" } } },
      { name: "title", selector: { text: {} } },
      {
        name: "layout",
        selector: { select: { mode: "dropdown", options: [{ value: "tabs", label: "Tabs" }, { value: "stacked", label: "Stacked (all sections)" }] } },
      },
      {
        name: "default_tab",
        selector: { select: { mode: "dropdown", options: ALL_SECTIONS.map((s) => ({ value: s, label: SECTION_LABELS[s] })) } },
      },
      {
        name: "sections",
        selector: { select: { multiple: true, reorder: true, mode: "list", options: ALL_SECTIONS.map((s) => ({ value: s, label: SECTION_LABELS[s] })) } },
      },
    ].filter((f) => !fixed || !["layout", "sections", "default_tab"].includes(f.name)).concat([
      { name: "max_items", selector: { number: { min: 1, max: 15, mode: "box" } } },
      { name: "this_month", selector: { boolean: {} } },
    ]);
  }
}

// Ready-made single-purpose cards: same code, fixed sections.
class SpfmVisitorsCard extends SpfmCard {
  static FIXED = { sections: ["visitors"], layout: "stacked" };
}
class SpfmUpdatesCard extends SpfmCard {
  static FIXED = { sections: ["announcements", "notices"], layout: "tabs" };
}
class SpfmBillCard extends SpfmCard {
  static FIXED = { sections: ["bill"], layout: "stacked" };
}

if (!customElements.get("spfm-card")) customElements.define("spfm-card", SpfmCard);
if (!customElements.get("spfm-visitors-card")) customElements.define("spfm-visitors-card", SpfmVisitorsCard);
if (!customElements.get("spfm-updates-card")) customElements.define("spfm-updates-card", SpfmUpdatesCard);
if (!customElements.get("spfm-bill-card")) customElements.define("spfm-bill-card", SpfmBillCard);
if (!customElements.get("spfm-card-editor")) customElements.define("spfm-card-editor", SpfmCardEditor);

window.customCards = window.customCards || [];
for (const [type, name, description] of [
  ["spfm-visitors-card", "SPFM Visitors", "Walk-ins waiting at the guardhouse (approve or reject), who's here now and who's coming."],
  ["spfm-updates-card", "SPFM Announcements & Notices", "App announcements and official notices, in two tabs."],
  ["spfm-bill-card", "SPFM Bill", "Outstanding amount, due date, invoice PDF and a Pay button."],
  ["spfm-card", "SPFM (all in one)", "Visitors, announcements, notices and bill in one card, as tabs or stacked."],
]) {
  if (!window.customCards.some((c) => c.type === type))
    window.customCards.push({ type, name, description, preview: true, documentationURL: "https://github.com/zubir2k/homeassistant-spfm" });
}
console.info(`%c SPFM-CARD %c v${CARD_VERSION} `, "background:#00539b;color:#fff;border-radius:3px 0 0 3px", "background:#eee;color:#00539b;border-radius:0 3px 3px 0");
