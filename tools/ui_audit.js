const { chromium } = require('playwright');
const fs = require('fs');
// Layout audit for SC-Dash (see CONTRIBUTING.md):
//   python tools/make_stress_log.py stress.log
//   python -m scdash --log stress.log --no-status --port 8777
//   node tools/ui_audit.js out-dir stress.log
// Checks every visible text/graphic element in 9 screen sizes x 2 modes x (normal, timer form open,
// drawer open, history drawer open; update notice shown) plus a live banner: does it run into another area, is it cut off, off-screen,
// or overlapping inside the headline / timer bar? Exit code 1 if anything is found.
const [,, OUT = 'ui-audit', LOG = 'stress.log'] = process.argv;
fs.mkdirSync(OUT, { recursive: true });
const VIEWS = [[1280, 720], [1366, 768], [1440, 900], [1586, 860], [1920, 1080], [2560, 1440], [3440, 1440], [1080, 1920], [1024, 768]];
const TIMERS = (n) => Array.from({ length: n }, (_, i) => ({ id: i + 1, label: ['Raffinerie ARC-L1 Wide Forest', 'Schiffsmiete Constellation Andromeda', 'Bounty Cooldown', 'Lagerhaus', 'Med-Bed', 'Fracht 2'][i], start: Date.now() - 3600e3, end: Date.now() + (i + 1) * 3700e3 }));

const AUDIT = () => {
  const vis = (e) => { if (!e || !e.getClientRects().length) return false; const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden') return false; for (let x = e; x; x = x.parentElement) if (parseFloat(getComputedStyle(x).opacity) < 0.05) return false; return true; };
  const R = (e) => e.getBoundingClientRect();
  const nm = (e) => (e.id ? '#' + e.id : e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.split(' ')[0] : '')) + (e.textContent ? ` "${e.textContent.trim().slice(0, 28)}"` : '');
  const inter = (a, b) => { const x = Math.min(a.right, b.right) - Math.max(a.left, b.left), y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top); return x > 2 && y > 2; };
  // leaves = visible elements that draw something themselves (own text, svg, inputs, bars)
  // what is really visible of an element: its box cut by every ancestor that hides overflow
  const visibleRect = (e) => { let r = R(e); let L = r.left, T = r.top, Rt = r.right, B = r.bottom, clipper = null;
    for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) { const cs = getComputedStyle(x);
      if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible' || x.id === 'drawer') { const q = R(x);
        const nl = Math.max(L, q.left), nt = Math.max(T, q.top), nr = Math.min(Rt, q.right), nb = Math.min(B, q.bottom);
        if ((nr - nl) * (nb - nt) < (Rt - L) * (B - T) - 4) clipper = clipper || x; L = nl; T = nt; Rt = nr; B = nb; } }
    return { left: L, top: T, right: Rt, bottom: B, width: Rt - L, height: B - T, clipper }; };
  const leaves = [...document.querySelectorAll('body *')].filter((e) => vis(e) && (
    [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) || ['svg', 'input', 'button'].includes(e.tagName.toLowerCase()) ||
    e.matches('.t-bar, .bar, .dot')) && !e.closest('svg *'));
  const regions = ['.top', '.hero', '.feed', '.dock'].map((s) => document.querySelector(s)).filter(vis);
  const drawer = document.querySelector('#drawer.open');
  const issues = [];
  for (const leaf of leaves) {
    if (drawer && (drawer.contains(leaf))) continue;
    if (!drawer && leaf.closest('#drawer')) continue;           // closed drawer sits off-screen on purpose
    const r = visibleRect(leaf);
    if (r.width < 1 || r.height < 1) continue;                    // fully clipped = not visible
    // partly cut by an ancestor: fine for the feed (fades out on purpose) and for "…" text
    if (r.clipper && !r.clipper.closest('#feed') && getComputedStyle(leaf).textOverflow !== 'ellipsis' && !leaf.closest('.ev-actor'))
      issues.push(`CLIPPED ${nm(leaf)} by ${nm(r.clipper).split(' ')[0]}`);
    const own = regions.find((g) => g.contains(leaf));
    if (drawer && inter(r, R(drawer))) continue; // covered by the drawer on purpose
    for (const g of regions) if (g !== own && inter(r, R(g))) issues.push(`INTO-OTHER-AREA ${nm(leaf)} → ${g.className.split(' ')[0]}`);
    if (own) {
      const o = R(own);
      if (r.bottom > o.bottom + 2 || r.right > o.right + 2 || r.top < o.top - 2) issues.push(`CUT-OFF ${nm(leaf)} in ${own.className.split(' ')[0]} (${Math.round(r.bottom - o.bottom)}px below)`);
    }
    if (r.right > innerWidth + 1 || r.left < -1) issues.push(`OFFSCREEN ${nm(leaf)}`);
    const cs = getComputedStyle(leaf);
    if (cs.textOverflow !== 'ellipsis' && leaf.scrollWidth > leaf.clientWidth + 2 && leaf.clientWidth > 0 && cs.overflowX === 'visible' && cs.whiteSpace === 'nowrap')
      issues.push(`TEXT-WIDER-THAN-BOX ${nm(leaf)}`);
  }
  // inside the hero: headline vs. lower part, chrono vs. stats
  const pair = (a, b) => { for (const x of document.querySelectorAll(a)) for (const y of document.querySelectorAll(b))
    if (vis(x) && vis(y) && !x.contains(y) && !y.contains(x) && inter(R(x), R(y))) issues.push(`OVERLAP ${nm(x)} × ${nm(y)}`); };
  pair('.loc .pills span, .loc .place, .loc .loc-meta, #banner', '.core:not([hidden]) .chrono, .core .readout, .core .contract');
  pair('.core .chrono', '.core .readout, .core .contract');
  pair('.top .brand, .top .modes, .top .sys li', '.top .clock');
  pair('#timers li:not([hidden]), #timer-add, .timers .more, #timer-form', '.dock .rsi, .dock .tools');
  // drawer content (history): nothing may stick out of the drawer or be cut without "…"
  if (drawer) for (const leaf of leaves.filter((e) => drawer.contains(e))) {
    const r = R(leaf), d = R(drawer), cs = getComputedStyle(leaf);
    if (r.right > d.right + 1 || r.left < d.left - 1) issues.push(`OUT-OF-DRAWER ${nm(leaf)}`);
    if (cs.textOverflow !== 'ellipsis' && leaf.scrollWidth > leaf.clientWidth + 2 && leaf.clientWidth > 0 && cs.whiteSpace === 'nowrap')
      issues.push(`DRAWER-TEXT-CUT ${nm(leaf)}`);
  }
  return { issues: [...new Set(issues)], density: [...document.body.classList].filter((c) => c.startsWith('dense')).pop() || '-', scroll: document.documentElement.scrollHeight > innerHeight + 1 };
};

