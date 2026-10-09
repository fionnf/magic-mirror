// Fortuna gallery: runs each edition's GLSL (the same source the wall runs) in one shared WebGL2
// context and copies frames into the visible posts. A post can also listen to the visitor's room.
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

  const glc = document.createElement('canvas');
  const gl = glc.getContext('webgl2', {preserveDrawingBuffer: true, antialias: false});
  if (!gl) { document.documentElement.classList.add('no-gl'); return; }
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);

  function program(src) {
    const sh = (type, s) => { const o = gl.createShader(type); gl.shaderSource(o, s); gl.compileShader(o);
      if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o)); return o; };
    const p = gl.createProgram();
    gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, PRELUDE + src + POST));
    gl.bindAttribLocation(p, 0, 'p'); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }

  // the visitor's room, if they let it listen
  const ears = {on: false, f: {bass: 0, mid: 0, treble: 0, energy: 0, breath: 0, level: 0}};
  async function listen(btn) {
    if (ears.on) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const ac = new AudioContext(), an = ac.createAnalyser(); an.fftSize = 1024;
      ac.createMediaStreamSource(stream).connect(an);
      const bins = new Uint8Array(an.frequencyBinCount); let peak = 0.05;
      ears.on = true; document.querySelectorAll('[data-listen]').forEach(b => { b.textContent = 'Listening to your room'; b.disabled = true; });
      (function tick() {
        an.getByteFrequencyData(bins);
        const band = (a, b) => { let s = 0; for (let i = a; i < b; i++) s += bins[i]; return s / ((b - a) * 255); };
        const raw = {bass: band(1, 8), mid: band(8, 60), treble: band(60, 240)};
        const e = (raw.bass + raw.mid + raw.treble) / 3; peak = Math.max(peak * 0.999, e, 0.05);
        const f = ears.f, k = 0.08;
        for (const key of ['bass', 'mid', 'treble']) f[key] += (Math.min(1, raw[key] / peak) - f[key]) * k;
        f.energy += (Math.min(1, e / peak) - f.energy) * 0.05;
        f.breath += (f.bass * 0.8 - f.breath) * 0.02; f.level = Math.min(0.4, f.energy * 0.4);
        requestAnimationFrame(tick);
      })();
    } catch (e) { btn.textContent = 'The microphone is not available'; }
  }
  document.addEventListener('click', e => { const b = e.target.closest('[data-listen]'); if (b) listen(b); });

  const pieces = [];
  for (const el of document.querySelectorAll('canvas[data-frag]')) {
    const piece = {el, ctx: el.getContext('2d'), visible: false, prog: null, src: null,
                   pal: JSON.parse(el.dataset.palette).map(hex), day: JSON.parse(el.dataset.day || '[]'),
                   w: +el.width, h: +el.height, cols: +el.dataset.cols || 3, rows: +el.dataset.rows || 3};
    pieces.push(piece);
    fetch(el.dataset.frag).then(r => r.text()).then(src => { piece.src = src; }).catch(() => {});
  }
  const io = new IntersectionObserver(es => es.forEach(e => {
    const p = pieces.find(p => p.el === e.target); if (p) p.visible = e.isIntersecting; }), {rootMargin: '200px'});
  pieces.forEach(p => io.observe(p.el));

  const t0 = performance.now() / 1000 - 30;
  function frame() {
    const t = performance.now() / 1000 - t0;
    for (const p of pieces) {
      if (!p.visible || !p.src || p.failed) continue;
      try { if (!p.prog) p.prog = program(p.src); } catch (err) { p.failed = true; p.el.classList.add('failed'); console.warn(err); continue; }
      if (glc.width !== p.w || glc.height !== p.h) { glc.width = p.w; glc.height = p.h; }
      gl.viewport(0, 0, p.w, p.h); gl.useProgram(p.prog);
      const u = n => gl.getUniformLocation(p.prog, n), f = ears.f;
      gl.uniform1f(u('iTime'), t); { const d = new Date(); gl.uniform1f(u('iClock'), d.getHours() + d.getMinutes() / 60 + d.getSeconds() / 3600); } gl.uniform2f(u('iResolution'), p.w, p.h); gl.uniform2f(u('iPanels'), p.cols, p.rows);
      gl.uniform1f(u('iBass'), f.bass); gl.uniform1f(u('iMid'), f.mid); gl.uniform1f(u('iTreble'), f.treble);
      gl.uniform1f(u('iEnergy'), f.energy); gl.uniform1f(u('iLevel'), f.level); gl.uniform1f(u('iBreath'), f.breath);
      gl.uniform1f(u('iTension'), f.energy * 0.5); gl.uniform1f(u('iBright'), f.treble);
      gl.uniform3fv(u('iColA'), p.pal[0]); gl.uniform3fv(u('iColB'), p.pal[1]); gl.uniform3fv(u('iColC'), p.pal[2]);
      const day = new Float32Array(24); p.day.forEach((v, i) => { if (i < 24) day[i] = v; });
      const ud = u('iDay[0]') || u('iDay'); if (ud) gl.uniform1fv(ud, day);
      gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      p.ctx.drawImage(glc, 0, 0);
    }
    requestAnimationFrame(frame);
  }
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) requestAnimationFrame(frame);
  else document.documentElement.classList.add('still');
})();
