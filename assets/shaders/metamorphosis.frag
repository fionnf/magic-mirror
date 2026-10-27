// Metamorphosis: one body of violet glass that changes form once round the clock face every hour -
// a drop on the hour, swelling to a full orb at :10, opening into a five-petalled flower at :20,
// parting into three droplets that circle each other at :30, joining into a ring of glass at :40,
// closing into a crescent at :50 that narrows back to the drop. Each form holds for five minutes and
// melts into the next over the following five, lit like the glass orb: a cold rim light that walks
// round with the day, a blue glow on the far edge, veins moving slowly inside.
float n2(vec2 p){ return sin(p.x * 1.7 + sin(p.y * 1.3)) * 0.5 + sin(p.y * 2.3 - p.x * 0.7) * 0.5; }
float smin(float a, float b, float k){ float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0); return mix(b, a, h) - k * h * (1.0 - h); }
float smax(float a, float b, float k){ return -smin(-a, -b, k); }
mat2 rot(float a){ return mat2(cos(a), -sin(a), sin(a), cos(a)); }
float tear(vec2 p, float r1, float r2, float h){      // a round end r1 tapering to r2 at height h
  p.x = abs(p.x);
  float b = (r1 - r2) / h, a = sqrt(1.0 - b * b), k = dot(p, vec2(-b, a));
  if (k < 0.0) return length(p) - r1;
  if (k > a * h) return length(p - vec2(0.0, h)) - r2;
  return dot(p, vec2(a, b)) - r1;
}

// the six forms, each a signed distance (< 0 inside the glass)
float form(int k, vec2 uv, float t){
  float a = atan(uv.y, uv.x), r = length(uv);
  if (k == 0) {                                          // a drop, pointed at the top
    return tear(uv - vec2(0.0, -0.08), 0.16, 0.03, 0.24);
  }
  if (k == 1) return r - (0.3 + 0.012 * sin(a * 3.0 + t * 2.0));                  // the full orb
  if (k == 2) {                                          // the flower: five round petals round a heart
    float d = r - 0.16;
    for (int i = 0; i < 5; i++) {
      float b = t * 0.5 + float(i) * 1.25664;
      d = smin(d, length(uv - 0.19 * vec2(cos(b), sin(b))) - 0.11, 0.04);
    }
    return d;
  }
  if (k == 3) {                                          // three droplets circling, just touching
    float d = 1e3;
    for (int i = 0; i < 3; i++) {
      float b = t * 0.8 + float(i) * 2.0944;
      d = smin(d, length(uv - 0.24 * vec2(cos(b), sin(b))) - 0.13, 0.05);
    }
    return d;
  }
  if (k == 4) return abs(length(uv * vec2(1.0, 1.08)) - 0.27) - 0.075;         // the ring
  vec2 q = rot(0.5 + t * 0.2) * uv;                      // the crescent
  return smax(length(q) - 0.3, -(length(q - vec2(0.15, 0.05)) - 0.245), 0.04);
}

float shape(vec2 uv, float t, int k, float s){
  // the old form melts away while the new one swells out of it, the two flowing together where they
  // meet (no form is more than 0.3 deep, so at s = 0 and 1 each form is exactly itself)
  float a = form(k, uv, t);
  if (s <= 0.0) return a;
  float b = form(k == 5 ? 0 : k + 1, uv, t);
  float e = s * s * (3.0 - 2.0 * s);
  float keep = 0.405 * e * (1.0 - e) * 4.0 * 0.5;     // mid-change both stay full and flow together
  return smin(a + 0.45 * e - keep, b + 0.45 * (1.0 - e) - keep, 0.1);
}

void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y) / 1.15;
  float t = iTime * 0.03;
  float p = fract(iClock) * 6.0;                         // where we are in the hour, 0..6
  int k = int(floor(p));
  float s = smoothstep(0.5, 1.0, fract(p));              // hold half the stage, melt for the other half
  float d = shape(uv, t, k, s) - 0.01 * iBreath;
  vec2 h = vec2(0.004, 0.0);
  vec2 nrm = normalize(vec2(shape(uv + h.xy, t, k, s) - shape(uv - h.xy, t, k, s),
                            shape(uv + h.yx, t, k, s) - shape(uv - h.yx, t, k, s)) + 1e-6);
  float body = smoothstep(0.01, -0.02, d);
  float depth = clamp(-d / 0.16, 0.0, 1.0);
  vec2 L = normalize(vec2(cos(2.4 + iClock * 0.26), sin(2.4 + iClock * 0.26)));   // the key light moves with the day
  float rim = exp(-pow(d / 0.02, 2.0));
  float lit = pow(max(dot(nrm, L), 0.0), 2.0);
  float under = pow(max(dot(nrm, -L), 0.0), 3.0);
  float melt = sin(3.14159 * s);                         // the glass stirs while it changes form
  float veins = (0.07 + 0.05 * iEvolve.y + 0.08 * melt) * n2(uv * (3.5 + 1.5 * iEvolve.x) + t * (1.0 + 3.0 * melt));
  vec3 col = iColA * 0.15;
  col = mix(col, mix(iColA * 0.9, iColB * 0.45, pow(1.0 - depth, 2.0) * 0.8 + veins), body);
  col += iColC * rim * (0.25 + 1.2 * lit);               // the white edge light
  col += iColB * rim * under * 1.3;                      // a blue glow along the far edge
  col += iColC * 0.12 * body * smoothstep(0.45, 0.0, length(uv - L * 0.18));   // a soft inner sheen
  col += iColB * (0.06 + 0.04 * melt) * exp(-d * 9.0) * step(0.0, d);         // a halo in the room, wider while it melts
  o = vec4(col, 1.0);
}