(async () => {
  const b = await chromium.launch({ args: ['--disable-gpu'] });
  const all = [];
  for (const [w, h] of VIEWS) for (const mode of ['combat', 'mission']) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    const errs = []; p.on('pageerror', (e) => errs.push(String(e)));
    // pretend a new version is out, so the update notice takes its room in the tool bar
    await p.route('**/api/state*', async (route) => {
      try {
        const res = await route.fetch();
        if (res.status() !== 200) return await route.fulfill({ response: res });
        const data = await res.json();
        data.update = { version: '0.99.0', current: '0.10.0', url: 'https://github.com/Phantom-35/StarCitizen-Dash/releases/latest' };
        await route.fulfill({ response: res, json: data });
      } catch { /* page already closed while a long poll was open */ }
    });
    await p.goto('http://127.0.0.1:8777/');
    await p.evaluate(([m, t]) => { localStorage.setItem('scdash.mode', m); localStorage.setItem('scdash.timers', JSON.stringify(t)); }, [mode, TIMERS(6)]);
    await p.reload();
    await p.waitForFunction(() => document.getElementById('loc-place').textContent.length > 15, null, { timeout: 8000 }).catch(() => errs.push('no data'));
    await p.waitForTimeout(600);
    const tag = `${w}x${h}-${mode}`;
    const states = {};
    states.base = await p.evaluate(AUDIT);
    await p.screenshot({ path: `${OUT}/${tag}.png` });
    await p.click('#timer-add'); await p.waitForTimeout(150);
    states.form = await p.evaluate(AUDIT);
    if (mode === 'mission' && w === 1280) await p.screenshot({ path: `${OUT}/${tag}-form.png` });
    await p.keyboard.press('Escape'); await p.waitForTimeout(100);
    await p.keyboard.press('n'); await p.waitForTimeout(350);
    states.drawer = await p.evaluate(AUDIT);
    await p.keyboard.press('Escape'); await p.waitForTimeout(350);
    await p.keyboard.press('v'); await p.waitForTimeout(600);
    states.history = await p.evaluate(AUDIT);
    if (w === 1920 && mode === 'mission') await p.screenshot({ path: `${OUT}/${tag}-history.png` });
    await p.keyboard.press('Escape'); await p.waitForTimeout(350);
    all.push({ tag, states, errs });
    await p.unrouteAll({ behavior: 'ignoreErrors' });
    await p.close();
  }
  // banner: trigger one real event and audit while it is shown
  for (const [w, h] of [[1280, 720], [1920, 1080], [1080, 1920]]) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    await p.goto('http://127.0.0.1:8777/?mode=mission'); await p.waitForTimeout(800);
    // current time: the dashboard (rightly) shows no banner for events older than a minute
    fs.appendFileSync(LOG, `<${new Date().toISOString()}> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Banner Test With A Really Quite Long Contract Name For Layout ${w}: " [9] to queue. MissionId: [b${w}], ObjectiveId: []\r\n`);
    await p.waitForFunction(() => !document.getElementById('banner').hidden, null, { timeout: 8000 });
    await p.waitForTimeout(500);
    const res = await p.evaluate(AUDIT);
    await p.screenshot({ path: `${OUT}/banner-${w}x${h}.png` });
    all.push({ tag: `banner ${w}x${h}`, states: { banner: res }, errs: [] });
    await p.close();
  }
  let total = 0;
  for (const r of all) {
    const n = Object.values(r.states).reduce((a, s) => a + s.issues.length, 0); total += n;
    console.log(`${r.tag.padEnd(24)} ${Object.entries(r.states).map(([k, s]) => `${k}:${s.issues.length}${s.density !== '-' ? '/' + s.density : ''}${s.scroll ? '/scroll' : ''}`).join('  ')}  js-errors:${r.errs.length}`);
    for (const [k, s] of Object.entries(r.states)) for (const i of s.issues.slice(0, 6)) console.log(`     [${k}] ${i}`);
    for (const e of r.errs) console.log('     ERR ' + e);
  }
  console.log('TOTAL', total);
  await b.close();
  process.exit(total ? 1 : 0);
})();
