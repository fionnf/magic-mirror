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
// 3D (optional, for raymarched forms): write  float map(vec3 p)  (your scene, 1 unit = the wall's short side), then:
//   vec3 calcNormal(vec3 p) { vec2 e = vec2(0.003, 0.0); return normalize(vec3(map(p + e.xyy) - map(p - e.xyy), map(p + e.yxy) - map(p - e.yxy), map(p + e.yyx) - map(p - e.yyx))); }
//   vec3 ro = vec3(0.0, 0.0, -3.2), rd = normalize(vec3(uv, 1.5)); float t = 0.0, gl = 9.0;
//   for (int i = 0; i < 48; i++) { float d = map(ro + rd * t); gl = min(gl, d); if (d < 0.002 || t > 8.0) break; t += d; }
//   volumetric glow from the nearest miss:  col += iColC * 0.04 / (0.02 + gl * gl * 6.0);
// a single sphere needs no march: ray-sphere analytically, as in the reference piece.
