// Rose Pebble - art of the day 2026-11-10
// A translucent rose-glass pebble floats above a dark ground, catching a peach side light and revealing a warm refracted core that slowly changes shape and presence through the day.
float hash21(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x), mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p = p * 2.03 + 11.7; a *= 0.5; } return s; }
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
vec3 tone(vec3 c) { return 1.0 - exp(-c * 1.35); }
float fresnel(vec3 n, vec3 v, float k) { return pow(1.0 - clamp(dot(n, v), 0.0, 1.0), k); }
vec3 hueShift(vec3 c, float a) { const vec3 k = vec3(0.57735); float ca = cos(a); return c * ca + cross(k, c) * sin(a) + k * dot(k, c) * (1.0 - ca); }

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
  vec2 uv = (fragCoord - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);
  float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
  float T = iTime * (0.012 + 0.008 * iMid) + 0.13 * iEvolve.x;
  float music = clamp(0.25 * iBass + 0.35 * iMid + 0.40 * iTreble, 0.0, 1.0);

  vec3 colA = vec3(0.16, 0.06, 0.12);
  vec3 colB = vec3(0.72, 0.34, 0.46);
  vec3 colC = vec3(1.00, 0.78, 0.64);
  vec3 accent = hueShift(colC, 0.55);

  // slow atmospheric ground and wall glow
  vec2 p = uv;
  p.x += 0.04 * sin(0.7 * T + 2.0 * day);
  float haze = fbm(p * 1.8 + vec2(0.0, 0.12 * T));
  vec3 col = mix(colA * 0.85, colB * 0.55, 0.22 + 0.35 * haze);
  col += colB * 0.20 * exp(-3.2 * dot(uv + vec2(0.05, -0.02), uv + vec2(0.05, -0.02)));
  col += colC * 0.05 * exp(-8.0 * dot(uv - vec2(0.25, 0.18), uv - vec2(0.25, 0.18)));

  // day arc: the pebble rises, widens, and shifts slightly across the wall
  vec2 ctr = vec2(mix(-0.10, 0.16, day), mix(-0.06, 0.10, day)) + vec2(0.02 * sin(0.5 * T), 0.015 * cos(0.37 * T));
  float R = mix(0.30, 0.44, day) + 0.02 * iEvolve.y + 0.03 * music;

  // floor reflection and shadow under the form
  vec2 rf = uv - vec2(ctr.x, ctr.y - 0.50 * R);
  float shadow = exp(-18.0 * rf.x * rf.x - 40.0 * max(rf.y, 0.0) * max(rf.y, 0.0));
  col += colA * 0.85 * shadow;
  col += colB * 0.20 * exp(-14.0 * (rf.x * rf.x + (rf.y + 0.08) * (rf.y + 0.08)));

  // ray-sphere intersection for the glass body
  vec3 ro = vec3(0.0, 0.0, -2.9);
  vec3 rd = normalize(vec3(uv, 1.55));
  vec3 oc = ro - vec3(ctr, 0.0);
  float b = dot(oc, rd);
  float c = dot(oc, oc) - R * R;
  float h = b * b - c;

  float glow = exp(-max(length(uv - ctr) - R, 0.0) * 7.5);
  col += colB * 0.10 * glow;
  col += colC * 0.14 * glow * (0.45 + 0.55 * day);

  if (h > 0.0) {
    float t = -b - sqrt(h);
    vec3 p3 = ro + rd * t;
    vec3 n = normalize(p3 - vec3(ctr, 0.0));
    vec3 v = -rd;
    vec3 L = normalize(vec3(-0.65, 0.55, -0.35));
    vec3 B = normalize(vec3(0.28, -0.36, -0.90)); // soft bounce from below/back

    float dif = max(dot(n, L), 0.0);
    float back = max(dot(n, B), 0.0);
    float fr = fresnel(n, v, 3.0);
    float spec = pow(max(dot(reflect(-L, n), v), 0.0), 40.0);

    // refraction: sample a warped interior field through the glass
    vec3 rdir = refract(rd, n, mix(0.76, 0.71, day));
    vec2 ip = uv + rdir.xy * (0.55 + 0.12 * day);
    float inner = fbm(ip * 2.2 + vec2(0.0, 0.18 * T));
    float strata = smoothstep(0.25, 0.95, inner + 0.12 * sin(3.0 * ip.y + 0.6 * day));

    vec3 body = mix(colB, colC, 0.35 + 0.45 * strata);
    body = mix(body, hueShift(colC, 0.50), 0.18 * fr);
    body *= 0.85 + 0.55 * dif + 0.22 * back;
    body += colC * 0.25 * spec;
    body += accent * 0.10 * pow(fr, 4.0);
    body += colA * 0.25 * (1.0 - fr) * smoothstep(-0.20, 0.30, n.y);

    // bright rim and peach edge light
    body += colC * 0.55 * fr;
    body += accent * 0.75 * pow(fr, 1.8) * smoothstep(-0.15, 0.65, n.x + 0.10);

    // subtle volumetric core glow, stronger later in the day
    float core = exp(-9.0 * dot(uv - ctr, uv - ctr));
    body += mix(colB, colC, 0.5) * (0.12 + 0.10 * day) * core;

    col = mix(col, body, 0.96);
  }

  // surrounding vignette to hold the eye
  col *= 0.80 + 0.20 * smoothstep(1.15, 0.15, length(uv));
  col += colA * 0.12 * (1.0 - smoothstep(0.15, 1.2, length(uv)));
  fragColor = vec4(tone(col), 1.0);
}