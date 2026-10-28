// Bloom: a flower drawn in light that lives its whole life once an hour, from a seed on the ground back to a seed.
// On the hour a single seed rests on a faint line of ground, glowing softly. At :04 it puts down roots,
// and from :05 a stem rises out of it with its tip bent over in a hook, uncurling as it climbs. Two leaves
// unfold from it at :09 and :11. At :14 a bud swells at the top, and from :21 the flower opens one petal
// at a time, outer petals first, until it stands full and open at :32. At :35 the petals let go one by one
// and fall, fading as they go, while a round seed head grows out of the heart (:37). At :44 the seeds lift
// off on the air one by one, turn their parachutes to the sky and drift away up and to the right; from :50
// the bare stem draws itself back down into the ground, folding its leaves as it goes. Meanwhile one seed
// comes back from the upper left, swaying down to land on the spot at :58, and folds its parachute away -
// the seed again at the top of the hour. Everything is line and point light: bright cores in the light
// colour with a halo of the mid colour, faint fills in the petals and leaves, a pulse of sap that runs up
// the stem, and a pool of light on the ground under the plant that grows while it flowers.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
vec2 rotv(vec2 v, float a){ float c = cos(a), s = sin(a); return vec2(c * v.x - s * v.y, s * v.x + c * v.y); }
vec2 dirv(float a){ return vec2(cos(a), sin(a)); }
float segd(vec2 p, vec2 a, vec2 b, out float h){
  vec2 pa = p - a, ba = b - a;
  h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-8), 0.0, 1.0);
  return length(pa - ba * h);
}
float tear(vec2 p, float r1, float r2, float h){      // a round end r1 at the origin, r2 at height h
  p.x = abs(p.x);
  float b = (r1 - r2) / h, a = sqrt(1.0 - b * b), k = dot(p, vec2(-b, a));
  if (k < 0.0) return length(p) - r1;
  if (k > a * h) return length(p - vec2(0.0, h)) - r2;
  return dot(p, vec2(a, b)) - r1;
}
float vesica(vec2 p, float h, float w){               // a leaf: tips at (0, +-h), half-width w
  float r = (h * h + w * w) / (2.0 * w), d = r - w;
  p = abs(p);
  return ((p.y - h) * d > p.x * h) ? length(p - vec2(0.0, h)) : length(p - vec2(-d, 0.0)) - r;
}

vec3 col;
void glow(float d, float w, float a, vec3 tint){      // a line of light: bright core, soft halo
  col += a * (tint * smoothstep(w, w * 0.15, d) + iColB * 0.4 * exp(-max(d, 0.0) / 0.016));
}

// one seed: achene at A pointing along b, stalk to the parachute at A + L along b, parachute opened pap
void seed(vec2 p, vec2 A, float b, float L, float pap, float ach, float vis){
  if (vis <= 0.0 || length(p - A) > L + 0.08) return;
  vec2 q = rotv(p - A, 1.5708 - b);                    // local: the seed points up +y
  float as = max(ach, 0.001);
  float da = tear(q / as, 0.0105, 0.0035, 0.026) * as;
  col += vis * (iColC * smoothstep(0.004, -0.001, da) + iColB * 0.3 * exp(-max(da, 0.0) / 0.01));
  float h, top = 0.026 * as;
  if (L > top + 0.002) glow(segd(q, vec2(0.0, top), vec2(0.0, L), h), 0.0032, vis * 0.9, mix(iColB, iColC, 0.6));
  vec2 c = q - vec2(0.0, L);
  float dotA = smoothstep(0.03, 0.06, L);
  col += vis * dotA * (iColC * smoothstep(0.009, 0.004, length(c)) * (0.8 + 0.3 * iBright));
  if (pap > 0.01) {                                    // the parachute: a fan of fine rays
    float r = length(c), a = atan(c.x, c.y), span = 1.25 * pap, st = span / 3.0;
    float k = clamp(floor(a / st + 0.5), -3.0, 3.0);
    float dr = length(c - r * vec2(sin(k * st), cos(k * st)));
    float len = 0.042 * pap;
    float ray = smoothstep(0.003, 0.0006, dr) * smoothstep(len + 0.004, len - 0.002, r);
    float tip = smoothstep(0.0075, 0.002, length(c - len * vec2(sin(k * st), cos(k * st))));
    col += vis * (mix(iColB, iColC, 0.7) * ray * 0.95 + iColC * tip * 0.9);
  }
}

