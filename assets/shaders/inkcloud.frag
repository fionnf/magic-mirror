// Ink cloud: one drop of ink that lives an hour of weather - it falls into still water and blooms, gathers into a cloud, rains itself into a pool and draws itself back up into the drop.
// On the hour the drop hangs at the top; it falls and blooms into a soft mushroom plume, its rim curling
// into two vortex rings, by :10; the plume spreads, rises and gathers into a floating cloud by :20; the
// cloud darkens and begins to rain fine streaks at about :24, raining hard at :30; the cloud rains itself
// out while the streaks collect into a pool along the bottom by :40; the pool draws itself up from its
// middle into a column that pinches into one drop, rising with a thin tail at :50, and the drop climbs to
// the top, swallowing its tail, to hang there ready to fall again. Each form rests a moment and flows into
// the next over most of its ten minutes. Lit like light through ink: thin edges glow where light gets
// through, the body deepens where the ink is thick, a pale rim catches the light from the surface above
// and curling striations follow the swirl of the water.
float n2(vec2 p){ return sin(p.x * 1.7 + sin(p.y * 1.3)) * 0.5 + sin(p.y * 2.3 - p.x * 0.7) * 0.5; }
float h1(float x){ return fract(sin(x * 127.1 + 31.7) * 43758.5453); }
float smin(float a, float b, float k){ float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0); return mix(b, a, h) - k * h * (1.0 - h); }
mat2 rot(float a){ return mat2(cos(a), -sin(a), sin(a), cos(a)); }
float ell(vec2 q, vec2 r){ q += vec2(1.3e-4, 0.7e-4); float k0 = length(q / r), k1 = length(q / (r * r)); return k0 * (k0 - 1.0) / k1; }

// six forms, eight soft blobs each (x, y, radius x, radius y): the drop at the top, the mushroom plume,
// the cloud, the raining cloud, the pool, the rising drop with its tail
const vec4 K[48] = vec4[48](
  vec4(0.0, 0.37, 0.075, 0.082), vec4(-0.02, 0.37, 0.04, 0.04), vec4(0.02, 0.37, 0.04, 0.04), vec4(0.0, 0.36, 0.04, 0.05),
  vec4(0.0, 0.38, 0.035, 0.05), vec4(0.0, 0.385, 0.03, 0.05), vec4(0.0, 0.35, 0.04, 0.04), vec4(0.0, 0.38, 0.04, 0.04),
  vec4(0.0, -0.05, 0.15, 0.075), vec4(-0.15, -0.03, 0.075, 0.07), vec4(0.15, -0.03, 0.075, 0.07), vec4(0.0, 0.07, 0.045, 0.08),
  vec4(0.0, 0.2, 0.03, 0.08), vec4(0.0, 0.31, 0.022, 0.07), vec4(0.0, -0.1, 0.1, 0.05), vec4(0.0, 0.37, 0.018, 0.05),
  vec4(0.0, 0.12, 0.24, 0.065), vec4(-0.17, 0.15, 0.085, 0.075), vec4(0.17, 0.16, 0.09, 0.075), vec4(-0.05, 0.21, 0.11, 0.1),
  vec4(0.08, 0.22, 0.1, 0.09), vec4(-0.01, 0.29, 0.075, 0.07), vec4(-0.13, 0.23, 0.07, 0.065), vec4(0.19, 0.2, 0.06, 0.06),
  vec4(0.0, 0.1, 0.25, 0.06), vec4(-0.18, 0.13, 0.08, 0.065), vec4(0.18, 0.135, 0.085, 0.065), vec4(-0.06, 0.18, 0.1, 0.085),
  vec4(0.08, 0.185, 0.1, 0.08), vec4(0.0, 0.245, 0.07, 0.06), vec4(-0.13, 0.19, 0.065, 0.055), vec4(0.19, 0.17, 0.055, 0.05),
  vec4(0.0, -0.37, 0.26, 0.045), vec4(-0.17, -0.365, 0.1, 0.04), vec4(0.17, -0.365, 0.1, 0.04), vec4(0.0, -0.355, 0.11, 0.045),
  vec4(-0.09, -0.37, 0.09, 0.04), vec4(0.09, -0.37, 0.09, 0.04), vec4(-0.22, -0.373, 0.055, 0.036), vec4(0.22, -0.373, 0.055, 0.036),
  vec4(0.0, 0.0, 0.07, 0.078), vec4(0.0, -0.175, 0.028, 0.055), vec4(0.0, -0.175, 0.028, 0.055), vec4(0.0, 0.01, 0.045, 0.05),
  vec4(0.0, -0.09, 0.038, 0.06), vec4(0.0, -0.09, 0.038, 0.06), vec4(0.0, -0.235, 0.026, 0.042), vec4(0.0, -0.235, 0.026, 0.042));
