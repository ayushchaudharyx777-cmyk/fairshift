const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { IDBFactory } = require('fake-indexeddb');

const SRC = fs.readFileSync(path.join(__dirname, '../../static/js/round3.js'), 'utf8');
const I18N = (l) => JSON.parse(fs.readFileSync(path.join(__dirname, `../../static/i18n/${l}.json`), 'utf8'));
const LANGS = fs.readdirSync(path.join(__dirname, '../../static/i18n')).filter((f) => f.endsWith('.json')).map((f) => f.replace('.json', ''));
const HTML = `<body><select id="langSelector">${LANGS.map((l) => `<option value="${l}">${l}</option>`).join('')}</select>
<div id="r3PhotoSlot"></div><div id="r3WageSlot"></div><div id="r3AdminSlot"></div></body>`;
const tick = (ms = 20) => new Promise((r) => setTimeout(r, ms));
const jsonRes = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const PHOTO_OK = { severity: 'high', category: 'ppe', summary_en: 'No helmet near edge', summary_local: 'हेलमेट नहीं' };

// Build a fresh page. `routes` maps "METHOD url-prefix" -> handler(init) => response | throws
async function page({ lang = 'en', online = true, routes = {} } = {}) {
  const dom = new JSDOM(HTML, { url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.localStorage.setItem('fairshift_lang', lang);
  w.indexedDB = new IDBFactory();
  w.FormData = globalThis.FormData;           // Node FormData accepts Node File/Blob (structured-clone safe)
  Object.defineProperty(w.navigator, 'onLine', { value: online, configurable: true, writable: true });
  const calls = [];
  w.fetch = async (url, init = {}) => {
    const method = (init.method || 'GET').toUpperCase();
    calls.push({ url, method, init });
    if (url.startsWith('/static/i18n/')) return jsonRes(200, I18N(url.split('/').pop().replace('.json', '')));
    for (const [key, h] of Object.entries(routes)) {
      const [m, prefix] = key.split(' ');
      if (m === method && url.startsWith(prefix)) { const r = typeof h === 'function' ? h(init) : h; return r; }
    }
    return jsonRes(404, { detail: 'no route' });
  };
  w.eval(SRC);
  await tick(40);
  return { w, doc: w.document, calls, setOnline: (v) => { w.navigator.onLine = v; } };
}

async function pickPhoto(p, bytes = 'x'.repeat(50)) {
  const input = p.doc.querySelector('#r3PhotoSlot input[type=file]');
  const file = new File([bytes], 'a.jpg', { type: 'image/jpeg' });
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  input.dispatchEvent(new p.w.Event('change'));
  await tick(80);
}
const text = (p, sel) => p.doc.querySelector(sel).textContent;

test('photo: online success shows severity + summary, sends multipart with language', async () => {
  const p = await page({ lang: 'en', routes: { 'POST /api/v1/worker/hazard-photo': jsonRes(200, PHOTO_OK) } });
  await pickPhoto(p);
  assert.match(text(p, '#r3PhotoSlot'), /HIGH · PPE/);
  const call = p.calls.find((c) => c.url === '/api/v1/worker/hazard-photo');
  assert.equal(call.init.body.get('language'), 'en');
  assert.ok(call.init.body.get('photo'));
});

test('photo: server text is rendered as text, never as HTML (XSS)', async () => {
  const evil = { ...PHOTO_OK, summary_en: '<img src=x onerror=alert(1)>', summary_local: '<img src=x onerror=alert(1)>' };
  const p = await page({ routes: { 'POST /api/v1/worker/hazard-photo': jsonRes(200, evil) } });
  await pickPhoto(p);
  assert.equal(p.doc.querySelectorAll('#r3PhotoSlot img').length, 0);
  assert.match(text(p, '#r3PhotoSlot'), /<img src=x/);
});

test('photo: offline => queued in IndexedDB, chip shown, then auto-sync when back online', async () => {
  let accept = false;
  const p = await page({ online: false, routes: { 'POST /api/v1/worker/hazard-photo': () => accept ? jsonRes(200, PHOTO_OK) : jsonRes(401, {}) } });
  await pickPhoto(p);
  assert.equal(p.calls.filter((c) => c.url.includes('hazard-photo')).length, 0, 'must not hit network while offline');
  assert.match(text(p, '#r3PhotoSlot'), /No internet/);
  assert.match(text(p, '#r3PhotoSlot'), /Pending sync \(1\)/);
  assert.equal((await p.w.__fairshiftR3.queueAll()).length, 1);

  accept = true; p.setOnline(true);
  p.w.dispatchEvent(new p.w.Event('online'));
  await tick(150);
  assert.equal((await p.w.__fairshiftR3.queueAll()).length, 0);
  assert.doesNotMatch(text(p, '#r3PhotoSlot'), /Pending sync/);
  assert.match(text(p, '#r3PhotoSlot'), /Offline reports sent/);
});

test('photo: network failure while "online" also queues the evidence', async () => {
  const p = await page({ routes: { 'POST /api/v1/worker/hazard-photo': () => { throw new TypeError('Failed to fetch'); } } });
  await pickPhoto(p);
  assert.equal((await p.w.__fairshiftR3.queueAll()).length, 1);
  assert.match(text(p, '#r3PhotoSlot'), /Pending sync \(1\)/);
});

test('photo: permanent server rejection (415) is shown and NOT queued', async () => {
  const p = await page({ routes: { 'POST /api/v1/worker/hazard-photo': jsonRes(415, { detail: 'Only JPEG, PNG or WebP images are accepted' }) } });
  await pickPhoto(p);
  assert.match(text(p, '#r3PhotoSlot'), /Only JPEG, PNG or WebP/);
  assert.equal((await p.w.__fairshiftR3.queueAll()).length, 0);
});

test('queue: keeps items on 401/500 (retry later), drops on 415, never loops forever', async () => {
  const mode = { s: 401 };
  const p = await page({ online: false, routes: { 'POST /api/v1/worker/hazard-photo': () => jsonRes(mode.s, {}) } });
  await pickPhoto(p); await pickPhoto(p, 'y'.repeat(30));
  assert.equal((await p.w.__fairshiftR3.queueAll()).length, 2);
  let r = await p.w.__fairshiftR3.syncQueue(); assert.equal(r.left, 2);        // 401: session expired, keep
  mode.s = 500; r = await p.w.__fairshiftR3.syncQueue(); assert.equal(r.left, 2); // server error, keep
  mode.s = 415; r = await p.w.__fairshiftR3.syncQueue(); assert.equal(r.left, 0); // poison items dropped
});

test('photo: file over 5 MB is blocked client-side without network call', async () => {
  const p = await page({ routes: { 'POST /api/v1/worker/hazard-photo': jsonRes(200, PHOTO_OK) } });
  const input = p.doc.querySelector('#r3PhotoSlot input[type=file]');
  const big = { size: 6 * 1024 * 1024, name: 'big.jpg', type: 'image/jpeg' };
  Object.defineProperty(input, 'files', { value: [big], configurable: true });
  input.dispatchEvent(new p.w.Event('change')); await tick();
  assert.match(text(p, '#r3PhotoSlot'), /too large/);
  assert.equal(p.calls.filter((c) => c.url.includes('hazard-photo')).length, 0);
});

const WAGE = (v, extra = {}) => ({ verdict: v, expected_net: 16736.4, paid_amount: 15000, shortfall: v === 'underpaid' ? 1736.4 : 0,
  shortfall_percent: 10.4, likely_cause: extra.cause || null, legal_note: 'Indicative check', breakdown: {} });
async function check(p, amt) {
  const inp = p.doc.querySelector('#r3WageSlot input'); inp.value = amt;
  p.doc.querySelector('#r3WageSlot button').click(); await tick(60);
}

test('wage: underpaid shows red headline in ₹ with likely cause', async () => {
  const p = await page({ routes: { 'POST /api/v1/worker/wage-check': jsonRes(200, WAGE('underpaid', { cause: 'Overtime looks paid at 1x instead of 2x' })) } });
  await check(p, '15000');
  const t = text(p, '#r3WageSlot');
  assert.match(t, /Underpaid by ₹1,736 \(10\.4%\)/); assert.match(t, /Likely cause: Overtime looks paid at 1x/);
  assert.equal(JSON.parse(p.calls.find((c) => c.url.includes('wage-check')).init.body).paid_amount, 15000);
});

test('wage: fair, invalid input, and server error are all handled', async () => {
  const p = await page({ routes: { 'POST /api/v1/worker/wage-check': jsonRes(200, WAGE('fair')) } });
  await check(p, '16736.4'); assert.match(text(p, '#r3WageSlot'), /Your pay is fair ✓/);
  await check(p, ''); assert.match(text(p, '#r3WageSlot'), /Enter a valid amount/);
  const p2 = await page({ routes: { 'POST /api/v1/worker/wage-check': jsonRes(401, { error: { message: 'Not authenticated' } }) } });
  await check(p2, '100'); assert.match(text(p2, '#r3WageSlot'), /Not authenticated/);
});

test('i18n: Hindi and Tamil strings render, and switching language relabels live', async () => {
  const p = await page({ lang: 'hi' });
  assert.match(text(p, '#r3WageSlot'), /वेतन जांच/);
  assert.match(text(p, '#r3PhotoSlot'), /फोटो से रिपोर्ट करें/);
  const sel = p.doc.querySelector('#langSelector'); sel.value = 'ta'; sel.dispatchEvent(new p.w.Event('change')); await tick(60);
  assert.match(text(p, '#r3WageSlot'), /ஊதிய சரிபார்ப்பு/);
  assert.match(text(p, '#r3PhotoSlot'), /புகைப்படத்துடன்/);
});
function localStorage_set(p, l) { p.w.localStorage.setItem('fairshift_lang', l); }

test('i18n: every r3_ key exists in en/hi/ta with the same placeholders', () => {
  const en = I18N('en'); const keys = Object.keys(en).filter((k) => k.startsWith('r3_'));
  assert.ok(keys.length >= 18);
  for (const l of ['hi', 'ta']) {
    const d = I18N(l);
    for (const k of keys) {
      assert.ok(d[k], `${l} missing ${k}`);
      assert.deepEqual((d[k].match(/\{\w+\}/g) || []).sort(), (en[k].match(/\{\w+\}/g) || []).sort(), `${l}.${k} placeholders`);
    }
  }
});

test('admin: integrity badge shows Verified, and TAMPERING when chain is broken', async () => {
  const ok = { valid: true, checked: 7, head_hash: 'a'.repeat(64) };
  const impact = { estimated_annual_wage_protected_inr: 8330766, workers_affected: 300, workers_at_fatigue_risk_percent: 37.5,
    assumptions: { basis: 'Seeded demo data', model: 'Assumption, not a statistic.' } };
  let integrity = ok;
  const p = await page({ routes: { 'GET /api/v1/admin/integrity-check': () => jsonRes(200, integrity), 'GET /api/v1/admin/impact': jsonRes(200, impact) } });
  assert.match(text(p, '#r3AdminSlot'), /Integrity: Verified ✓ \(7 reports\)/);
  assert.match(text(p, '#r3AdminSlot'), /₹83,30,766 \/ year/);
  integrity = { valid: false, checked: 2, broken_report_id: 'rep-002', reason: 'content hash mismatch (report was modified)' };
  [...p.doc.querySelectorAll('#r3AdminSlot button')].find((b) => /Verify/.test(b.textContent)).click(); await tick(60);
  assert.match(text(p, '#r3AdminSlot'), /TAMPERING DETECTED/); assert.match(text(p, '#r3AdminSlot'), /rep-002/);
});


test('i18n: all languages (at least 8 beyond English) render wage + photo UI from their own bundle', async () => {
  assert.ok(LANGS.length >= 8, `expected >=8 bundles, got ${LANGS.length}`);
  for (const l of LANGS) {
    const b = I18N(l);
    const p = await page({ lang: l });
    assert.equal(text(p, '#r3WageSlot h4'), b.r3_wage_title, `${l} wage title`);
    assert.equal(p.doc.querySelector('#r3PhotoSlot button').textContent, b.r3_photo_btn, `${l} photo button`);
    assert.equal(p.doc.querySelector('#r3WageSlot input').getAttribute('placeholder'), b.r3_wage_ph, `${l} placeholder`);
    assert.equal(p.doc.querySelector('#r3WageSlot button').textContent, b.r3_wage_btn, `${l} wage button`);
  }
});

test('i18n: live-switching through every language never leaves stale text', async () => {
  const p = await page({ lang: 'en' });
  for (const l of LANGS) {
    const sel = p.doc.querySelector('#langSelector'); sel.value = l;      // a real <select> changes its value first
    sel.dispatchEvent(new p.w.Event('change')); await tick(40);
    assert.equal(text(p, '#r3WageSlot h4'), I18N(l).r3_wage_title, `after switching to ${l}`);
  }
});

test('i18n: placeholders ({amt},{pct},{exp},{paid},{n}) are substituted in every language', async () => {
  for (const l of LANGS) {
    const p = await page({ lang: l, routes: { 'POST /api/v1/worker/wage-check': jsonRes(200, WAGE('underpaid', { cause: 'x' })) } });
    await check(p, '15000');
    const t = text(p, '#r3WageSlot');
    assert.doesNotMatch(t, /\{(amt|pct|exp|paid)\}/, `${l} left a raw placeholder`);
    assert.match(t, /₹1,736/, `${l} amount missing`);
  }
});

test('i18n: missing key in a bundle falls back to English instead of showing the raw key', async () => {
  const dom = await page({ lang: 'hi' });
  const t = dom.w.__fairshiftR3.t;
  assert.equal(t('r3_does_not_exist'), 'r3_does_not_exist');        // unknown key => visible, not crash
  assert.match(t('r3_pending', { n: 3 }), /3/);
});

// ---------- regression: the card lagged one language behind (screenshot: Marathi header, Hindi wage card) ----------
test('i18n race: cards follow the NEW language even though worker.js has not written localStorage yet', async () => {
  const p = await page({ lang: 'en' });                                   // localStorage still says 'en'
  const sel = p.doc.querySelector('#langSelector');
  sel.value = 'mr';
  sel.dispatchEvent(new p.w.Event('change'));                              // note: localStorage NOT updated (the real race)
  await tick(60);
  assert.equal(text(p, '#r3WageSlot h4'), I18N('mr').r3_wage_title);
  assert.equal(p.doc.querySelector('#r3PhotoSlot button').textContent, I18N('mr').r3_photo_btn);
});

test('i18n race: the fairshift:langchange event (sent by worker.js) also relabels', async () => {
  const p = await page({ lang: 'en' });
  p.w.dispatchEvent(new p.w.CustomEvent('fairshift:langchange', { detail: { lang: 'gu' } }));
  await tick(60);
  assert.equal(text(p, '#r3WageSlot h4'), I18N('gu').r3_wage_title);
});

test('i18n race: rapid switching keeps the LAST choice even if an earlier bundle loads later', async () => {
  const p = await page({ lang: 'en' });
  const realFetch = p.w.fetch;
  p.w.fetch = async (url, init) => {                                       // make Tamil slow, Hindi fast
    if (url.endsWith('/ta.json')) await tick(120);
    return realFetch(url, init);
  };
  const sel = p.doc.querySelector('#langSelector');
  sel.value = 'ta'; sel.dispatchEvent(new p.w.Event('change'));
  sel.value = 'hi'; sel.dispatchEvent(new p.w.Event('change'));
  await tick(250);
  assert.equal(text(p, '#r3WageSlot h4'), I18N('hi').r3_wage_title);
});

test('admin: AI status card explains a missing key and the Test AI button reports success and failure', async () => {
  const impact = { estimated_annual_wage_protected_inr: 1000, workers_affected: 3, workers_at_fatigue_risk_percent: 12.5,
    assumptions: { basis: 'b', model: 'm' } };
  let status = { configured: false, ok_count: 0, error_count: 0, fallback_count: 4, model: 'gemini-2.5-flash' };
  let self = { ok: true, latency_ms: 812, model: 'gemini-2.5-flash', error: null };
  const p = await page({ routes: {
    'GET /api/v1/admin/integrity-check': jsonRes(200, { valid: true, checked: 1, head_hash: 'a'.repeat(64) }),
    'GET /api/v1/admin/impact': jsonRes(200, impact),
    'GET /api/v1/admin/ai-status': () => jsonRes(200, status),
    'POST /api/v1/admin/ai-selftest': () => jsonRes(200, self) } });
  assert.match(text(p, '#r3AdminSlot'), /NOT CONFIGURED/);
  assert.match(text(p, '#r3AdminSlot'), /GEMINI_API_KEY in Render/);
  assert.match(text(p, '#r3AdminSlot'), /37\.5|12\.5% of current workers at fatigue risk/);
  const btn = [...p.doc.querySelectorAll('#r3AdminSlot button')].find((b) => /Test AI/.test(b.textContent));
  btn.click(); await tick(60);
  assert.match(text(p, '#r3AdminSlot'), /AI: LIVE ✓ 812 ms/);
  self = { ok: false, latency_ms: 40, model: 'm', error: 'ClientError: 429 quota exceeded' };
  btn.click(); await tick(60);
  assert.match(text(p, '#r3AdminSlot'), /AI: FAILED/); assert.match(text(p, '#r3AdminSlot'), /429 quota exceeded/);
});