void mainImage(out vec4 o, in vec2 fc){
  vec2 p = (fc - 0.5 * iResolution) / iResolution.y * 1.3333;
  float y0 = -0.585;                                   // the ground line
  float gy = p.y;
  p.y = y0 + (p.y - y0) / 1.15; p.x /= 1.15;   // the plant drawn a little larger about its root
  float m = fract(iClock) * 60.0;                      // minutes into the hour
  float t = iTime;
  col = iColA * 0.12 * smoothstep(0.2, -0.7, p.y);

  // --- the timeline
  float g = smoothstep(5.0, 16.0, m) * (1.0 - smoothstep(50.5, 57.0, m));     // how much stem is drawn
  float roots = smoothstep(3.5, 10.0, m) * (1.0 - smoothstep(53.0, 57.5, m));
  float bud = smoothstep(14.0, 21.0, m);
  float bloomL = smoothstep(22.0, 32.0, m) * (1.0 - smoothstep(36.0, 42.0, m));
  float recep = smoothstep(14.0, 18.0, m) * (1.0 - smoothstep(49.5, 51.5, m));
  float age = smoothstep(40.0, 49.0, m);

  // --- the ground: a faint line with a pool of light under the plant
  float gx = exp(-p.x * p.x / 0.035);
  float gl = smoothstep(0.0045, 0.0008, abs(gy - y0)) * (0.3 + 0.55 * gx) * (0.85 + 0.25 * bloomL);
  col += mix(iColB, iColC, 0.35 * gx) * gl;
  col += iColB * 0.16 * (0.5 + bloomL) * exp(-p.x * p.x / 0.02) * exp(-max(p.y - y0, 0.0) / 0.05) * step(y0, p.y);

  // --- the resting seed (the hour's start), spent while the plant grows from it
  vec2 home = vec2(0.0, y0 + 0.0199);
  float breath = 0.5 + 0.5 * sin(t * 0.6);
  if (m < 18.0) {
    float wake = smoothstep(2.0, 5.0, m) * (1.0 - smoothstep(9.0, 17.0, m));
    col += iColB * (0.1 + 0.05 * breath + 0.18 * wake) * exp(-length(p - home) / 0.03);
    seed(p, home, 1.5708, 0.04, 0.0, 1.9, 1.0 - smoothstep(9.0, 17.0, m));
  }

  // --- roots, under the ground line
  if (roots > 0.0 && p.y < y0 + 0.01) {
    for (int i = 0; i < 3; i++) {
      float fi = float(i) - 1.0, h;
      vec2 a = vec2(fi * 0.006, y0);
      vec2 b = a + roots * 0.028 * vec2(fi * 0.6, -1.0);
      vec2 c = b + roots * (0.022 - 0.005 * abs(fi)) * vec2(fi * 1.1 + 0.3, -0.7);
      float d = min(segd(p, a, b, h), segd(p, b, c, h));
      glow(d, 0.0028, 0.7 * roots, iColB);
    }
  }

  // --- the stem: drawn from the seed, its tip hooked over while it grows
  vec2 P = vec2(0.0, y0 + 0.012), T = P, N1 = P, N2 = P;
  float th = 1.5708, tth = th, n1t = th, n2t = th;
  if (g > 0.001) {
    float lean = 0.28 + 0.06 * iEvolve.x;
    float sl = g * 0.66 / 24.0;
    float hook = 3.2 * (1.0 - smoothstep(0.45, 1.0, g));
    float sway = 0.035 * sin(t * 0.37) + 0.02 * sin(t * 0.61 + 1.0);
    float dmin = 1e3, sAt = 0.0;
    for (int i = 0; i < 24; i++) {
      float s = (float(i) + 0.5) / 24.0 * g;
      float w = clamp((s - (g - 0.28)) / 0.28, 0.0, 1.0);
      th = 1.5708 - (lean * cos(s * 3.4) - 0.05) + sway * s + hook * w * w;
      vec2 Q = P + sl * dirv(th);
      float h, dd = segd(p, P, Q, h);
      if (dd < dmin) { dmin = dd; sAt = (float(i) + h) / 24.0 * g; }
      float f1 = 0.28 / g * 24.0 - float(i), f2 = 0.47 / g * 24.0 - float(i);
      if (f1 >= 0.0 && f1 < 1.0) { N1 = mix(P, Q, f1); n1t = th; }
      if (f2 >= 0.0 && f2 < 1.0) { N2 = mix(P, Q, f2); n2t = th; }
      P = Q;
    }
    T = P; tth = th;
    float sap = 1.0 + 0.5 * exp(-pow((sAt / max(g, 0.01) - fract(t * 0.045)) * 7.0, 2.0));
    glow(dmin, 0.0065 - 0.0025 * sAt, 0.95 * sap, mix(iColB, iColC, 0.3 + 0.45 * sAt));

    // two leaves unfold as the tip passes them (and fold again as it draws back)
    for (int j = 0; j < 2; j++) {
      float sN = j == 0 ? 0.28 : 0.47, side = j == 0 ? 1.0 : -1.0;
      vec2 nd = j == 0 ? N1 : N2;
      float nt = j == 0 ? n1t : n2t;
      float u = smoothstep(sN + 0.03, sN + 0.32, g);
      if (u <= 0.0) continue;
      float ang = nt + side * ((0.95 + 0.15 * iEvolve.y) * u + 0.25 * age) - 0.2 * side * (1.0 - u);
      float L = (j == 0 ? 0.078 : 0.07) * u;
      vec2 q = rotv(p - nd, 1.5708 - ang);
      q.x -= 0.012 * sin(3.1416 * clamp(q.y / (2.0 * L), 0.0, 1.0)) * side;   // a slight curve
      float d = vesica((q - vec2(0.0, L)) / u, L / u, 0.024) * u;
      float h, rib = segd(q, vec2(0.0), vec2(0.0, 1.8 * L), h);
      float lv = 1.0 - 0.35 * age;
      glow(abs(d), 0.0045, 0.85 * lv, mix(iColB, iColC, 0.5));
      glow(rib, 0.0025, 0.5 * lv, mix(iColB, iColC, 0.4));
      col += mix(iColA, iColB, 0.6) * 0.3 * lv * smoothstep(0.004, -0.01, d);
    }
  }
  vec2 F = T;

  // --- the bud and the flower: five petals on the tip, opening one by one, then falling
  if (bud > 0.0 && m < 47.0) {
    float sc = bud * (1.0 + 0.08 * iEvolve.w);
    float ds = 1e3, fill = 0.0;
    for (int i = 0; i < 5; i++) {
      float fi = float(i);
      float phi = (fi - 2.0) * 0.56;
      float rk = i == 0 ? 0.0 : i == 4 ? 1.0 : i == 1 ? 2.0 : i == 3 ? 3.0 : 4.0;   // outer petals first
      float op = smoothstep(21.0 + 1.8 * rk, 25.0 + 1.8 * rk, m);
      float rd = i == 0 ? 0.0 : i == 3 ? 1.0 : i == 4 ? 2.0 : i == 1 ? 3.0 : 4.0;
      float td = 35.0 + 1.25 * rd + 0.4 * hash(fi);
      float tau = m - td;
      float s = sc * (0.82 + 0.18 * op);
      float ax = tth + phi * (0.1 + 0.9 * op);
      vec2 piv = F;
      float a = 1.0;
      if (tau > 0.0) {                                 // let go: drift down, turning, fading out
        float sd = phi == 0.0 ? 0.6 : sign(phi);
        piv += vec2(0.03 * sd * tau + 0.035 * sin(tau * 1.4 + fi) * min(tau, 1.0), -0.05 * tau - 0.028 * tau * tau);
        ax += sd * 0.45 * tau;
        a = 1.0 - smoothstep(0.6, 4.2, tau);
        if (a <= 0.0) continue;
      }
      vec2 q = rotv(p - piv, 1.5708 - ax) / s;
      float d = tear(q, 0.012, 0.042, 0.12) * s;
      if (tau > 0.0) {
        glow(abs(d), 0.0048, a * 0.95, iColC);
        col += mix(iColA, iColB, 0.7) * 0.4 * a * smoothstep(0.004, -0.012, d);
      } else {
        ds = min(ds, abs(d));
        fill = max(fill, smoothstep(0.004, -0.012, d) * (0.6 + 0.4 * smoothstep(0.17 * s, 0.0, length(q * s))));
      }
    }
    if (ds < 1e2) glow(ds, 0.005, 1.0, iColC);
    col += mix(iColA, iColB, 0.7) * 0.42 * fill;
  }

  // --- the heart, and the seed head that grows out of it
  if (recep > 0.0) {
    float rr = (0.01 + 0.008 * bud + 0.007 * smoothstep(36.0, 41.0, m)) * (1.0 - 0.55 * smoothstep(45.0, 50.5, m));
    float dr = length(p - F) - rr;
    col += recep * (iColC * smoothstep(0.004, -0.002, dr) * 0.9 + iColB * 0.6 * exp(-max(dr, 0.0) / 0.03) * (0.6 + 0.6 * bloomL));
  }
  float hr = 0.3 + 0.25 * iEvolve.z;
  if (m > 36.0 && m < 52.0) {
    vec2 v = p - F;
    float r = length(v), sector = 6.28318 / 20.0;
    float a = atan(v.y, v.x) - hr;
    float k = floor(a / sector + 0.5);
    float da = (a - k * sector) * r;
    float kk = mod(k, 20.0);
    float tr = 44.0 + 6.0 * fract(kk * 0.618 + 0.21);
    float len = 0.13 * smoothstep(36.5 + 2.5 * hash(kk + 3.0), 40.0 + 2.5 * hash(kk + 3.0), m);
    if (m < tr && len > 0.02) {
      float d = length(vec2(da, r - clamp(r, 0.02, len)));
      glow(d, 0.0032, 0.85, mix(iColB, iColC, 0.6));
      col += iColC * smoothstep(0.009, 0.004, length(vec2(da, r - len))) * (0.8 + 0.3 * iBright);
    }
  }

  // --- the seeds on the air
  if (m > 44.0 && m < 57.5) {
    for (int i = 0; i < 20; i++) {
      float kk = float(i);
      float tr = 44.0 + 6.0 * fract(kk * 0.618 + 0.21);
      float tau = m - tr;
      if (tau < 0.0 || tau > 6.0) continue;
      float al = hr + kk * 6.28318 / 20.0;
      float dA = mod(1.5708 - al + 3.1416, 6.28318) - 3.1416;
      float b = al + dA * smoothstep(0.0, 2.2, tau);
      vec2 vel = vec2(0.02 + 0.03 * hash(kk), 0.012 + 0.02 * hash(kk + 7.0));
      vec2 A = F + dirv(al) * (0.02 + 0.07 * smoothstep(0.0, 1.6, tau)) + vel * (tau + 0.15 * tau * tau)
             + vec2(0.015 * sin(1.6 * tau + kk), 0.01 * sin(2.1 * tau + 2.0 * kk)) * min(tau, 1.0);
      float edge = (1.0 - smoothstep(0.34, 0.45, A.y + 0.11)) * (1.0 - smoothstep(0.28, 0.38, abs(A.x)));   // gone before the frame's edge
      seed(p, A, b, 0.11, smoothstep(0.0, 1.0, tau), smoothstep(0.0, 0.8, tau), edge * (1.0 - smoothstep(2.6, 5.2, tau)));
    }
  }

  // --- the one that comes back, sways down and lands where it began
  if (m > 50.5) {
    float u = clamp((m - 50.5) / 7.5, 0.0, 1.0);
    float e = 1.0 - (1.0 - u) * (1.0 - u);
    vec2 A = vec2(mix(-0.3, 0.0, smoothstep(0.0, 1.0, u)) + 0.07 * sin(u * 9.0) * (1.0 - u) * (1.0 - u),
                  mix(0.78, home.y, e));
    float b = 1.5708 + 0.3 * cos(u * 9.0) * (1.0 - u) * (1.0 - u);
    float fold = smoothstep(58.0, 59.8, m);
    float L = mix(0.11, 0.04, fold);
    float land = smoothstep(56.5, 59.5, m);
    col += iColB * (0.1 + 0.05 * breath) * land * exp(-length(p - home) / 0.03);
    seed(p, A, b, L, 1.0 - fold, mix(1.0, 1.9, fold), smoothstep(50.5, 52.0, m));
  }
  o = vec4(col, 1.0);
}
