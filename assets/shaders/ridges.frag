// Ridges: mountain ridges in morning fog, five layers of one hue, each paler and softer than the
// one before. The fog lifts through the day (iClock); the bass breathes it.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
float ridge(float x, float seed){ return 0.5 * noise(vec2(x * 1.3 + seed, seed)) + 0.25 * noise(vec2(x * 3.1 + seed * 2.0, seed)) + 0.12 * noise(vec2(x * 7.0, seed)); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.006;
  float day = 0.5 - 0.5 * cos((iClock - 4.0) / 24.0 * 6.2832);     // fog thickest before dawn
  float fog = 0.75 - 0.4 * day + 0.1 * iBreath;
  vec3 sky = mix(iColC, iColB, 0.35 + 0.3 * day);
  vec3 col = mix(sky, iColC, smoothstep(0.4, 1.0, uv.y) * 0.3);
  for (int i = 4; i >= 0; i--) {
    float fi = float(i);
    float depth = fi / 4.0;
    float h = 0.12 + 0.13 * fi + 0.22 * ridge(uv.x * (1.0 + 0.3 * fi) + t * (0.3 + 0.1 * fi), fi * 7.3);
    vec3 tone = mix(iColA, iColB, depth * 0.9);
    tone = mix(tone, sky, depth * fog);
    float m = smoothstep(h + 0.004, h - 0.004, uv.y);
    float haze = smoothstep(h - 0.25, h, uv.y) * 0.35 * fog;
    col = mix(col, tone, m);
    col = mix(col, sky, haze * m);
  }
  col += (hash(fc) - 0.5) * 0.015;
  o = vec4(col, 1.0);
}
