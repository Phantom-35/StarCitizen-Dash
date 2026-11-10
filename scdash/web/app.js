/*
 * SC-Dash frontend. Plain JS, no framework, no canvas, no animations.
 * - polls /api/state every 2 s and only re-renders when the version changed
 * - pauses polling while the window is hidden/minimised
 * - the 1 s tick only updates a handful of text nodes (clocks, timers)
 */
(() => {
  "use strict";

  const POLL_MS = 2000;
  const $ = (id) => document.getElementById(id);
  const pad = (n) => String(n).padStart(2, "0");

  let lastVersion = -1;
  let sessionStart = null;
  let pollTimer = null;

  // ---------------------------------------------------------------- helpers
  function setText(el, text) {
    if (el.textContent !== text) el.textContent = text;
  }

  function setChip(el, text, cls) {
    setText(el, text);
    el.className = "chip" + (cls ? " " + cls : "");
  }

  function fmtDuration(ms) {
    if (ms < 0 || !isFinite(ms)) return "–";
    const s = Math.floor(ms / 1000);
    const h = Math.floor(s / 3600);
    return `${h}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
  }

  function fmtClock(d, utc) {
    return utc
      ? `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
      : `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  // ---------------------------------------------------------------- polling
  async function poll() {
    try {
      const res = await fetch("/api/state", { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      const st = await res.json();
      setChip($("chip-link"), "VERBUNDEN", "on");
      if (st.version !== lastVersion) {
        lastVersion = st.version;
        render(st);
      }
    } catch (e) {
      setChip($("chip-link"), "KEIN SERVER", "off");
      lastVersion = -1;
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

  document.addEventListener("visibilitychange", () => {
    document.hidden ? stopPolling() : startPolling();
  });

  // ---------------------------------------------------------------- render
  function render(st) {
    const gr = st.game_running;
    setChip($("chip-game"), gr === true ? "SPIEL LÄUFT" : gr === false ? "SPIEL AUS" : "SPIEL ?",
      gr === true ? "on" : gr === false ? "off" : "");
    setChip($("chip-log"), st.log.found ? "LOG OK" : "KEINE GAME.LOG", st.log.found ? "on" : "warn");
    setText($("log-path"), st.log.path || "Game.log nicht gefunden – siehe README (--log)");

    const s = st.session;
    setText($("s-handle"), s.handle || "–");
    setText($("s-location"), s.location || "–");
    setText($("s-shard"), s.shard || "–");
    sessionStart = s.start ? Date.parse(s.start) : null;

    const k = st.stats;
    setText($("st-kills"), String(k.kills));
    setText($("st-npc"), String(k.npc_kills));
    setText($("st-deaths"), String(k.deaths + k.suicides));
    const deaths = k.deaths + k.suicides;
    const kills = k.kills + k.npc_kills;
    setText($("st-kd"), deaths ? (kills / deaths).toFixed(2) : kills ? "∞" : "–");
    setText($("st-vdest"), String(k.vehicles_destroyed));
    setText($("st-vlost"), String(k.vehicles_lost));

    renderFeed(st.events);
    renderStatus(st.rsi_status);
  }

  function renderFeed(events) {
    const feed = $("feed");
    const frag = document.createDocumentFragment();
    if (!events.length) {
      frag.appendChild(el("li", "muted", "Noch keine Ereignisse."));
    }
    for (const ev of events) {
      const li = el("li");
      const d = ev.ts ? new Date(ev.ts) : null;
      li.appendChild(el("time", "", d ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : "--:--"));
      li.appendChild(el("span", ev.cat, ev.text));
      frag.appendChild(li);
    }
    feed.replaceChildren(frag);
  }

  const STATUS_DE = {
    operational: "OK",
    disrupted: "GESTÖRT",
    down: "AUSFALL",
    notice: "HINWEIS",
    unknown: "?",
  };

  function renderStatus(rs) {
    const ul = $("rsi");
    if (!rs) {
      ul.replaceChildren(el("li", "muted", "Deaktiviert oder noch nicht geladen."));
      setText($("rsi-meta"), "");
      return;
    }
    const frag = document.createDocumentFragment();
    for (const sys of rs.systems || []) {
      const li = el("li");
      li.appendChild(el("span", "", sys.name));
      const label = (STATUS_DE[sys.status] || sys.status) + (sys.issues ? ` (${sys.issues})` : "");
      li.appendChild(el("b", "st-" + (STATUS_DE[sys.status] ? sys.status : "unknown"), label));
      frag.appendChild(li);
    }
    if (!frag.childNodes.length) frag.appendChild(el("li", "muted", "Keine Daten."));
    ul.replaceChildren(frag);
    const when = rs.checked ? new Date(rs.checked * 1000) : null;
    setText($("rsi-meta"),
      (rs.error ? rs.error + " · " : "") + (when ? `Stand ${pad(when.getHours())}:${pad(when.getMinutes())}` : ""));
  }

  // ---------------------------------------------------------------- timers
  const TIMER_KEY = "scdash.timers";
  let timers = load(TIMER_KEY, []);
  const timerNodes = new Map();

  function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  }

  function saveTimers() {
    localStorage.setItem(TIMER_KEY, JSON.stringify(timers));
  }

  function renderTimers() {
    const ul = $("timers");
    ul.replaceChildren();
    timerNodes.clear();
    timers.sort((a, b) => a.end - b.end);
    for (const t of timers) {
      const li = el("li");
      li.appendChild(el("span", "label", t.label));
      const left = el("span", "left", "");
      li.appendChild(left);
      const del = el("button", "", "×");
      del.title = "Entfernen";
      del.addEventListener("click", () => {
        timers = timers.filter((x) => x.id !== t.id);
        saveTimers();
        renderTimers();
      });
      li.appendChild(del);
      ul.appendChild(li);
      timerNodes.set(t.id, { li, left });
    }
    if (!timers.length) ul.appendChild(el("li", "muted", "Keine Timer."));
    tickTimers(Date.now());
  }

  function tickTimers(now) {
    let done = 0;
    for (const t of timers) {
      const n = timerNodes.get(t.id);
      if (!n) continue;
      const left = t.end - now;
      if (left <= 0) {
        done++;
        setText(n.left, "FERTIG");
        if (n.li.className !== "done") n.li.className = "done";
      } else {
        setText(n.left, fmtDuration(left));
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
    timers.push({ id: Date.now() + Math.random(), label, end: Date.now() + mins * 60000 });
    saveTimers();
    renderTimers();
    e.target.reset();
  });

  // ---------------------------------------------------------------- notes
  const NOTES_KEY = "scdash.notes";
  const notes = $("notes");
  notes.value = localStorage.getItem(NOTES_KEY) || "";
  let notesTimer = null;
  notes.addEventListener("input", () => {
    clearTimeout(notesTimer);
    notesTimer = setTimeout(() => localStorage.setItem(NOTES_KEY, notes.value), 400);
  });

  // ---------------------------------------------------------------- links
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

  // ---------------------------------------------------------------- 1 s tick
  function tick() {
    const now = new Date();
    setText($("clock-local"), fmtClock(now, false));
    setText($("clock-utc"), fmtClock(now, true));
    setText($("s-duration"), sessionStart ? fmtDuration(now - sessionStart) : "–");
    tickTimers(now.getTime());
  }

  renderTimers();
  tick();
  // Align to full seconds so the clock does not drift visibly.
  setTimeout(() => { tick(); setInterval(tick, 1000); }, 1000 - (Date.now() % 1000));
  startPolling();
})();
