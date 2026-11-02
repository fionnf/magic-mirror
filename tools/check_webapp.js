#!/usr/bin/env node
/* Smoke test for the wall's control web app (panel_setup/web/index.html).

   It loads the page for real in jsdom (scripts run), stubs what jsdom lacks (canvas, dialogs, Image
   loading, observers, clipboard...), lets GET requests reach the wall, and BLOCKS every non-GET request
   (so nothing on the wall is ever changed). It then checks that start() completed, that the polling and
   preview loops were installed, that the preview <img id="now"> got a src, clicks every nav tab and
   filter chip, and reports every uncaught error / unhandled rejection / console.error.

   Run (needs jsdom 24, e.g. `npm i jsdom@24` in any scratch dir):
     NODE_PATH=/path/to/node_modules node tools/check_webapp.js [http://mirror4.local/] [local/index.html]
   With a second argument the page HTML is read from that file (e.g. panel_setup/web/index.html) instead of
   being downloaded, while all /api/* calls still go to the wall (GET only). Use the wall IP rather than
   mirror4.local: node resolves .local slowly and parallel requests time out.
   Exit code 0 = zero errors and app running; 1 otherwise. */
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('fs');
const URL0 = process.argv[2] || 'http://mirror4.local/', FILE = process.argv[3];
const errors = [], blocked = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push('jsdomError: ' + (e.detail && e.detail.stack || e.stack || e.message)));
vc.on('error', (...a) => errors.push('console.error: ' + a.map(x => x && x.stack || String(x)).join(' ')));
const intervals = [];
const sleep = ms => new Promise(r => setTimeout(r, ms));
process.on('unhandledRejection', e => errors.push('node unhandledRejection: ' + (e && e.stack || e)));

(async () => {
  const html = FILE ? fs.readFileSync(FILE, 'utf8') : await (await fetch(URL0)).text();
  const dom = new JSDOM(html, {
    url: URL0,
    runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      const noop = () => {};
      const ctx = new Proxy({}, { get: (t, k) => k in t ? t[k] :
        k === 'measureText' ? () => ({ width: 10 }) :
        k === 'getImageData' || k === 'createImageData' ? (a, b, c, d) => { const cw = c || a || 1, ch = d || b || 1; return { width: cw, height: ch, data: new Uint8ClampedArray(cw * ch * 4) }; } :
        k === 'createLinearGradient' || k === 'createRadialGradient' ? () => ({ addColorStop: noop }) : noop,
        set: (t, k, v) => (t[k] = v, true) });
      w.HTMLCanvasElement.prototype.getContext = function () { return ctx; };
      w.HTMLCanvasElement.prototype.toDataURL = () => 'data:image/png;base64,';
      w.HTMLCanvasElement.prototype.toBlob = cb => cb(new w.Blob([]));
      w.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
      w.HTMLDialogElement.prototype.show = function () { this.setAttribute('open', ''); };
      w.HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
      // images: fire load asynchronously
      const d = Object.getOwnPropertyDescriptor(w.HTMLImageElement.prototype, 'src');
      Object.defineProperty(w.HTMLImageElement.prototype, 'src', {
        configurable: true,
        get() { return d.get.call(this); },
        set(v) { d.set.call(this, v); setTimeout(() => { if (this.onload) this.onload(new w.Event('load')); }, 5); } });
      Object.defineProperty(w.HTMLImageElement.prototype, 'naturalWidth', { get: () => 192 });
      Object.defineProperty(w.HTMLImageElement.prototype, 'naturalHeight', { get: () => 192 });
      Object.defineProperty(w.HTMLImageElement.prototype, 'complete', { get: () => true });
      w.matchMedia = w.matchMedia || (q => ({ matches: false, media: q, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop }));
      w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
      w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
      try { Object.defineProperty(w.navigator, 'vibrate', { value: () => true }); } catch (e) {}
      try { Object.defineProperty(w.navigator, 'share', { value: async () => {} }); } catch (e) {}
      try { Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: async () => {} } }); } catch (e) {}
      w.scrollTo = noop; w.HTMLElement.prototype.scrollIntoView = noop;
      w.fetch = async (url, opt = {}) => {
        const abs = new URL(url, URL0).href, method = (opt.method || 'GET').toUpperCase();
        if (method !== 'GET') { blocked.push(method + ' ' + abs); return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }); }
        return fetch(abs, { headers: opt.headers });
      };
      w.addEventListener('error', e => errors.push('window error: ' + e.message + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno + ':' + e.colno + (e.error && e.error.stack ? '\n' + e.error.stack.split('\n').slice(0, 4).join('\n') : '')));
      w.addEventListener('unhandledrejection', e => errors.push('unhandledrejection: ' + (e.reason && e.reason.stack || e.reason)));
      const si = w.setInterval; w.setInterval = (f, ms, ...a) => { intervals.push(ms); return si.call(w, f, ms, ...a); };
    },
  });
  const w = dom.window;
  await sleep(8000);
  const started = w.eval('started');
  const src = w.document.getElementById('now').getAttribute('src');
  console.log('started =', started, '| intervals =', JSON.stringify(intervals), '| #now src =', src);
  const tabs = [...w.document.querySelectorAll('nav button')];
  for (const b of tabs) { b.click(); await sleep(1500); }
  for (const c of w.document.querySelectorAll('.chips button, .chip, [data-filter], [onclick^="filter"]')) { try { c.click(); } catch (e) { errors.push('chip click: ' + e.stack); } await sleep(300); }
  await sleep(2000);
  console.log('tabs clicked:', tabs.map(b => b.dataset.tab).join(','), '| blocked non-GET:', blocked.length);
  console.log(errors.length ? 'ERRORS (' + errors.length + '):\n' + [...new Set(errors)].join('\n---\n') : 'no errors');
  const ok = !errors.length && started && src && intervals.includes(1500);
  console.log(ok ? 'OK' : 'FAIL');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
