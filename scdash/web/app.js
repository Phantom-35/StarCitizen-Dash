/*
 * SC-Dash frontend. Vanilla JS, no framework.
 * - polls /api/state every 2 s, re-renders only when the version changed
 * - pauses polling while the window is hidden/minimised
 * - the 1 s tick only touches a few text nodes and two SVG attributes
 */
(() => {
  "use strict";

  const POLL_MS = 2000;
  const BANNER_MS = 7000;
  const $ = (id) => document.getElementById(id);
  const pad = (n) => String(n).padStart(2, "0");

  let st = null;            // last state from the server
  let lastToken = "";       // "<server boot id>-<version>", sent back so the server can answer 204
  let lastEventId = null;   // null = first render, no banner for old events
  let pollTimer = null;
  let bannerTimer = null;

  // ---------------------------------------------------------------- helpers
  function setText(el, text) {
    if (el.textContent !== text) el.textContent = text;
  }
  function setClass(el, cls) {
    if (el.className !== cls) el.className = cls;
  }
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function hms(ms) {
    if (!isFinite(ms) || ms < 0) ms = 0;
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 3600)}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
  }
  function short(ms) {
    if (!isFinite(ms) || ms < 0) ms = 0;
    const s = Math.floor(ms / 1000);
    return s < 3600 ? `${pad(Math.floor(s / 60))}:${pad(s % 60)}` : hms(ms);
  }
  function ago(ms) {
    const m = Math.floor(ms / 60000);
    if (m < 1) return "gerade eben";
    if (m < 60) return `vor ${m} min`;
    return `vor ${Math.floor(m / 60)} h ${m % 60} min`;
  }
  const parseTs = (ts) => (ts ? Date.parse(ts) : NaN);

  /** Reference "now" for durations: frozen at the last log line when the game is closed. */
  function sessionNow(now) {
    if (!st) return now;
    const s = st.session;
    if (st.game_running === false || s.ended) {
      const last = parseTs(s.last_log);
      return isFinite(last) ? last : now;
    }
    return now;
  }

  // ---------------------------------------------------------------- chrono ticks (static)
  document.querySelectorAll(".ticks").forEach(function buildTicks(g) {
    const NS = "http://www.w3.org/2000/svg";
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2;
      const major = i % 5 === 0;
      const r1 = major ? 84 : 86, r2 = 94;
      const l = document.createElementNS(NS, "line");
      l.setAttribute("x1", 100 + r1 * Math.cos(a));
      l.setAttribute("y1", 100 + r1 * Math.sin(a));
      l.setAttribute("x2", 100 + r2 * Math.cos(a));
      l.setAttribute("y2", 100 + r2 * Math.sin(a));
      if (major) l.setAttribute("class", "major");
      g.appendChild(l);
    }
  });

  // ---------------------------------------------------------------- mode switch
  const MODE_KEY = "scdash.mode";
  const MODES = ["combat", "mission"];
  let mode = new URLSearchParams(location.search).get("mode") || localStorage.getItem(MODE_KEY) || "combat";

  function setMode(m) {
    mode = MODES.includes(m) ? m : "combat";
    document.body.dataset.mode = mode;
    localStorage.setItem(MODE_KEY, mode);
    document.querySelectorAll(".modes button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    setText($("feed-title"), mode === "combat" ? "Ereignisse" : "Komm-Log");
    if (st) renderFeed();
    tick();
  }
  document.querySelectorAll(".modes button").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));

  // ---------------------------------------------------------------- polling
  async function poll() {
    try {
      const res = await fetch("/api/state?since=" + encodeURIComponent(lastToken), { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      setClass($("ind-link"), "on");
      if (res.status === 204) return; // nothing changed
      const data = await res.json();
      if (data.token === lastToken) return;
      // event ids start again after a server restart
      if (lastToken.split("-")[0] !== data.token.split("-")[0]) lastEventId = null;
      lastToken = data.token;
      st = data;
      render();
    } catch (e) {
      setClass($("ind-link"), "off");
      lastToken = "";
    }
  }
  function startPolling() {
    if (pollTimer) return;
    poll();
    pollTimer = setInterval(poll, POLL_MS);
  }
  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  document.addEventListener("visibilitychange", () => (document.hidden ? stopPolling() : startPolling()));

  // ---------------------------------------------------------------- render (on change only)
  function render() {
    const gr = st.game_running;
    setClass($("ind-game"), gr === true ? "on live" : gr === false ? "off" : "");
    setClass($("ind-log"), st.log.found ? "on" : "warn");
    document.body.classList.toggle("offline", gr === false);

    const s = st.session;
    const loc = s.location;
    let crumb, place;
    if (!st.log.found) {
      crumb = "Game.log nicht gefunden";
      place = "Kein Log";
    } else if (loc) {
      crumb = [loc.system, loc.planet !== loc.place ? loc.planet : null].filter(Boolean).join(" › ");
      place = loc.place;
    } else {
      crumb = s.handle ? "Standort wird ermittelt" : "Warte auf Spiel";
      place = s.handle ? "Im Verse" : "Kein Signal";
    }
    if (gr === false && s.handle) crumb = "Letzte Session" + (crumb ? " · " + crumb : "");
    renderCrumb(crumb || "–");
    setText($("loc-place"), place);
    $("loc-place").classList.toggle("long", place.length > 11);
    setText($("loc-region"), s.region || "");
    setText($("loc-shard"), s.shard || "");
    setText($("loc-version"), st.game_version ? "SC " + st.game_version : "");

    const k = st.stats;
    const deaths = k.deaths + k.suicides;
    const kills = k.kills + k.npc_kills;
    setText($("st-kills"), String(k.kills));
    setText($("st-npc"), String(k.npc_kills));
    setText($("st-deaths"), String(deaths));
    const kd = kills / Math.max(1, deaths);
    setText($("st-kd"), kills || deaths ? kd.toFixed(kd >= 10 ? 0 : 1) : "–");
    setText($("st-streak"), String(k.streak));
    setText($("st-best"), String(k.best_streak));
    setText($("st-vdest"), String(k.vehicles_destroyed));
    setText($("st-vlost"), String(k.vehicles_lost));
    setText($("st-killer"), s.last_killer ? s.last_killer.name : "–");

    renderPills(st.nav);
    renderMissions();
    renderFeed();
    renderRsi(st.rsi_status);
    setText($("log-path"), st.log.path ? "Log: " + st.log.path : "Keine Game.log gefunden – siehe README (--log)");
    tick();
  }

  function renderCrumb(text) {
    const c = $("loc-crumb");
    if (c.dataset.v === text) return;
    c.dataset.v = text;
    c.replaceChildren();
    text.split(" › ").forEach((part, i) => {
      if (i) c.appendChild(el("i", "", "›"));
      c.appendChild(document.createTextNode(part));
    });
  }

  function renderFeed() {
    const events = st.feeds[mode] || [];
    const now = Date.now();
    const frag = document.createDocumentFragment();
    if (!events.length) frag.appendChild(el("li", "empty", "Noch keine Ereignisse in dieser Session."));
    for (const ev of events) {
      const li = el("li", ev.cat);
      const fresh = lastEventId !== null && ev.id > lastEventId;
      if (fresh || (now - parseTs(ev.ts) < 20000)) li.classList.add("fresh");
      const head = el("div", "ev-head");
      const d = parseTs(ev.ts);
      head.appendChild(el("time", "", isFinite(d) ? `${pad(new Date(d).getHours())}:${pad(new Date(d).getMinutes())}` : "--:--"));
      head.appendChild(el("span", "", ev.title));
      li.appendChild(head);
      if (ev.actor) li.appendChild(el("div", "ev-actor", ev.actor));
      if (ev.detail) li.appendChild(el("div", "ev-detail", ev.detail));
      frag.appendChild(li);
    }
    $("feed").replaceChildren(frag);

    // banner for brand-new important events of the current mode
    const newest = events.find((e) => e.banner && lastEventId !== null && e.id > lastEventId);
    if (newest && now - parseTs(newest.ts) < 60000) showBanner(newest);
    let maxId = lastEventId ?? 0;
    for (const f of Object.values(st.feeds)) if (f.length) maxId = Math.max(maxId, f[0].id);
    lastEventId = maxId;
  }

  // ---------------------------------------------------------------- zone / ship pills
  function pill(id, text, cls) {
    const e = $(id);
    setText(e, text || "");
    setClass(e, cls || "");
  }
  function renderPills(nav) {
    pill("p-ship", nav.ship ? "◈ " + nav.ship : "", "ship");
    pill("p-arm", nav.armistice === true ? "Armistice" : nav.armistice === false ? "Waffen frei" : "",
      nav.armistice ? "ok" : "warn");
    pill("p-mon", nav.monitored === true ? "Überwacht" : nav.monitored === false ? "Unüberwacht" : "",
      nav.monitored ? "ok" : "bad");
    pill("p-jur", nav.jurisdiction || "", "");
  }

  // ---------------------------------------------------------------- missions
  const RESULT_LABEL = { completed: "Erledigt", failed: "Gescheitert", abandoned: "Abgebrochen" };

  function mins(sec) {
    if (sec == null) return "";
    const m = Math.round(sec / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
  }

  function renderMissions() {
    const ms = st.missions;
    const active = ms.active;
    const focus = active[0];
    const title = $("c-title");
    setText(title, focus ? focus.title : "Kein aktiver Auftrag");
    title.classList.toggle("none", !focus);
    setText($("c-count"), active.length > 1 ? `1 / ${active.length}` : "");

    const ol = $("c-objectives");
    const frag = document.createDocumentFragment();
    if (!focus) {
      frag.appendChild(el("li", "hint", "Nimm einen Auftrag an – er erscheint hier automatisch mit allen Zielen."));
    } else if (!focus.objectives.length) {
      frag.appendChild(el("li", "hint", "Ziele erscheinen, sobald das Spiel sie meldet."));
    } else {
      // open objectives first, then finished ones; at most 6
      const sorted = [...focus.objectives].sort((a, b) => (a.state === "open" ? 0 : 1) - (b.state === "open" ? 0 : 1));
      for (const o of sorted.slice(0, 6)) frag.appendChild(el("li", o.state, o.text));
    }
    ol.replaceChildren(frag);

    const others = $("c-others");
    const of = document.createDocumentFragment();
    for (const m of active.slice(1, 4)) {
      const li = el("li");
      li.appendChild(el("b", "", "Aktiv"));
      const open = m.objectives.filter((o) => o.state === "open").length;
      li.appendChild(document.createTextNode(m.title + (m.objectives.length ? ` · ${open} offene Ziele` : "")));
      of.appendChild(li);
    }
    for (const h of ms.history.slice(0, Math.max(0, 4 - Math.min(3, active.length - 1)))) {
      const li = el("li", "r-" + h.result);
      li.appendChild(el("b", "", RESULT_LABEL[h.result] || h.result));
      li.appendChild(document.createTextNode(h.title + (h.duration != null ? ` · ${mins(h.duration)}` : "")));
      of.appendChild(li);
    }
    others.replaceChildren(of);

    const k = st.stats;
    setText($("ms-done"), String(k.missions_completed));
    setText($("ms-failed"), String(k.missions_failed));
    setText($("ms-aband"), `${k.missions_abandoned} abgebrochen`);
    const total = k.missions_completed + k.missions_failed;
    setText($("ms-rate"), total ? `${Math.round((k.missions_completed / total) * 100)} % Quote` : "–");
    setText($("ms-places"), String(k.places));
    setText($("ms-jumps"), `besucht · ${k.quantum_jumps} QT-Sprünge`);
    renderEarnings();
  }

  // ---------------------------------------------------------------- earnings (manual, per game session)
  const EARN_KEY = "scdash.earnings";
  const numFmt = new Intl.NumberFormat("de-DE");
  function earnings() {
    const e = load(EARN_KEY, { session: null, total: 0 });
    const cur = st && st.session.start;
    if (cur && e.session !== cur) return { session: cur, total: 0 };
    return e;
  }
  function renderEarnings() {
    const e = earnings();
    setText($("ms-earn"), numFmt.format(e.total));
  }
  $("earn-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const raw = $("earn-in").value.trim().toLowerCase().replace(/[\s.,]/g, "");
    const m = raw.match(/^([+-]?\d+)(k|m)?$/);
    if (!m) return;
    const val = parseInt(m[1], 10) * (m[2] === "k" ? 1e3 : m[2] === "m" ? 1e6 : 1);
    const e = earnings();
    e.total += val;
    localStorage.setItem(EARN_KEY, JSON.stringify(e));
    $("earn-in").value = "";
    renderEarnings();
  });

  function showBanner(ev) {
    const b = $("banner");
    setText($("banner-title"), ev.title);
    setText($("banner-actor"), ev.actor || (ev.cat === "kill" ? "Ziel neutralisiert" : "K.O."));
    setText($("banner-detail"), ev.detail || "");
    b.className = "banner " + ev.cat;
    b.hidden = false;
    void b.offsetWidth; // restart animation
    clearTimeout(bannerTimer);
    bannerTimer = setTimeout(() => {
      b.classList.add("out");
      bannerTimer = setTimeout(() => (b.hidden = true), 650);
    }, BANNER_MS);
  }

  const RSI_CLASS = { operational: "on", disrupted: "warn", notice: "warn", down: "off" };
  const RSI_SHORT = { "Persistent Universe": "PU", "Arena Commander": "AC", Platform: "Plattform" };

  function renderRsi(rs) {
    const ul = $("rsi");
    const frag = document.createDocumentFragment();
    if (!rs || !(rs.systems || []).length) {
      frag.appendChild(el("li", "", rs && rs.error ? "nicht erreichbar" : "–"));
    } else {
      for (const sys of rs.systems) {
        const li = el("li", RSI_CLASS[sys.status] || "");
        li.title = `${sys.name}: ${sys.status}`;
        li.appendChild(el("span", "dot"));
        li.appendChild(document.createTextNode(RSI_SHORT[sys.name] || sys.name));
        frag.appendChild(li);
      }
    }
    ul.replaceChildren(frag);
    setClass($("ind-rsi"), rs ? RSI_CLASS[rs.summary] || "" : "");
  }

  // ---------------------------------------------------------------- 1 s tick
  const arcMin = $("arc-min"), arcSec = $("arc-sec");
  const dateFmt = new Intl.DateTimeFormat("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });

  function tick() {
    const now = Date.now();
    const d = new Date(now);
    setText($("clock-local"), `${pad(d.getHours())}:${pad(d.getMinutes())}`);
    setText($("clock-sec"), pad(d.getSeconds()));
    setText($("clock-utc"), `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`);
    setText($("date-local"), dateFmt.format(d));

    if (st) {
      const s = st.session;
      const ref = sessionNow(now);
      const alive = ref - parseTs(s.alive_since);
      setText($("alive"), isFinite(alive) ? short(alive) : "--:--");
      setText($("session"), isFinite(parseTs(s.start)) ? hms(ref - parseTs(s.start)) : "--:--:--");
      if (isFinite(alive)) {
        const sec = Math.floor(alive / 1000);
        arcMin.style.strokeDasharray = `${(((sec / 60) % 60) / 60) * 1000} 1000`;
        arcSec.style.strokeDasharray = `${((sec % 60) / 60) * 1000} 1000`;
      }
      // mission ring: time in the focused contract, otherwise session time
      const focus = st.missions.active[0];
      const accepted = focus ? parseTs(focus.accepted) : NaN;
      const sessionMs = ref - parseTs(s.start);
      const ringMs = isFinite(accepted) ? ref - accepted : sessionMs;
      setText($("m-ring-label"), isFinite(accepted) ? "Im Auftrag" : "Session");
      setText($("m-ring"), isFinite(ringMs) ? short(ringMs) : "--:--");
      setText($("m-ring-sub-wrap"), isFinite(accepted)
        ? "Session " + (isFinite(sessionMs) ? hms(sessionMs) : "--:--:--")
        : `${st.stats.missions_completed} Aufträge erledigt`);
      if (isFinite(ringMs)) {
        const sec = Math.floor(ringMs / 1000);
        $("m-arc-min").style.strokeDasharray = `${(((sec / 60) % 60) / 60) * 1000} 1000`;
        $("m-arc-sec").style.strokeDasharray = `${((sec % 60) / 60) * 1000} 1000`;
      }

      const since = parseTs(s.location_since);
      setText($("loc-since"), isFinite(since) && s.location ? "Hier seit " + short(ref - since) : "");
      setText($("st-killer-sub"), s.last_killer ? ago(now - parseTs(s.last_killer.ts)) : "noch keiner – weiter so");
    }
    tickTimers(now);
  }

  // ---------------------------------------------------------------- timers
  const TIMER_KEY = "scdash.timers";
  let timers = load(TIMER_KEY, []);
  const timerNodes = new Map();

  function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  }
  function saveTimers() { localStorage.setItem(TIMER_KEY, JSON.stringify(timers)); }

  function renderTimers() {
    const ul = $("timers");
    ul.replaceChildren();
    timerNodes.clear();
    timers.sort((a, b) => a.end - b.end);
    for (const t of timers) {
      const li = el("li");
      li.appendChild(el("span", "t-label", t.label));
      const left = el("span", "t-left", "");
      li.appendChild(left);
      const bar = el("span", "t-bar");
      const fill = el("i");
      bar.appendChild(fill);
      li.appendChild(bar);
      const del = el("button", "t-del", "×");
      del.title = "Timer entfernen";
      del.addEventListener("click", () => {
        timers = timers.filter((x) => x.id !== t.id);
        saveTimers();
        renderTimers();
      });
      li.appendChild(del);
      ul.appendChild(li);
      timerNodes.set(t.id, { li, left, fill });
    }
    tickTimers(Date.now());
  }

  function tickTimers(now) {
    let done = 0;
    for (const t of timers) {
      const n = timerNodes.get(t.id);
      if (!n) continue;
      const left = t.end - now;
      const total = t.end - (t.start || t.end - 1);
      const pct = Math.min(100, Math.max(0, 100 - (left / total) * 100));
      n.fill.style.width = pct.toFixed(1) + "%";
      if (left <= 0) {
        done++;
        setText(n.left, "FERTIG");
        setClass(n.li, "done");
      } else {
        setText(n.left, short(left));
      }
    }
    const title = done ? `(${done}) ⏰ SC-Dash` : "SC-Dash";
    if (document.title !== title) document.title = title;
  }

  $("timer-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const h = parseInt($("t-h").value || "0", 10);
    const m = parseInt($("t-m").value || "0", 10);
    const mins = h * 60 + m;
    const label = $("t-label").value.trim();
    if (!label || mins <= 0) return;
    const now = Date.now();
    timers.push({ id: now + Math.random(), label, start: now, end: now + mins * 60000 });
    saveTimers();
    renderTimers();
    e.target.reset();
  });

  // ---------------------------------------------------------------- drawer (notes / links)
  const drawer = $("drawer");
  function openDrawer(name) {
    const isOpen = drawer.classList.contains("open") && drawer.dataset.pane === name;
    if (isOpen) return closeDrawer();
    drawer.dataset.pane = name;
    drawer.querySelectorAll("[data-pane]").forEach((p) => (p.hidden = p.dataset.pane !== name));
    setText($("drawer-title"), name === "notes" ? "Notizen" : "Links");
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    document.querySelectorAll(".tools button").forEach((b) => b.classList.toggle("active", b.dataset.drawer === name));
    if (name === "notes") setTimeout(() => $("notes").focus(), 260);
  }
  function closeDrawer() {
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    document.querySelectorAll(".tools button").forEach((b) => b.classList.remove("active"));
  }
  document.querySelectorAll(".tools button").forEach((b) => b.addEventListener("click", () => openDrawer(b.dataset.drawer)));
  $("drawer-close").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") return closeDrawer();
    if (/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName) || e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.key === "n" || e.key === "N") { e.preventDefault(); openDrawer("notes"); }
    if (e.key === "l" || e.key === "L") { e.preventDefault(); openDrawer("links"); }
    if (e.key === "m" || e.key === "M") { e.preventDefault(); setMode(mode === "combat" ? "mission" : "combat"); }
  });

  const NOTES_KEY = "scdash.notes";
  const notes = $("notes");
  notes.value = localStorage.getItem(NOTES_KEY) || "";
  let notesTimer = null;
  notes.addEventListener("input", () => {
    clearTimeout(notesTimer);
    notesTimer = setTimeout(() => localStorage.setItem(NOTES_KEY, notes.value), 400);
  });

  fetch("links.json")
    .then((r) => r.json())
    .then((links) => {
      const ul = $("links");
      for (const l of links) {
        if (!/^https?:\/\//.test(l.url)) continue;
        const li = el("li");
        const a = el("a", "", l.name);
        a.href = l.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        li.appendChild(a);
        ul.appendChild(li);
      }
    })
    .catch(() => {});

  // ---------------------------------------------------------------- start
  setMode(mode);
  renderTimers();
  tick();
  setTimeout(() => { tick(); setInterval(tick, 1000); }, 1000 - (Date.now() % 1000));
  startPolling();
})();