// how late each blob sets off when its form flows into the next (the trail behind the falling drop,
// the column rising out of the middle of the pool, the tail following the drop up)
const float DL[48] = float[48](
  0.0, 0.05, 0.05, 0.12, 0.22, 0.3, 0.0, 0.35,
  0.1, 0.0, 0.0, 0.15, 0.2, 0.25, 0.1, 0.3,
  0.0, 0.05, 0.05, 0.1, 0.1, 0.15, 0.1, 0.15,
  0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
  0.14, 0.06, 0.06, 0.06, 0.03, 0.03, 0.0, 0.0,
  0.0, 0.14, 0.14, 0.0, 0.07, 0.07, 0.22, 0.22);
// the two vortices that curl the ink (x, y of the right one, strength, width)
const vec4 SW[6] = vec4[6](vec4(0.1, 0.37, 0.0, 0.07), vec4(0.165, 0.0, 2.8, 0.07), vec4(0.2, 0.2, 1.3, 0.07),
  vec4(0.2, 0.16, 0.6, 0.07), vec4(0.2, -0.37, 0.0, 0.07), vec4(0.1, 0.0, 0.0, 0.07));

vec2 swirl(vec2 uv, vec4 w){
  for (int i = 0; i < 2; i++) {
    float sd = i == 0 ? 1.0 : -1.0;
    vec2 c = vec2(sd * w.x, w.y), q = uv - c;
    uv = c + rot(sd * w.z * exp(-dot(q, q) / (w.w * w.w))) * q;
  }
  return uv;
}

float blobs(vec2 uv, int k, int kn, float s, float t){
  float d = 1e3;
  float kk = 0.035 + (k == 4 ? 0.015 : 0.035) * sin(3.14159 * s);   // the ink holds together while it moves
  for (int i = 0; i < 8; i++) {
    float dl = DL[k * 8 + i];
    vec4 c0 = K[k * 8 + i], c1 = K[kn * 8 + i];
    vec4 c = mix(c0, c1, smoothstep(dl, dl + 0.65, s));
    if (k == 4) {                                        // the pool gathers in first, then lifts
      float g = smoothstep(dl, dl + 0.45, s);
      c = vec4(mix(c0.x, c1.x, g), mix(c0.y, c1.y, smoothstep(dl + 0.15, dl + 0.8, s)), mix(c0.zw, c1.zw, g));
    }
    c.xy += 0.005 * vec2(sin(t * 1.3 + c.y * 3.0), cos(t * 1.1 + c.x * 3.0 + c.y * 2.0));   // the ink never quite still (it sways as one)
    d = smin(d, ell(uv - c.xy, c.zw), kk);
  }
  return d;
}

float shape(vec2 uv, float t, int k, float s, out vec2 wuv){
  int kn = k == 5 ? 0 : k + 1;
  vec4 w = mix(SW[k], SW[kn], smoothstep(0.0, 1.0, s));
  if (k == 0) w.z = SW[1].z * smoothstep(0.35, 1.0, s);      // the curl wakes once the falling drop has opened
  w.z *= 1.0 + 0.12 * sin(t * 0.7) + 0.15 * iEvolve.z;
  wuv = swirl(uv, w);
  if (k != 3) return blobs(wuv, k, kn, s, t);
  // the cloud rains itself away while the pool fills along the bottom (they never touch: the rain joins them)
  float sc = 1.0 - 0.75 * smoothstep(0.1, 0.92, s);          // the cloud shrinks into itself as it rains
  vec2 cc = vec2(0.0, 0.17);
  float a = blobs((wuv - cc) / sc + cc, 3, 3, 0.0, t) * sc + 0.3 * smoothstep(0.82, 1.0, s);
  float sp = 0.45 + 0.55 * smoothstep(0.05, 0.85, s);          // the pool spreads out from where the rain lands
  vec2 pc = vec2(0.0, -0.41);
  float b = blobs((wuv - pc) / sp + pc, 4, 4, 0.0, t) * sp + 0.03 * (1.0 - smoothstep(0.05, 0.6, s)) + 0.25 * (1.0 - smoothstep(0.0, 0.1, s));
  return smin(a, b, 0.05);
}

