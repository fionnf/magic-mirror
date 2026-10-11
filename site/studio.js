// The studio on an edition's page: play the piece with your own hands. Every control is something the
// wall hears or knows (bass, the hour, the day's listening...); moving one takes over from the room.
(() => {
  const S = document.getElementById('studio'), F = window.Fortuna;
  if (!S || !F || !F.pieces.length) { if (S) S.hidden = true; return; }
  const p = F.pieces[0], meta = JSON.parse(S.dataset.meta);
  const $ = sel => S.querySelector(sel), $$ = sel => [...S.querySelectorAll(sel)];
  const knobs = $$('input[data-u]'), swatches = $$('input[data-c]');
  const dayEl = $('.day.draw'), hourOut = $('[data-hour]');
  let mode = 'live';                       // 'still' | 'live' | 'fast' | 'day'
  const hh = h => { const m = Math.round(h * 60) % 1440; return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); };

  function show() {
    for (const k of knobs) {
      const v = k.dataset.u === 'clock' ? p.over.clock : p.over[k.dataset.u];
      k.closest('label').classList.toggle('held', v != null);
      if (document.activeElement !== k && (v != null || k.dataset.u in F.ears.f)) k.value = v != null ? v : F.ears.f[k.dataset.u];
      const out = k.closest('label').querySelector('output');
      out.textContent = k.dataset.u === 'clock' ? (v == null ? 'now' : hh(v)) : v == null ? (F.ears.on ? 'your room' : 'the room') : (+v).toFixed(k.step < 1 ? 2 : 0);
    }
    swatches.forEach((s, i) => { if (document.activeElement !== s) s.value = (p.over.pal || p.pal)[i]; });
    const day = p.over.day || p.day;
    [...dayEl.children].forEach((b, i) => { b.style.height = Math.max(2, (day[i] || 0) * 100) + '%'; });
    dayEl.classList.toggle('held', !!p.over.day);
    $$('[data-speed]').forEach(b => b.setAttribute('aria-pressed', b.dataset.speed === mode));
    $('[data-reset]').disabled = !Object.keys(p.over).length && mode === 'live';
  }

  for (const k of knobs) k.addEventListener('input', () => {
    if (k.dataset.u === 'clock' && mode === 'day') setMode('live');
    p.over[k.dataset.u === 'clock' ? 'clock' : k.dataset.u] = +k.value; show();
  });
  swatches.forEach((s, i) => s.addEventListener('input', () => {
    p.over.pal = (p.over.pal || p.pal).slice(); p.over.pal[i] = s.value; show();
    document.querySelector('.piece').style.setProperty('--glow', p.over.pal[1]);
  }));

  // draw the day's listening with a finger: 24 hours, loud at the top
  let stroke = null;                       // the last hour touched, so a quick swipe fills every hour it crosses
  const paint = ev => {
    const r = dayEl.getBoundingClientRect();
    const i = Math.max(0, Math.min(23, Math.floor((ev.clientX - r.left) / r.width * 24)));
    const v = Math.round(Math.max(0, Math.min(1, 1 - (ev.clientY - r.top) / r.height)) * 100) / 100;
    p.over.day = (p.over.day || p.day.slice()).slice(); while (p.over.day.length < 24) p.over.day.push(0);
    const [i0, v0] = stroke || [i, v], n = Math.abs(i - i0);
    for (let k = 0; k <= n; k++) p.over.day[i0 + Math.sign(i - i0) * k] = n ? v0 + (v - v0) * k / n : v;
    stroke = [i, v]; show();
  };
  dayEl.addEventListener('pointerdown', ev => { stroke = null; dayEl.setPointerCapture(ev.pointerId); paint(ev); ev.preventDefault(); });
  dayEl.addEventListener('pointermove', ev => { if (dayEl.hasPointerCapture(ev.pointerId)) paint(ev); });

  // time: hold it still, let it run, hurry it, or watch a whole day pass in a minute
  function setMode(m) {
    mode = m; p.speed = {still: 0, live: 1, fast: 12, day: 20}[m];
    if (m === 'day' && p.over.clock == null) { const d = new Date(); p.over.clock = d.getHours() + d.getMinutes() / 60; }
    show();
  }
  $$('[data-speed]').forEach(b => b.addEventListener('click', () => setMode(b.dataset.speed)));
  let last = performance.now();
  (function tick(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (mode === 'day') { p.over.clock = (p.over.clock + dt * 24 / 60) % 24; const k = knobs.find(k => k.dataset.u === 'clock'); k.value = p.over.clock; hourOut.textContent = hh(p.over.clock); }
    requestAnimationFrame(tick);
  })(last);

  $('[data-reset]').addEventListener('click', () => {
    p.over = {}; setMode('live'); history.replaceState(null, '', location.pathname);
    document.querySelector('.piece').style.setProperty('--glow', p.pal[1]); say('Back to the room');
  });

  // a version can be passed on as a link
  const enc = o => btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const dec = s => JSON.parse(decodeURIComponent(escape(atob(s.replace(/-/g, '+').replace(/_/g, '/')))));
  $('[data-link]').addEventListener('click', async () => {
    const url = location.origin + location.pathname + '#v=' + enc({o: p.over, m: mode});
    history.replaceState(null, '', url);
    try { await navigator.clipboard.writeText(url); say('Link to your version copied'); } catch (e) { say('The link is in the address bar'); }
  });
  const m = location.hash.match(/#v=([\w-]+)/);
  if (m) try {
    const v = dec(m[1]); p.over = v.o || {}; setMode(v.m || 'live');
    if (p.over.pal) document.querySelector('.piece').style.setProperty('--glow', p.over.pal[1]);
    S.open = true; say('Someone’s version of this piece');
  } catch (e) {}

  // postcards
  const card = () => ({name: meta.name, slug: meta.date + (Object.keys(p.over).length ? '-remix' : ''),
                      line: `${meta.when} · Fortuna, made by Dewa and Fionn` + (Object.keys(p.over).length ? ' · your version' : '')});
  $('[data-still]').addEventListener('click', async ev => {
    const b = ev.currentTarget; b.disabled = true; try { await F.postcard(p, card()); } finally { b.disabled = false; }
  });
  const rec = $('[data-record]');
  if (!F.canRecord || F.still) rec.hidden = true;
  rec.addEventListener('click', async () => {
    rec.disabled = true; const label = rec.textContent;
    try { await F.record(p, card(), 8, f => { rec.textContent = `Recording ${Math.ceil(8 - f * 8)} s`; }); }
    catch (e) { say('This browser cannot record video'); }
    finally { rec.textContent = label; rec.disabled = false; }
  });

  const live = $('[role=status]');
  function say(t) { live.textContent = t; clearTimeout(say.t); say.t = setTimeout(() => { live.textContent = ''; }, 3000); }
  setInterval(show, 250);              // free knobs follow the room
  show();
})();
