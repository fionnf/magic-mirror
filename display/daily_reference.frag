// ---- toolkit: copy what you need ----
float hash21(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x), mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p = p * 2.03 + 11.7; a *= 0.5; } return s; }
vec2 warp(vec2 p, float t) { return p + 0.35 * vec2(fbm(p + t), fbm(p + 7.3 - t)); }   // domain warp: liquid, silky fields
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
vec3 ramp(float t) { t = clamp(t, 0.0, 1.0); return t < 0.5 ? mix(iColA, iColB, t * 2.0) : mix(iColB, iColC, t * 2.0 - 1.0); }   // shadow -> mid -> highlight
vec3 hueShift(vec3 c, float a) { const vec3 k = vec3(0.57735); float ca = cos(a); return c * ca + cross(k, c) * sin(a) + k * dot(k, c) * (1.0 - ca); }   // a = radians: a small accent hue
vec3 tone(vec3 c) { return 1.0 - exp(-c * 1.35); }   // soft shoulder: glows roll off instead of clipping to white
float fresnel(vec3 n, vec3 v, float k) { return pow(1.0 - clamp(dot(n, v), 0.0, 1.0), k); }   // rim light, k about 2-4
float sdSphere(vec3 p, float r) { return length(p) - r; }
float sdTorus(vec3 p, vec2 t) { vec2 q = vec2(length(p.xz) - t.x, p.y); return length(q) - t.y; }
float sdRBox(vec3 p, vec3 b, float r) { vec3 q = abs(p) - b; return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0) - r; }
float smin(float a, float b, float k) { float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0); return mix(b, a, h) - k * h * (1.0 - h); }   // melts shapes together
void mainImage(out vec4 fragColor, in vec2 fragCoord) {
  vec2 uv = (fragCoord - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);
  float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
  float T = iTime * 0.03 + iEvolve.x * 0.6;
  vec3 ro = vec3(0.0, 0.0, -3.2), rd = normalize(vec3(uv, 1.5));
  // atmosphere: a warped, silky field behind everything, darker towards the edges
  vec2 q = warp(uv * 1.5 + vec2(0.0, T), T);
  float haze = fbm(q * 1.4);
  vec3 col = ramp(0.12 + 0.55 * haze) * (0.62 - 0.38 * length(uv)) * (0.8 + 0.5 * day);
  // the hero: a glass sphere that travels and grows through the day
  vec3 ctr = vec3(mix(-0.30, 0.28, day), mix(-0.22, 0.10, day) + 0.04 * iEvolve.y, 0.0);
  float R = mix(0.36, 0.62, day);
  vec3 oc = ro - ctr;
  float b = dot(oc, rd), h = b * b - (dot(oc, oc) - R * R);
  float miss = sqrt(max(dot(oc, oc) - b * b, 0.0));
  col += iColB * 0.55 * exp(-max(miss - R, 0.0) * 5.0) * (0.7 + 0.5 * day);          // soft halo
  if (h > 0.0) {
    vec3 p = ro + rd * (-b - sqrt(h));
    vec3 n = normalize(p - ctr);
    vec3 L = normalize(vec3(-0.55, 0.7, -0.5));
    float dif = max(dot(n, L), 0.0);
    float fr = fresnel(n, -rd, 3.0);
    vec3 rf = refract(rd, n, 0.72);                                                  // look through the glass
    vec2 q2 = warp((uv + rf.xy * 0.45) * 1.7 + vec2(0.0, T), T + 3.0);
    vec3 inner = ramp(0.25 + 0.7 * fbm(q2 * 2.0)) * (0.55 + 0.9 * pow(max(dot(n, -rd), 0.0), 2.0));
    float spec = pow(max(dot(reflect(-L, n), -rd), 0.0), 36.0);
    col = inner * (0.45 + 0.65 * dif) + iColC * fr * 1.0 + hueShift(iColC, 0.6) * pow(fr, 6.0) * 0.35 + iColC * spec * 0.8;
    col += iColB * 0.25 * smoothstep(0.0, 1.0, -n.y) * (1.0 - fr);                  // light bouncing up from below
  }
  fragColor = vec4(tone(col), 1.0);
}