float rain(vec2 uv, float t, float p){
  float amt = smoothstep(2.2, 2.6, p) * (1.0 - smoothstep(3.85, 4.1, p));
  if (amt <= 0.0) return 0.0;
  float ybot = mix(0.07, -0.4, smoothstep(2.2, 2.75, p));      // the front of the first rain
  float sc = 1.0 - 0.75 * smoothstep(0.1, 0.92, clamp((p - 3.15) / 0.85, 0.0, 1.0));
  float ytop = mix(0.17 - 0.12 * sc, -0.4, smoothstep(3.85, 4.1, p));   // under the shrinking cloud, then falling after it
  float cw = 0.03, i = floor(uv.x / cw), hi = h1(i), hj = h1(i + 17.0);
  float xc = (i + 0.5 + 0.3 * (hj - 0.5)) * cw;
  float v = uv.y * 2.6 + t * (1.6 + 0.8 * hi) + hi * 7.0, f = fract(v);
  float seg = smoothstep(0.0, 0.06, f) * smoothstep(0.5, 0.2, f);
  float line = exp(-pow((uv.x - xc) / 0.0055, 2.0));
  float on = step(hj, 0.25 + 0.75 * amt) * smoothstep(0.03 + 0.23 * sc, 0.23 * sc - 0.01, abs(uv.x));
  return amt * seg * line * on * smoothstep(ybot, ybot + 0.03, uv.y) * smoothstep(ytop, ytop - 0.03, uv.y);
}

void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.x;
  float t = iTime * 0.3;
  float p = fract(iClock) * 6.0;                           // where we are in the hour, 0..6
  int k = int(floor(p));
  float s = clamp((fract(p) - 0.15) / 0.85, 0.0, 1.0);     // rest a moment in each form, flow for the rest
  vec2 wuv, dum;
  float d = shape(uv, t, k, s, wuv) - 0.006 * iBreath;
  vec2 h = vec2(0.004, 0.0);
  vec2 gr = vec2(shape(uv + h.xy, t, k, s, dum) - shape(uv - h.xy, t, k, s, dum),
                 shape(uv + h.yx, t, k, s, dum) - shape(uv - h.yx, t, k, s, dum)) / (2.0 * h.x);
  vec2 nrm = gr / (length(gr) + 1e-4);
  d = mix(d, d / clamp(length(gr), 0.35, 3.0), exp(-d * d / 0.0009));   // a true distance at the edge, so it keeps its width where the water shears
  float dark = smoothstep(2.1, 2.9, p) * (1.0 - smoothstep(3.3, 3.9, p));   // the cloud darkens before the rain
  float body = smoothstep(0.008, -0.012, d);
  float thick = clamp(-d / 0.08, 0.0, 1.0);
  vec2 L = normalize(vec2(0.4 * sin(iClock * 0.26), 1.0));  // light from the surface above, leaning with the day
  float rim = exp(-pow(d / 0.012, 2.0));
  float lit = pow(max(dot(nrm, L), 0.0), 1.5);
  float under = pow(max(dot(nrm, -L), 0.0), 2.0);
  float stri = n2(wuv * vec2(16.0, 9.0) + vec2(0.0, t * 0.8)) * (0.5 + 0.3 * iEvolve.x);
  float through = pow(1.0 - thick, 2.0) * 0.7 + 0.18 * stri;             // light gets through the thin ink
  vec3 ink = mix(iColB * (0.78 - 0.18 * dark), iColC, clamp(through * (1.0 - 0.5 * dark), 0.0, 1.0) * 0.55);
  vec3 col = iColA * 0.15;
  col = mix(col, ink, body);
  col += iColC * rim * (0.2 + 0.9 * lit);                  // the pale edge catching the light
  col += iColB * rim * under * 0.6;
  col += iColB * 0.07 * exp(-max(d, 0.0) * 10.0) * step(0.0, d);   // the stained water round it
  float r = rain(uv, t, p) * (1.0 - body);
  col = mix(col, mix(iColB, iColC, 0.55), r);
  o = vec4(col, 1.0);
}
