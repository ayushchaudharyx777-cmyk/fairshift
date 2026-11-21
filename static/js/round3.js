/* FairShift Round 3 UI: photo hazard, wage-theft check, integrity badge, impact calculator.
   Self-contained; uses textContent only (no innerHTML) so server data can never inject markup. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const inr = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (k === 'style') node.style.cssText = v;
      else if (k === 'text') node.textContent = v;
      else if (k === 'class') node.className = v;
      else node.setAttribute(k, v);
    });
    (children || []).forEach((c) => node.appendChild(c));
    return node;
  }

  async function api(url, opts) {
    const res = await fetch(url, opts);
    let body = null;
    try { body = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) {
      const msg = (body && (body.error && body.error.message || body.detail)) || ('Request failed (' + res.status + ')');
      throw new Error(typeof msg === 'string' ? msg : 'Request failed');
    }
    return body;
  }

  // ---------------- i18n (falls back to English if a key is missing) ----------------
  const EN_FALLBACK = {
    r3_photo_btn: '📷 Report with Photo (AI)', r3_photo_analyzing: 'AI is analyzing the photo...',
    r3_photo_too_big: 'Photo too large (max 5 MB).', r3_photo_sent: 'Sent to the site engineer and logged tamper-proof.',
    r3_photo_fail: 'Could not analyze photo: ',
    r3_queued: 'No internet. Report saved on your phone and will be sent automatically when you are back online.',
    r3_pending: 'Pending sync ({n})', r3_synced: 'Offline reports sent ✓',
    r3_wage_title: '🔍 Wage Theft Check', r3_wage_sub: 'Compare what you were paid with what the law says you should get.',
    r3_wage_ph: 'Amount you actually received (₹)', r3_wage_btn: 'Check my pay', r3_wage_fair: 'Your pay is fair ✓',
    r3_wage_under: 'Underpaid by {amt} ({pct}%)', r3_wage_over: 'Paid more than expected',
    r3_wage_expected: 'Expected take-home: {exp} · You received: {paid}', r3_wage_cause: 'Likely cause: ',
    r3_wage_invalid: 'Enter a valid amount.', r3_checking: 'Checking...'
  };
  let strings = {};
  let activeLang = localStorage.getItem('fairshift_lang') || 'en';
  const curLang = () => activeLang;
  const t = (k, vars) => {
    let v = strings[k] || EN_FALLBACK[k] || k;
    Object.entries(vars || {}).forEach(([a, b]) => { v = v.split('{' + a + '}').join(b); });
    return v;
  };
  async function loadStrings() {
    try { const r = await fetch('/static/i18n/' + curLang() + '.json'); if (r.ok) strings = await r.json(); }
    catch (_) { strings = {}; }
  }
  // Switch language. The value comes from the event/selector itself (worker.js writes localStorage only AFTER its
  // own fetch finishes, so reading storage here made these cards lag one language behind). Out-of-order loads are dropped.
  let langSeq = 0;
  async function setLang(code, relabelAll) {
    const mine = ++langSeq;
    activeLang = code;
    let next = {};
    try { const r = await fetch('/static/i18n/' + code + '.json'); if (r.ok) next = await r.json(); } catch (_) { /* keep English fallback */ }
    if (mine !== langSeq) return;
    strings = next;
    relabelAll();
  }

  // ---------------- Offline queue (IndexedDB) for photo reports ----------------
  const DB_NAME = 'fairshift_r3', STORE = 'pending';
  function openDb() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) return reject(new Error('no-idb'));
      const req = window.indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  function tx(mode, fn) {
    return openDb().then((db) => new Promise((resolve, reject) => {
      const t0 = db.transaction(STORE, mode); const out = fn(t0.objectStore(STORE));
      t0.oncomplete = () => { db.close(); resolve(out && out.result !== undefined ? out.result : undefined); };
      t0.onerror = () => { db.close(); reject(t0.error); };
    }));
  }
  const queueAdd = (item) => tx('readwrite', (s) => s.add(item));
  const queueAll = () => tx('readonly', (s) => s.getAll());
  const queueDel = (id) => tx('readwrite', (s) => s.delete(id));

  async function postPhoto(blob, lang, note) {
    const fd = new FormData();
    fd.append('photo', blob, 'hazard.jpg'); fd.append('language', lang); if (note) fd.append('note', note);
    return fetch('/api/v1/worker/hazard-photo', { method: 'POST', body: fd });
  }

  // Sync every queued report. Keeps items on network error / 401 / 5xx; drops items the server permanently rejects.
  let syncing = false;
  async function syncQueue(onChange) {
    if (syncing) return { sent: 0, left: 0 };
    syncing = true; let sent = 0;
    try {
      let items = []; try { items = await queueAll(); } catch (_) { return { sent: 0, left: 0 }; }
      for (const it of items) {
        try {
          const res = await postPhoto(it.blob, it.lang, it.note);
          if (res.ok || [400, 413, 415, 422].includes(res.status)) { await queueDel(it.id); if (res.ok) sent++; }
          else break; // 401 / 429 / 5xx: stop and retry later
        } catch (_) { break; } // still offline
      }
      let left = 0; try { left = (await queueAll()).length; } catch (_) { /* ignore */ }
      if (onChange) onChange(sent, left);
      return { sent, left };
    } finally { syncing = false; }
  }

  // ---------------- Worker: photo hazard ----------------
  function initPhoto(slot) {
    const input = el('input', { type: 'file', accept: 'image/*', capture: 'environment', style: 'display:none' });
    const btn = el('button', { class: 'btn btn-secondary', style: 'width:100%; margin-top:0.6rem;' });
    const chip = el('div', { style: 'margin-top:0.4rem; font-size:0.8rem; color:#F59E0B; display:none;' });
    const result = el('div', { style: 'margin-top:0.6rem; font-size:0.85rem;' });
    const label = () => { btn.textContent = t('r3_photo_btn'); };
    label();

    async function refreshChip(sent) {
      let n = 0; try { n = (await queueAll()).length; } catch (_) { /* ignore */ }
      chip.style.display = n ? 'block' : 'none'; chip.textContent = n ? t('r3_pending', { n: n }) : '';
      if (sent) { result.textContent = t('r3_synced'); }
    }
    btn.addEventListener('click', () => input.click());
    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) { result.textContent = t('r3_photo_too_big'); return; }
      btn.disabled = true; btn.textContent = t('r3_photo_analyzing'); result.textContent = '';
      const lang = curLang();
      try {
        if (navigator.onLine === false) throw new TypeError('offline');
        const res = await postPhoto(file, lang, '');
        let body = null; try { body = await res.json(); } catch (_) { /* ignore */ }
        if (!res.ok) throw new Error((body && (body.error && body.error.message || body.detail)) || ('HTTP ' + res.status));
        result.textContent = '';
        result.appendChild(el('strong', { text: body.severity.toUpperCase() + ' · ' + body.category.toUpperCase() }));
        result.appendChild(el('div', { text: lang === 'en' ? body.summary_en : body.summary_local, style: 'margin-top:0.25rem;' }));
        result.appendChild(el('div', { text: t('r3_photo_sent'), style: 'color:var(--text-secondary); margin-top:0.25rem;' }));
      } catch (e) {
        if (e && e.name === 'TypeError') { // network failure => keep the evidence, send later
          try { await queueAdd({ blob: file, lang: lang, note: '', ts: Date.now() }); result.textContent = t('r3_queued'); }
          catch (_) { result.textContent = t('r3_photo_fail') + 'storage unavailable'; }
        } else { result.textContent = t('r3_photo_fail') + e.message; }
      } finally {
        btn.disabled = false; label(); input.value = ''; refreshChip(0);
      }
    });
    window.addEventListener('online', () => syncQueue((sent) => refreshChip(sent)));
    slot.append(input, btn, chip, result);
    refreshChip(0);
    if (navigator.onLine !== false) syncQueue((sent) => refreshChip(sent));
    return { relabel: label, refreshChip: refreshChip };
  }

  // ---------------- Worker: wage check ----------------
  function initWage(slot) {
    const amount = el('input', { type: 'number', min: '0', step: '1', inputmode: 'numeric', class: 'input-field' });
    const btn = el('button', { class: 'btn btn-primary', style: 'width:100%; margin-top:0.6rem;' });
    const out = el('div', { style: 'margin-top:0.75rem;' });
    const title = el('h4', { style: 'font-size:0.95rem; margin-bottom:0.25rem;' });
    const sub = el('p', { style: 'font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.6rem;' });
    const relabel = () => { title.textContent = t('r3_wage_title'); sub.textContent = t('r3_wage_sub');
      amount.setAttribute('placeholder', t('r3_wage_ph')); btn.textContent = t('r3_wage_btn'); };
    relabel();
    btn.addEventListener('click', async () => {
      const v = parseFloat(amount.value);
      if (!isFinite(v) || v < 0) { out.textContent = t('r3_wage_invalid'); return; }
      btn.disabled = true; out.textContent = t('r3_checking');
      try {
        const r = await api('/api/v1/worker/wage-check', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ paid_amount: v }),
        });
        const colors = { fair: '#10B981', underpaid: '#EF4444', overpaid: '#F59E0B' };
        const headline = r.verdict === 'underpaid' ? t('r3_wage_under', { amt: inr(r.shortfall), pct: r.shortfall_percent })
          : r.verdict === 'fair' ? t('r3_wage_fair') : t('r3_wage_over');
        out.textContent = '';
        out.appendChild(el('div', { style: 'font-weight:700; font-size:1.05rem; color:' + colors[r.verdict], text: headline }));
        out.appendChild(el('div', { style: 'font-size:0.85rem; margin-top:0.25rem;', text: t('r3_wage_expected', { exp: inr(r.expected_net), paid: inr(r.paid_amount) }) }));
        if (r.likely_cause) out.appendChild(el('div', { style: 'font-size:0.85rem; margin-top:0.25rem; color:#F59E0B;', text: t('r3_wage_cause') + r.likely_cause }));
        out.appendChild(el('div', { style: 'font-size:0.72rem; margin-top:0.4rem; color:var(--text-secondary);', text: r.legal_note }));
      } catch (e) { out.textContent = e.message; }
      finally { btn.disabled = false; }
    });
    slot.appendChild(el('div', { class: 'card' }, [title, sub, amount, btn, out]));
    return { relabel: relabel };
  }

  // ---------------- Admin: integrity + impact ----------------
  function initAdmin(slot) {
    const badge = el('span', { class: 'badge badge-info', text: 'Integrity: checking...' });
    const detail = el('div', { style: 'font-size:0.75rem; color:var(--text-secondary); margin-top:0.35rem;' });
    const refresh = el('button', { class: 'btn btn-secondary btn-sm', text: 'Verify now' });

    async function verify() {
      try {
        const r = await api('/api/v1/admin/integrity-check');
        badge.className = 'badge ' + (r.valid ? 'badge-success' : 'badge-critical');
        badge.textContent = r.valid ? 'Integrity: Verified ✓ (' + r.checked + ' reports)' : 'Integrity: TAMPERING DETECTED';
        detail.textContent = r.valid ? 'Head hash ' + r.head_hash.slice(0, 16) + '…' : (r.reason + ' · report ' + r.broken_report_id);
      } catch (e) { badge.textContent = 'Integrity: unavailable'; }
    }
    refresh.addEventListener('click', verify);

    const slider = el('input', { type: 'range', min: '100', max: '100000', step: '100', value: '1000', style: 'width:100%;' });
    const rate = el('input', { type: 'range', min: '0', max: '100', step: '5', value: '30', style: 'width:100%;' });
    const big = el('div', { style: 'font-size:1.8rem; font-weight:800; color:var(--color-primary);' });
    const sub = el('div', { style: 'font-size:0.82rem; color:var(--text-secondary);' });
    const assume = el('div', { style: 'font-size:0.72rem; color:var(--text-secondary); margin-top:0.4rem;' });
    const lbl1 = el('label', { style: 'font-size:0.8rem;' });
    const lbl2 = el('label', { style: 'font-size:0.8rem;' });

    let timer = null;
    async function impact() {
      lbl1.textContent = 'Workers covered: ' + Number(slider.value).toLocaleString('en-IN');
      lbl2.textContent = 'Assumed share underpaid: ' + rate.value + '%';
      try {
        const r = await api('/api/v1/admin/impact?workers=' + slider.value + '&theft_rate=' + (rate.value / 100));
        big.textContent = inr(r.estimated_annual_wage_protected_inr) + ' / year';
        sub.textContent = 'overtime premium protected for ' + r.workers_affected.toLocaleString('en-IN') + ' workers · ' + r.workers_at_fatigue_risk_percent + '% of current workers at fatigue risk';
        assume.textContent = 'Illustrative model. ' + r.assumptions.basis + '. ' + r.assumptions.model;
      } catch (e) { big.textContent = 'Unavailable'; }
    }
    [slider, rate].forEach((s) => s.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(impact, 150); }));

    const aiBadge = el('span', { class: 'badge badge-info', text: 'AI: checking...' });
    const aiDetail = el('div', { style: 'font-size:0.75rem; color:var(--text-secondary); margin-top:0.35rem;' });
    const aiBtn = el('button', { class: 'btn btn-secondary btn-sm', text: 'Test AI now' });
    async function aiStatus() {
      try {
        const r = await api('/api/v1/admin/ai-status');
        if (!r.configured) {
          aiBadge.className = 'badge badge-critical'; aiBadge.textContent = 'AI: NOT CONFIGURED (offline templates)';
          aiDetail.textContent = 'Add GEMINI_API_KEY in Render > Environment, then redeploy.'; return;
        }
        const bad = r.error_count > 0 && (!r.last_ok_at || (r.last_error_at && r.last_error_at > r.last_ok_at));
        aiBadge.className = 'badge ' + (bad ? 'badge-warning' : 'badge-success');
        aiBadge.textContent = bad ? 'AI: key set, last call FAILED' : 'AI: Gemini configured ✓';
        aiDetail.textContent = 'Model ' + r.model + ' · ok ' + r.ok_count + ' · errors ' + r.error_count + ' · offline fallbacks ' + r.fallback_count + (r.last_error ? ' · last error: ' + r.last_error : '');
      } catch (e) { aiBadge.textContent = 'AI: status unavailable'; }
    }
    aiBtn.addEventListener('click', async () => {
      aiBtn.disabled = true; aiDetail.textContent = 'Calling Gemini...';
      try {
        const r = await api('/api/v1/admin/ai-selftest', { method: 'POST' });
        aiBadge.className = 'badge ' + (r.ok ? 'badge-success' : 'badge-critical');
        aiBadge.textContent = r.ok ? 'AI: LIVE ✓ ' + r.latency_ms + ' ms' : 'AI: FAILED';
        aiDetail.textContent = r.ok ? 'Gemini (' + r.model + ') answered in ' + r.latency_ms + ' ms.' : (r.error || 'Unknown error');
      } catch (e) { aiBadge.className = 'badge badge-critical'; aiBadge.textContent = 'AI: FAILED'; aiDetail.textContent = e.message; }
      finally { aiBtn.disabled = false; }
    });

    slot.appendChild(el('div', { class: 'card' }, [
      el('div', { style: 'display:flex; justify-content:space-between; align-items:center; gap:0.5rem; flex-wrap:wrap;' }, [
        el('div', {}, [el('h3', { style: 'font-size:1.05rem;', text: '🤖 Gemini AI Status' }), aiDetail]), aiBadge, aiBtn]),
    ]));
    aiStatus();

    slot.appendChild(el('div', { class: 'card' }, [
      el('div', { style: 'display:flex; justify-content:space-between; align-items:center; gap:0.5rem; flex-wrap:wrap;' }, [
        el('div', {}, [el('h3', { style: 'font-size:1.05rem;', text: '🔒 Tamper-Proof Safety Log' }), detail]), badge, refresh]),
      el('hr', { style: 'border:none; border-top:1px solid var(--border-strong); margin:1rem 0;' }),
      el('h3', { style: 'font-size:1.05rem; margin-bottom:0.5rem;', text: '📈 Impact Calculator' }),
      lbl1, slider, lbl2, rate, big, sub, assume,
    ]));
    verify(); impact();
  }

  async function boot() {
    await loadStrings();
    const p = $('r3PhotoSlot'); const photo = p ? initPhoto(p) : null;
    const w = $('r3WageSlot'); const wage = w ? initWage(w) : null;
    const a = $('r3AdminSlot'); if (a) initAdmin(a);
    const relabelAll = () => {
      if (photo) { photo.relabel(); photo.refreshChip(0); }
      if (wage) wage.relabel();
    };
    document.querySelectorAll('select.select-lang, #langSelector').forEach((sel) =>
      sel.addEventListener('change', (e) => setLang(e.target.value, relabelAll)));
    window.addEventListener('fairshift:langchange', (e) => { if (e.detail && e.detail.lang !== activeLang) setLang(e.detail.lang, relabelAll); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();

  // test hook (no effect in production)
  window.__fairshiftR3 = { syncQueue: syncQueue, queueAll: queueAll, queueAdd: queueAdd, t: t, setLang: setLang };
})();
