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
out vec4 _out;
`;
  const POST = `
void main(){ vec4 c = vec4(0.0); mainImage(c, gl_FragCoord.xy); _out = vec4(clamp(c.rgb, 0.0, 1.0), 1.0); }`;
  const VS = `#version 300 es
in vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }`;
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
  const SCALARS = ['iBass', 'iMid', 'iTreble', 'iEnergy', 'iLevel', 'iBreath', 'iTension', 'iKey', 'iBright', 'iSong', 'iBeatPhase'];

  const F = window.Fortuna = {pieces: [], hex};
  const glc = document.createElement('canvas');
  const gl = glc.getContext('webgl2', {preserveDrawingBuffer: true, antialias: false});
  if (!gl) { document.documentElement.classList.add('no-gl'); F.add = () => null; return; }
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
    for (const n of SCALARS.concat(['iTime', 'iClock', 'iResolution', 'iPanels', 'iColA', 'iColB', 'iColC']))
      loc[n] = gl.getUniformLocation(p, n);
    loc.iDay = gl.getUniformLocation(p, 'iDay[0]') || gl.getUniformLocation(p, 'iDay');
    return {p, loc};
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
     over may hold any uniform name (iBass..), plus 'clock' (hours) and 'pal' / 'day'. */
  F.add = function (el, o = {}) {
    const piece = Object.assign({el, ctx: el.getContext('2d'), visible: false, prog: null, src: null, over: {},
      speed: 1, time: 30 + Math.random() * 60, taps: new Set(), w: 192, h: 192}, o);
    piece.cols = piece.cols || Math.max(1, Math.round(piece.w / 64)); piece.rows = piece.rows || Math.max(1, Math.round(piece.h / 64));
    F.pieces.push(piece);
    if (o.src == null && o.frag) fetch(o.frag).then(r => r.text()).then(src => { piece.src = src; }).catch(() => {});
    if (o.always) piece.visible = true; else io.observe(el);
    return piece;
  };
  F.setSource = (p, src) => { p.src = src; p.prog = null; p.failed = false; p.el.classList.remove('failed'); };
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
    const pal = (o.pal || p.pal).map(c => typeof c === 'string' ? hex(c) : c);
    gl.uniform3fv(L.iColA, pal[0]); gl.uniform3fv(L.iColB, pal[1]); gl.uniform3fv(L.iColC, pal[2]);
    const day = new Float32Array(24); (o.day || p.day || []).forEach((v, i) => { if (i < 24) day[i] = v; });
    if (L.iDay) gl.uniform1fv(L.iDay, day);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (p.draw) p.draw(glc); else p.ctx.drawImage(glc, 0, 0);
    p.taps.forEach(fn => fn(glc, p));
  }

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
    await new Promise(res => { p.taps.add(function once() { p.taps.delete(once); F.card(c.getContext('2d'), p, 1080, 1350, meta); res(); });
                               if (F.still) render(p, 0); });
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
  for (const el of document.querySelectorAll('canvas[data-frag]'))
    el.piece = F.add(el, {frag: el.dataset.frag, pal: JSON.parse(el.dataset.palette), day: JSON.parse(el.dataset.day || '[]'),
                          w: +el.width, h: +el.height, cols: +el.dataset.cols || 0, rows: +el.dataset.rows || 0});

  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    for (const p of F.pieces) {
      if (!(p.visible || p.taps.size) || !p.src || p.failed) continue;
      try { render(p, dt); } catch (err) { p.failed = true; p.el.classList.add('failed'); console.warn(err); if (p.onfail) p.onfail(err); }
    }
    requestAnimationFrame(frame);
  }
  F.still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!F.still) requestAnimationFrame(frame);
  else document.documentElement.classList.add('still');
})();
