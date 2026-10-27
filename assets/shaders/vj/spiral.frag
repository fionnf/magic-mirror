// Spiral (music): GPU port of shapes.SpiralMorph. 420 dots on a phyllotaxis spiral whose twist
// (the golden angle, wobbling a little) slowly morphs and turns; outer dots grow and shrink in a
// travelling wave. Gold dot colours -> luminance -> scene palette, as the CPU path does.
// The bass breathes the spiral outward and swells the dots.
//
// Cheap lookup: dot i sits at (index i, turn i*alpha) on a 2D lattice. Near the pixel that lattice
// is spanned by two short vectors built from the continued-fraction convergents of alpha (the
// spiral's arm counts), so the pixel solves a 2x2 system for its lattice cell and checks the 4 dots
// at the cell's corners - the same small fixed work for every pixel, no data-dependent loops.
vec3 pal(float v){
  float i = clamp(v, 0.0, 1.0) * 255.0;
  if (i < 25.0) return mix(iColA * 0.55, iColA, i / 25.0);
  if (i < 140.0) return mix(iColA, iColB, (i - 25.0) / 115.0);
  return mix(iColB, iColC, (i - 140.0) / 105.0);
}
// luminance of the CPU piece's gold ramp
float goldLum(float v){
  v *= 3.0;
  return 0.047 + 0.342 * clamp(v, 0.0, 1.0) + 0.336 * clamp(v - 1.0, 0.0, 1.0) + 0.224 * clamp(v - 2.0, 0.0, 1.0);
}
vec2 cmul(vec2 a, vec2 b){ return vec2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x); }
vec2 cis(float a){ return vec2(cos(a), sin(a)); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 R = iResolution;
  vec2 p = vec2(fc.x - 0.5, R.y - fc.y - 0.5);            // CPU pixel coords, y down
  float t = iTime;
  float n = 420.0;
  float ang = 2.399963 + 0.06 * sin(t * 0.07);
  float alpha = ang / 6.2831853;
  float rot = t * 0.05;
  float swell = 1.0 + 0.7 * iBass + 0.08 * iEnergy;
  float rmax = min(R.x, R.y) * 0.47 * (1.0 + 0.07 * iBass);
  vec2 q = p - 0.5 * R;
  float r = max(length(q), 0.5);
  float it = n * (r / rmax) * (r / rmax);                  // fractional dot index at this radius
  float phi = (atan(q.y, q.x) - rot) / 6.2831853;          // pixel angle in turns
  // local metric: px per index step (radial) and px per turn (tangential)
  vec2 sc = vec2(rmax * 0.5 * inversesqrt(n * max(it, 0.25)), 6.2831853 * r);
  // continued fraction of alpha -> consecutive convergents (q, e = q alpha - p); keep the best-shaped pair
  float x = alpha;
  vec2 b1 = vec2(1.0, alpha), b2 = vec2(0.0, 1.0);
  float best = 1e9;
  vec2 prev = vec2(0.0, -1.0);                              // q_{-1} = 0, e = -1
  vec2 cur = vec2(1.0, alpha);                              // q_0 = 1, p_0 = 0
  float qa = 1.0, pa = 0.0, qb = 0.0, pb = 1.0;
  for (int k = 0; k < 8; k++) {
    vec2 m1 = prev * sc, m2 = cur * sc;
    float s = max(dot(m1, m1), dot(m2, m2));
    if (s < best) { best = s; b1 = prev; b2 = cur; }
    x = 1.0 / max(x - floor(x), 1e-4);
    float a = floor(x);
    float qn = a * qa + qb, pn = a * pa + pb;
    qb = qa; pb = pa; qa = qn; pa = pn;
    prev = cur;
    cur = vec2(qn, qn * alpha - pn);
  }
  // one Lagrange reduction step in the metric, short vector first
  if (dot(b2 * sc, b2 * sc) < dot(b1 * sc, b1 * sc)) { vec2 tmp = b1; b1 = b2; b2 = tmp; }
  b2 -= floor(dot(b1 * sc, b2 * sc) / dot(b1 * sc, b1 * sc) + 0.5) * b1;
  // lattice coordinates of the pixel: (it, phi) = c1 b1 + c2 b2 (any whole-turn shift is a lattice vector)
  float det = b1.x * b2.y - b2.x * b1.y;
  vec2 c = vec2(b2.y * it - b2.x * phi, b1.x * phi - b1.y * it) / det;
  vec2 c0 = floor(c);                                      // the lattice cell holding the pixel
  float i0 = c0.x * b1.x + c0.y * b2.x;                    // dot index at the block corner
  vec2 e0 = cis(i0 * ang + rot), e1 = cis(b1.x * ang), e2 = cis(b2.x * ang);
  vec2 w0 = cis(i0 * 0.05 - t * 0.6), w1 = cis(b1.x * 0.05), w2 = cis(b2.x * 0.05);
  float core = 0.0, glow = 0.0;
  for (int j = 0; j < 2; j++) {
    vec2 e = e0, w = w0;
    float i = i0 + float(j) * b2.x;
    for (int k = 0; k < 2; k++) {
      float f = i / n;
      float ok = step(1.0, i) * step(i, n - 1.0);          // dot 0 is added below
      vec2 cpos = e * (rmax * sqrt(max(f, 0.0)));
      float s = (0.7 + 1.6 * f * (0.6 + 0.4 * w.y)) * swell;
      float d = length(q - cpos);
      float lum = goldLum(fract(f + t * 0.02)) * ok;
      float cov = clamp(max(s, 1.0) + 0.4 - d, 0.0, 1.0);
      float h = max(d - 0.5 * s, 0.0);
      float g = clamp(1.0 - h * h / 14.0, 0.0, 1.0);        // ~exp(-h^2 / 2.88), cut at 3.7 px
      g = 1.25 * clamp(0.43 * s - 0.15, 0.0, 1.0) * g * g * g * g;   // the blurred disc's peak, ~1 - exp(-s^2 / 2.88)
      core = max(core, cov * lum);
      glow += g * lum;
      i += b1.x; e = cmul(e, e1); w = cmul(w, w1);
    }
    e0 = cmul(e0, e2); w0 = cmul(w0, w2);
  }
  {                                                        // dot 0 sits on the centre, where the lattice view breaks down
    float d = length(q), s = 0.7 * swell, lum = goldLum(fract(t * 0.02));
    float h = max(d - 0.5 * s, 0.0), g = clamp(1.0 - h * h / 14.0, 0.0, 1.0);
    core = max(core, clamp(1.4 - d, 0.0, 1.0) * lum);
    glow += 1.25 * clamp(0.43 * s - 0.15, 0.0, 1.0) * g * g * g * g * lum;
  }
  float L = min(0.85 * core + 1.1 * glow, 1.0);
  float field = clamp(pow(L, 0.85) * 1.15, 0.0, 1.0);
  o = vec4(pal(field), 1.0);
}
