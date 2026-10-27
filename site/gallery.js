// Fortuna gallery: runs each edition's GLSL (the same source the wall runs) in one shared WebGL2
// context and copies frames into the visible pieces. A piece can listen to the visitor's room, be
// remixed (uniform overrides), drawn as real LED dots at any size, and recorded as a postcard.
(() => {
  const PRELUDE = `#version 300 es
precision highp float;
uniform float iTime; uniform vec2 iResolution;
uniform float iBass; uniform float iMid; uniform float iTreble; uniform float iEnergy; uniform float iLevel;
uniform vec3 iColA; uniform vec3 iColB; uniform vec3 iColC;
uniform float iBreath; uniform float iTension; uniform float iKey; uniform float iBright; uniform float iSong;
uniform float iBeatPhase; uniform float iDay[24]; uniform vec2 iPanels; uniform float iClock;
uniform vec4 iEvolve; uniform vec4 iFrame;
out vec4 _out;
`;
  const POST = `
void main(){
  vec2 m = 0.5 * iResolution, q = gl_FragCoord.xy - m;
  float cs = cos(iFrame.y), sn = sin(iFrame.y);
  q = mat2(cs, -sn, sn, cs) * q / max(iFrame.x, 0.3);
  vec4 c = vec4(0.0); mainImage(c, m + q - iFrame.zw * iResolution); _out = vec4(clamp(c.rgb, 0.0, 1.0), 1.0); }`;
  const VS = `#version 300 es
in vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }`;
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
  const SCALARS = ['iBass', 'iMid', 'iTreble', 'iEnergy', 'iLevel', 'iBreath', 'iTension', 'iKey', 'iBright', 'iSong', 'iBeatPhase'];

  /* Slow evolution, the same as display/shaders.py evolution(): over tens of minutes the palette drifts
     in hue and saturation, the frame grows, shrinks, turns and wanders, and iEvolve carries four slow
     drifts the shader can use for its form. Seeded by the source, timed by the wall clock, so the
     website shows a piece as the wall does at the same moment. */
  const CRC = new Uint32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc32 = str => { let c = 0xFFFFFFFF; for (const b of new TextEncoder().encode(str)) c = CRC[(c ^ b) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  const FIELD = /(fc|fragCoord)(\.xy)?\s*\/\s*iResolution/;
  function evolution(seed, secs, kind) {
    seed = seed / 2 ** 32 * 1000; const m = secs / 60, TAU = 2 * Math.PI;
    const d = (k, period) => { const ph = (seed * (k + 1) * 0.618034) % 1 * TAU;
      return 0.62 * Math.sin(TAU * m / period + ph) + 0.38 * Math.sin(TAU * m / (period * 1.618) + 1.7 * ph); };
    const evolve = [d(0, 11), d(1, 17), d(2, 26), d(3, 41)];
    let frame;
    if (kind === 'fixed') frame = [1, 0, 0, 0];
    else if (kind === 'field') { const sc = 1 + 0.09 * (d(4, 23) + 1), room = 0.45 * (1 - 1 / sc); frame = [sc, 0, room * d(6, 19), room * d(7, 29)]; }
    else frame = [2 ** (0.24 * d(4, 23)), 0.2 * d(5, 37), 0.08 * d(6, 19), 0.1 * d(7, 29)];
    return {evolve, frame, shift: [34 * d(8, 31), 14 * d(10, 47), 0.2 * d(9, 21)]};
  }
  function rgb2hls(r, g, b) {                       // as Python's colorsys
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
    if (mx === mn) return [0, l, 0];
    const s = l <= 0.5 ? (mx - mn) / (mx + mn) : (mx - mn) / (2 - mx - mn);
    const rc = (mx - r) / (mx - mn), gc = (mx - g) / (mx - mn), bc = (mx - b) / (mx - mn);
    const h = r === mx ? bc - gc : g === mx ? 2 + rc - bc : 4 + gc - rc;
    return [((h / 6) % 1 + 1) % 1, l, s];
  }
  function hls2rgb(h, l, s) {
    if (s === 0) return [l, l, l];
    const m2 = l <= 0.5 ? l * (1 + s) : l + s - l * s, m1 = 2 * l - m2;
    const v = hue => { hue = ((hue % 1) + 1) % 1;
      return hue < 1 / 6 ? m1 + (m2 - m1) * hue * 6 : hue < 0.5 ? m2 : hue < 2 / 3 ? m1 + (m2 - m1) * (2 / 3 - hue) * 6 : m1; };
    return [v(h + 1 / 3), v(h), v(h - 1 / 3)];
  }
  const shiftPalette = (pal, [hue, hue2, sat]) => pal.map((c, i) => {
    const [h, l, s] = rgb2hls(...c.map(v => Math.min(1, Math.max(0, v))));
    return hls2rgb((h + (hue + (i ? hue2 : 0)) / 360 + 1) % 1, l, Math.min(1, s * (1 + sat)));
  });

  const F = window.Fortuna = {pieces: [], hex, evolution};
  /* Draw a native frame as the wall really looks: one round diode per pixel, a little black between
     them, light blooming into the gaps, and the seams where the 64 x 64 panels meet. */
  const masks = new Map();
  function mask(cell) {
    if (!masks.has(cell)) {
      const t = document.createElement('canvas'); t.width = t.height = cell;
      const x = t.getContext('2d'); x.fillStyle = '#000'; x.fillRect(0, 0, cell, cell);
      x.globalCompositeOperation = 'destination-out';
      const g = x.createRadialGradient(cell / 2, cell / 2, 0, cell / 2, cell / 2, cell * 0.5);
      g.addColorStop(0, '#000'); g.addColorStop(0.62, '#000'); g.addColorStop(0.9, 'rgba(0,0,0,0)');
      x.fillStyle = g; x.fillRect(0, 0, cell, cell);
      masks.set(cell, x.createPattern(t, 'repeat'));
    }
    return masks.get(cell);
  }
  F.ledify = function (ctx, src, sw, sh, box, opt = {}) {
    const cell = Math.max(1, Math.floor(Math.min(box.w / sw, box.h / sh)));
    const w = sw * cell, h = sh * cell, x = Math.round(box.x + (box.w - w) / 2), y = Math.round(box.y + (box.h - h) / 2);
    ctx.save(); ctx.imageSmoothingEnabled = false;
    ctx.drawImage(src, 0, 0, sw, sh, x, y, w, h);
    if (cell >= 3) {
      ctx.translate(x, y); ctx.fillStyle = mask(cell); ctx.fillRect(0, 0, w, h);
      if (opt.seams !== false) {
        ctx.fillStyle = 'rgba(0,0,0,.6)';
        for (let c = 64; c < sw; c += 64) ctx.fillRect(c * cell - 1, 0, 2, h);
        for (let r = 64; r < sh; r += 64) ctx.fillRect(0, r * cell - 1, w, 2);
      }
      if (opt.bloom !== false && 'filter' in ctx) {
        ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = opt.bloom || 0.35;
        ctx.filter = `blur(${Math.max(2, cell * 1.4)}px)`; ctx.imageSmoothingEnabled = true;
        ctx.drawImage(src, 0, 0, sw, sh, 0, 0, w, h);
      }
    }
    ctx.restore();
    return {x, y, w, h, cell};
  };

  const glc = document.createElement('canvas');
  const gl = glc.getContext('webgl2', {preserveDrawingBuffer: true, antialias: false});
  if (!gl) { document.documentElement.classList.add('no-gl'); F.add = () => null; F.gl = false; return; }
  F.gl = true;
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);

  function program(src) {
    const sh = (type, s) => { const o = gl.createShader(type); gl.shaderSource(o, s); gl.compileShader(o);
      if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o)); return o; };
    const p = gl.createProgram();
    gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, PRELUDE + src + POST));
    gl.bindAttribLocation(p, 0, 'p'); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    const loc = {};
    for (const n of SCALARS.concat(['iTime', 'iClock', 'iResolution', 'iPanels', 'iColA', 'iColB', 'iColC', 'iEvolve', 'iFrame']))
      loc[n] = gl.getUniformLocation(p, n);
    loc.iDay = gl.getUniformLocation(p, 'iDay[0]') || gl.getUniformLocation(p, 'iDay');
    return {p, loc, seed: crc32(src), kind: /iPanels/.test(src) ? 'fixed' : FIELD.test(src) ? 'field' : 'free'};
  }

  // the visitor's room, if they let it listen
  const ears = F.ears = {on: false, f: {iBass: 0, iMid: 0, iTreble: 0, iEnergy: 0, iBreath: 0, iLevel: 0, iTension: 0, iBright: 0}};
  F.listen = async function (btn) {
    if (ears.on) return true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const ac = new AudioContext(), an = ac.createAnalyser(); an.fftSize = 1024;
      ac.createMediaStreamSource(stream).connect(an);
      const bins = new Uint8Array(an.frequencyBinCount); let peak = 0.05;
      ears.on = true; document.querySelectorAll('[data-listen]').forEach(b => { b.textContent = 'Listening to your room'; b.disabled = true; });
      (function tick() {
        an.getByteFrequencyData(bins);
        const band = (a, b) => { let s = 0; for (let i = a; i < b; i++) s += bins[i]; return s / ((b - a) * 255); };
        const raw = {iBass: band(1, 8), iMid: band(8, 60), iTreble: band(60, 240)};
        const e = (raw.iBass + raw.iMid + raw.iTreble) / 3; peak = Math.max(peak * 0.999, e, 0.05);
        const f = ears.f, k = 0.08;
        for (const key in raw) f[key] += (Math.min(1, raw[key] / peak) - f[key]) * k;
        f.iEnergy += (Math.min(1, e / peak) - f.iEnergy) * 0.05;
        f.iBreath += (f.iBass * 0.8 - f.iBreath) * 0.02; f.iLevel = Math.min(0.4, f.iEnergy * 0.4);
        f.iTension = f.iEnergy * 0.5; f.iBright = f.iTreble;
        requestAnimationFrame(tick);
      })();
      return true;
    } catch (e) { if (btn) btn.textContent = 'The microphone is not available'; return false; }
  };
  document.addEventListener('click', e => { const b = e.target.closest('[data-listen]'); if (b) F.listen(b); });

  /* A piece: {el, w, h, pal, day, over (uniform overrides), speed, draw(glc) | null}.
     over may hold any uniform name (iBass..), plus 'clock' (hours), 'pal' / 'day' and 'evolve'
     (false = as written, a number = that moment in seconds; default the wall clock). */
  F.add = function (el, o = {}) {
    const piece = Object.assign({el, ctx: el.getContext('2d'), visible: false, prog: null, src: null, over: {},
      speed: 1, time: 30 + Math.random() * 60, taps: new Set(), w: 192, h: 192}, o);
    piece.cols = piece.cols || Math.max(1, Math.round(piece.w / 64)); piece.rows = piece.rows || Math.max(1, Math.round(piece.h / 64));
    F.pieces.push(piece);
    if (o.src == null && o.frag) fetch(o.frag).then(r => r.text()).then(src => { piece.src = src; }).catch(() => {});
    if (o.always) piece.visible = true; else io.observe(el);
    return piece;
  };
  F.setSource = (p, src) => { p.src = src; p.prog = null; p.failed = false; p.drawn = false; p.el.classList.remove('failed'); };
  F.remove = p => {                         // stop rendering a piece for good (the app swaps pieces often)
    if (!p) return; const k = F.pieces.indexOf(p); if (k >= 0) F.pieces.splice(k, 1);
    try { io.unobserve(p.el); } catch (e) {} p.taps.clear();
  };
  const io = new IntersectionObserver(es => es.forEach(e => {
    const p = F.pieces.find(p => p.el === e.target); if (p) p.visible = e.isIntersecting; }), {rootMargin: '200px'});

  function render(p, dt) {
    if (!p.prog) p.prog = program(p.src);
    p.time += dt * p.speed;
    if (glc.width !== p.w || glc.height !== p.h) { glc.width = p.w; glc.height = p.h; }
    gl.viewport(0, 0, p.w, p.h); gl.useProgram(p.prog.p);
    const L = p.prog.loc, o = p.over, f = ears.f;
    const d = new Date(), clock = o.clock != null ? o.clock : d.getHours() + d.getMinutes() / 60 + d.getSeconds() / 3600;
    gl.uniform1f(L.iTime, p.time); gl.uniform1f(L.iClock, clock);
    gl.uniform2f(L.iResolution, p.w, p.h); gl.uniform2f(L.iPanels, p.cols, p.rows);
    for (const n of SCALARS) gl.uniform1f(L[n], o[n] != null ? o[n] : n === 'iBeatPhase' ? (p.time * 2) % 1 : (f[n] || 0));
    let pal = (o.pal || p.pal).map(c => typeof c === 'string' ? hex(c) : c);
    let ev = {evolve: [0, 0, 0, 0], frame: [1, 0, 0, 0]};
    if (o.evolve !== false) {
      ev = evolution(p.prog.seed, typeof o.evolve === 'number' ? o.evolve : Date.now() / 1000, p.prog.kind);
      pal = shiftPalette(pal, ev.shift);
    }
    gl.uniform4fv(L.iEvolve, ev.evolve); gl.uniform4fv(L.iFrame, ev.frame);
    gl.uniform3fv(L.iColA, pal[0]); gl.uniform3fv(L.iColB, pal[1]); gl.uniform3fv(L.iColC, pal[2]);
    const day = new Float32Array(24); (o.day || p.day || []).forEach((v, i) => { if (i < 24) day[i] = v; });
    if (L.iDay) gl.uniform1fv(L.iDay, day);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (p.draw) p.draw(glc); else p.ctx.drawImage(glc, 0, 0);
    p.taps.forEach(fn => fn(glc, p));
  }

  /* Postcards: a still (PNG) or a few seconds of the living piece (video), as LED dots with a label. */
  F.card = function (ctx, p, W, H, meta) {
    const pad = Math.round(W * 0.07), label = meta ? W * 0.17 : 0;
    ctx.fillStyle = '#121014'; ctx.fillRect(0, 0, W, H);
    const cell = Math.max(1, Math.floor(Math.min((W - 2 * pad) / p.w, (H - 2 * pad - label) / p.h)));
    const top = Math.round((H - p.h * cell - label) / 2);       // the art and its label, centred together
    const art = F.ledify(ctx, glc, p.w, p.h, {x: pad, y: top, w: W - 2 * pad, h: p.h * cell});
    if (!meta) return;
    ctx.fillStyle = '#f1ebf3'; ctx.textBaseline = 'alphabetic';
    ctx.font = `italic 400 ${Math.round(W * 0.062)}px "Instrument Serif", Georgia, serif`;
    const ty = art.y + art.h + W * 0.1;
    ctx.fillText(meta.name, art.x, ty, art.w);
    ctx.fillStyle = '#a39aa8'; ctx.font = `400 ${Math.round(W * 0.026)}px "Instrument Sans", system-ui, sans-serif`;
    ctx.fillText(meta.line, art.x, ty + W * 0.05, art.w);
  };
  async function share(blob, name) {
    const file = new File([blob], name, {type: blob.type});
    if (navigator.canShare && navigator.canShare({files: [file]}) && matchMedia('(pointer: coarse)').matches) {
      try { await navigator.share({files: [file]}); return; } catch (e) { if (e.name === 'AbortError') return; }
    }
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  F.postcard = async function (p, meta) {
    await document.fonts?.ready;
    const c = document.createElement('canvas'); c.width = 1080; c.height = 1350;
    await new Promise((res, rej) => {
      if (p.failed || !p.src) return rej(new Error('This piece cannot draw here.'));
      const once = () => { clearTimeout(t); p.taps.delete(once); F.card(c.getContext('2d'), p, 1080, 1350, meta); res(); };
      const t = setTimeout(() => { p.taps.delete(once); rej(new Error('This piece did not draw in time.')); }, 6000);
      p.taps.add(once);
    });
    const blob = await new Promise(res => c.toBlob(res, 'image/png'));
    await share(blob, `fortuna-${meta.slug}.png`);
  };
  F.canRecord = !!(window.MediaRecorder && HTMLCanvasElement.prototype.captureStream);
  F.record = async function (p, meta, seconds = 8, onTick) {
    await document.fonts?.ready;
    const c = document.createElement('canvas'); c.width = 1080; c.height = 1350;
    const x = c.getContext('2d');
    const type = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'].find(t => MediaRecorder.isTypeSupported(t));
    const rec = new MediaRecorder(c.captureStream(30), {mimeType: type, videoBitsPerSecond: 8e6}), parts = [];
    rec.ondataavailable = e => e.data.size && parts.push(e.data);
    const t0 = performance.now(), tap = () => {
      F.card(x, p, 1080, 1350, meta);
      if (onTick) onTick(Math.min(1, (performance.now() - t0) / 1000 / seconds));
    };
    p.taps.add(tap); rec.start(250);
    await new Promise(res => setTimeout(res, seconds * 1000));
    p.taps.delete(tap);
    await new Promise(res => { rec.onstop = res; rec.stop(); });
    await share(new Blob(parts, {type: type.split(';')[0]}), `fortuna-${meta.slug}.${type.includes('mp4') ? 'mp4' : 'webm'}`);
  };

  // the feed's pieces
  const sources = {};                      // one fetch per shader, shared by the piece and its day strip
  for (const el of document.querySelectorAll('canvas[data-frag]')) {
    const o = {pal: JSON.parse(el.dataset.palette), day: JSON.parse(el.dataset.day || '[]'), src: null,
               w: +el.width, h: +el.height, cols: +el.dataset.cols || 0, rows: +el.dataset.rows || 0};
    if (el.dataset.clock != null) { o.over = {clock: +el.dataset.clock}; o.speed = 0.15; }   // a held hour, barely moving
    el.piece = F.add(el, o);
    (sources[el.dataset.frag] = sources[el.dataset.frag] || fetch(el.dataset.frag).then(r => r.text()))
      .then(src => { el.piece.src = src; }).catch(() => {});
  }

  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    for (const p of F.pieces.slice()) {
      if (!(p.visible || p.taps.size) || !p.src || p.failed) continue;
      if (F.still && p.drawn && !p.taps.size && !p.dirty) continue;   // reduced motion: one still frame each
      try { render(p, F.still ? 0 : dt); p.drawn = true; p.dirty = false; }
      catch (err) { p.failed = true; p.el.classList.add('failed'); console.warn(err); if (p.onfail) p.onfail(err); }
    }
    requestAnimationFrame(frame);
  }
  F.still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  requestAnimationFrame(frame);
  if (F.still) document.documentElement.classList.add('still');
})();
