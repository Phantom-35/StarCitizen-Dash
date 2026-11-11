/*
 * SC-Dash frontend. Vanilla JS, no framework.
 * - polls /api/state every 2 s, re-renders only when the version changed
 * - pauses polling while the window is hidden/minimised
 * - the 1 s tick only touches a few text nodes and two SVG attributes
 */
(() => {
  "use strict";

  const LONG_POLL_S = 20;   // how long the server may hold a request
  const RETRY_MS = 2000;    // pause after a failed request
  const BANNER_MS = 7000;
  const $ = (id) => document.getElementById(id);
  const pad = (n) => String(n).padStart(2, "0");

  let st = null;            // last state from the server
  let lastToken = "";       // "<server boot id>-<version>", sent back so the server can answer 204
  let lastEventId = null;   // null = first render, no banner for old events
  // Difference between the server clock (= the game PC, which writes the log timestamps)
  // and this device. Matters when the dashboard runs on a tablet whose clock is off.
  let skew = 0;
  const serverNow = () => Date.now() + skew;
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
  // Long polling: the server holds the request until something changes, so events show up
  // within the watcher's read interval instead of waiting for the next poll.
  let pollGen = 0;            // increases whenever polling is (re)started or stopped
  let pollAbort = null;

  function applyState(data) {
    if (data.token === lastToken) return;
    // event ids start again after a server restart
    if (lastToken.split("-")[0] !== data.token.split("-")[0]) lastEventId = null;
    lastToken = data.token;
    if (typeof data.server_time === "number") skew = data.server_time * 1000 - Date.now();
    st = data;
    render();
  }

  async function pollLoop(gen) {
    while (gen === pollGen) {
      try {
        pollAbort = new AbortController();
        const url = `/api/state?since=${encodeURIComponent(lastToken)}&wait=${LONG_POLL_S}`;
        const res = await fetch(url, { cache: "no-store", signal: pollAbort.signal });
        if (gen !== pollGen) return;
        if (!res.ok) throw new Error(res.status);
        setClass($("ind-link"), "on");
        if (res.status !== 204) applyState(await res.json());
      } catch (e) {
        if (gen !== pollGen) return; // aborted on purpose
        setClass($("ind-link"), "off");
        lastToken = "";
        await new Promise((r) => setTimeout(r, RETRY_MS));
      }
    }
  }
  function startPolling() {
    pollLoop(++pollGen);
  }
  function stopPolling() {
    pollGen++;
    if (pollAbort) pollAbort.abort();
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
    setText($("loc-server"), s.server ? "Server " + s.server : "");
    renderHealth();

    const k = st.stats;
    bigNumber("st-deaths", k.deaths);
    bigNumber("st-incaps", k.incaps);
    bigNumber("st-injuries", k.injuries);
    bigNumber("st-crime", k.crimestat);
    setText($("st-medbed"), String(k.medbed));
    setText($("st-collisions"), `${k.collisions} ${k.collisions === 1 ? "Kollision" : "Kollisionen"}`);
    const ld = s.last_death;
    setText($("st-killer"), ld ? (ld.who && ld.cause !== "Gestorben" ? ld.who : ld.cause) : "–");

    // kill lines only exist in older game versions (until ~4.3) - show them only if present
    const kills = k.kills + k.npc_kills + k.vehicles_destroyed;
    $("legacy-kills").hidden = kills === 0;
    setText($("st-kills"), String(k.kills));
    setText($("st-npc"), String(k.npc_kills));
    const kd = (k.kills + k.npc_kills) / Math.max(1, k.deaths);
    setText($("st-kd"), kd.toFixed(kd >= 10 ? 0 : 1));

    renderPills(st.nav);
    renderMissions();
    renderFeed();
    renderRsi(st.rsi_status);
    setText($("log-path"), st.log.path ? "Log: " + st.log.path : "Keine Game.log gefunden – siehe README (--log)");
    tick();
  }

  function renderHealth() {
    const inj = st.health.injuries;
    const b = $("st-health");
    if (!inj.length) {
      setText(b, "Unverletzt");
      setClass(b, "ok");
      setText($("st-health-sub"), "keine offenen Verletzungen");
      return;
    }
    const worst = Math.min(...inj.map((i) => i.tier)); // tier 1 = needs the best med bed
    setText(b, inj.length === 1 ? inj[0].part : `${inj.length} Verletzungen`);
    setClass(b, inj.some((i) => i.severe) ? "bad" : "hurt");
    setText($("st-health-sub"), (inj.length > 1 ? inj.map((i) => i.part).join(", ") + " · " : "") + `Med-Bed Tier ${worst} nötig`);
  }

  function bigNumber(id, value) {
    const e = $(id);
    setText(e, String(value));
    e.classList.toggle("zero", !value);
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
    const now = serverNow();
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
  const fuelFmt = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const scuFmt = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
  /** Percent of the quantum tank: honest about tiny values instead of showing "0 %". */
  function pctFmt(p) {
    if (p < 0.1) return "< 0,1 %";
    if (p < 10) return fuelFmt.format(p) + " %";
    return Math.round(p) + " %";
  }
  /** "Deliver 8/24 SCU" vs. the ship's cargo hold -> how many trips are left. */
  function cargoHint(text) {
    const info = st.nav.ship_info;
    const m = text.match(/(\d+)\s*\/\s*(\d+)\s*SCU/i);
    if (!m || !info || info.cargo == null) return "";
    const left = +m[2] - +m[1];
    if (left <= 0) return "";
    const about = info.cargo_confirmed ? "" : "ca. ";
    if (info.cargo <= 0) return `${info.name} hat keinen Frachtraum`;
    const trips = Math.ceil(left / info.cargo);
    return trips <= 1
      ? `passt in einen Flug (Frachtraum ${about}${scuFmt.format(info.cargo)} SCU)`
      : `${trips} Flüge nötig (Frachtraum ${about}${scuFmt.format(info.cargo)} SCU, offen ${left} SCU)`;
  }

  /** Ship name plus how long we have been aboard (updated by the 1 s tick). */
  function shipPill(now) {
    const nav = st.nav;
    const since = parseTs(nav.ship_since);
    const aboard = isFinite(since) ? " · an Bord " + short(sessionNow(now) - since) : "";
    const info = nav.ship_info;
    // cargo capacity from the ship database ("ca." when no independent source confirmed it)
    const cargo = info && info.cargo != null ? ` · ${info.cargo_confirmed ? "" : "ca. "}${scuFmt.format(info.cargo)} SCU` : "";
    pill("p-ship", nav.ship ? "◈ " + nav.ship + aboard + cargo : "", "ship");
  }

  function renderPills(nav) {
    shipPill(Date.now() + skew);
    pill("p-arm", nav.armistice === true ? "Armistice" : nav.armistice === false ? "Waffen frei" : "",
      nav.armistice ? "ok" : "warn");
    pill("p-mon", nav.monitored === true ? "Überwacht" : nav.monitored === false ? "Unüberwacht" : "",
      nav.monitored ? "ok" : "bad");
    pill("p-crew", nav.crew.length ? "Crew: " + nav.crew.join(", ") : "", "crew");
    pill("p-jur", nav.jurisdiction || "", nav.jurisdiction && nav.jurisdiction.toLowerCase() === "ungoverned" ? "bad" : "");
    pill("p-restricted", nav.restricted ? "Sperrgebiet" : "", "bad");
    pill("p-private", nav.private ? "Privatgelände" : "", "warn");
    // What the planned jump takes out of the quantum tank. Falls back to the game's raw
    // estimate when the ship (or its tank size) is unknown.
    const approx = nav.ship_info && !nav.ship_info.qt_fuel_confirmed ? "ca. " : "";
    let need = "";
    let qtClass = "qt";
    if (nav.quantum_need_pct != null) {
      need = ` · braucht ${approx}${pctFmt(nav.quantum_need_pct)} Tank`;
      const total = nav.quantum_need_pct + (nav.quantum_used_pct || 0);
      if (nav.quantum_need_pct > 100) {
        need += " – reicht nicht!";
        qtClass = "qt bad";
      } else if (total > 100) {
        need += " – Tankstand prüfen";   // more than one full tank since the session started
        qtClass = "qt warn";
      }
    } else if (nav.quantum_fuel) {
      need = ` · Bedarf ${fuelFmt.format(nav.quantum_fuel)}`;
    }
    pill("p-qt", nav.quantum_target ? "⟶ " + nav.quantum_target + need : "", qtClass);
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

    const loc = st.session.location;
    const here = loc && loc.place ? loc.place.toLowerCase() : "";
    const ol = $("c-objectives");
    const frag = document.createDocumentFragment();
    if (!focus) {
      frag.appendChild(el("li", "hint", "Nimm einen Auftrag an – er erscheint hier automatisch mit allen Zielen."));
    } else if (!focus.objectives.length) {
      frag.appendChild(el("li", "hint", "Ziele erscheinen, sobald das Spiel sie meldet."));
    } else {
      // open objectives first, then finished ones; at most 6
      const sorted = [...focus.objectives].sort((a, b) => (a.state === "open" ? 0 : 1) - (b.state === "open" ? 0 : 1));
      for (const o of sorted.slice(0, 6)) {
        const li = el("li", o.state, o.text);
        // "Deliver 12/24 SCU ..." -> progress bar
        const m = o.text.match(/(\d+)\s*\/\s*(\d+)/);
        if (m && +m[2] > 0) {
          const bar = el("span", "bar");
          const fill = el("i");
          fill.style.width = Math.min(100, (100 * +m[1]) / +m[2]).toFixed(0) + "%";
          bar.appendChild(fill);
          li.appendChild(bar);
        }
        const hint = o.state === "open" ? cargoHint(o.text) : "";
        if (hint) li.appendChild(el("span", "cargo-hint", hint));
        if (o.state === "open" && here && o.text.toLowerCase().includes(here)) li.classList.add("here");
        frag.appendChild(li);
      }
    }
    ol.replaceChildren(frag);

    // where to fly next - and whether we are already there
    const next = focus && focus.next;
    $("c-next").hidden = !next;
    if (next) {
      setText($("c-next-place"), next);
      $("c-next-here").hidden = !(here && next.toLowerCase().includes(here));
    }

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
    const durs = ms.history.filter((h) => h.result === "completed" && h.duration != null).map((h) => h.duration);
    const avg = durs.length ? ` · Ø ${mins(durs.reduce((a, b) => a + b, 0) / durs.length)}` : "";
    setText($("ms-rate"), total ? `${Math.round((k.missions_completed / total) * 100)} % Quote${avg}` : "–");
    setText($("ms-places"), String(k.places));
    const used = st.nav.quantum_used_pct;
    const burned = used != null ? ` · ${pctFmt(used)} QT-Tank verflogen` : "";
    setText($("ms-jumps"), `besucht · ${k.quantum_jumps} QT-Sprünge${burned}`);
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
    const k = st ? st.stats : { money_in: 0, money_out: 0, spend: 0, fines: 0 };
    // manual contract pay + what the log tells us: transfers, purchases, fines
    const plus = e.total + k.money_in;
    const minus = k.spend + k.money_out + k.fines;
    const total = plus - minus;
    setText($("ms-earn"), numFmt.format(total));
    $("ms-earn").classList.toggle("neg", total < 0);
    const parts = [];
    if (minus) parts.push(`−${numFmt.format(minus)} ausgegeben`);
    if (k.money_in) parts.push(`+${numFmt.format(k.money_in)} erhalten`);
    setText($("ms-earn-sub"), parts.join(" · "));
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

  // ---------------------------------------------------------------- sound cues
  // Short, quiet tones so you notice important things while looking at the game.
  const SOUND_KEY = "scdash.sound";
  let soundOn = localStorage.getItem(SOUND_KEY) !== "off";
  let audio = null;
  const TONES = {
    good: [[660, 0], [880, 0.12]],            // rising: contract done, timer finished
    bad: [[440, 0], [330, 0.14], [247, 0.28]], // falling: death, K.O., error
    info: [[587, 0]],                          // single: contract accepted, warnings
  };
  function beep(kind) {
    if (!soundOn) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
      for (const [freq, at] of TONES[kind] || TONES.info) {
        const osc = audio.createOscillator();
        const gain = audio.createGain();
        const t0 = audio.currentTime + at;
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(0.09, t0 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.22);
        osc.connect(gain).connect(audio.destination);
        osc.start(t0);
        osc.stop(t0 + 0.25);
      }
    } catch (e) { /* no audio device - stay silent */ }
  }
  function renderSoundToggle() {
    const b = $("sound-toggle");
    setText(b, soundOn ? "Ton an" : "Ton aus");
    b.classList.toggle("off", !soundOn);
  }
  function toggleSound() {
    soundOn = !soundOn;
    localStorage.setItem(SOUND_KEY, soundOn ? "on" : "off");
    renderSoundToggle();
    beep("good");
  }
  $("sound-toggle").addEventListener("click", toggleSound);
  renderSoundToggle();
  const CAT_TONE = { death: "bad", fail: "bad", success: "good", kill: "good" };

  function showBanner(ev) {
    beep(CAT_TONE[ev.cat] || "info");
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
    const d = new Date();          // the clock shows this device's own time
    const now = serverNow();       // durations are measured against the log's clock
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

      shipPill(now);
      const since = parseTs(s.location_since);
      setText($("loc-since"), isFinite(since) && s.location ? "Hier seit " + short(ref - since) : "");
      const ld = s.last_death;
      setText($("st-killer-sub"), ld
        ? [ld.cause !== "Gestorben" && ld.who ? ld.cause : null, ld.where, ago(now - parseTs(ld.ts))].filter(Boolean).join(" · ")
        : "noch keiner – weiter so");
      const best = Math.max(st.stats.best_alive * 1000, isFinite(alive) ? alive : 0);
      setText($("st-best-alive"), best > 0 ? short(best) : "–");
      setText($("st-best-alive-sub"), isFinite(alive) && alive >= st.stats.best_alive * 1000 && st.stats.deaths
        ? "neuer Rekord läuft" : "diese Session");
    }
    tickTimers(Date.now()); // timers are stored with this device's clock
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
        if (!t.notified) {
          // announce once - but not for timers that ran out while the dashboard was closed
          t.notified = true;
          saveTimers();
          if (left > -15000) showBanner({ cat: "success", title: "Timer fertig", actor: t.label, detail: "" });
        }
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
    if (e.key === "t" || e.key === "T") { e.preventDefault(); toggleSound(); }
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
