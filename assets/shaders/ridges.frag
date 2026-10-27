// Ridges: mountain ridges in morning fog, five layers of one hue, each paler and softer than the
// one before. The fog lifts through the day (iClock); the bass breathes it.
// Over tens of minutes (iEvolve) the range changes: the ridges rise and settle, turn jagged or
// rounded, crowd together or open out into deep valleys, and a pale sun or moon rises behind the
// far ridge and sets again.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
float ridge(float x, float seed, float rough){ return 0.5 * noise(vec2(x * 1.3 + seed, seed)) + 0.25 * noise(vec2(x * 3.1 + seed * 2.0, seed)) + 0.12 * rough * noise(vec2(x * 7.0, seed)); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  vec4 e = iEvolve;
  float t = iTime * 0.006;
  float day = 0.5 - 0.5 * cos((iClock - 4.0) / 24.0 * 6.2832);     // fog thickest before dawn
  float fog = 0.75 - 0.4 * day + 0.1 * iBreath;
  vec3 sky = mix(iColC, iColB, 0.35 + 0.3 * day);
  vec3 col = mix(sky, iColC, smoothstep(0.4, 1.0, uv.y) * 0.3);
  float rough = 1.0 + 1.3 * e.y;                                    // rounded .. jagged
  float step_ = 0.13 + 0.025 * e.x;                                 // ridges crowd or open out
  float tall = (0.22 + 0.06 * e.z) * (1.0 - 0.25 * max(e.x, 0.0));  // low hills .. tall peaks
  float h4 = 0.12 + step_ * 4.0 + tall * 0.5;
  vec2 sun = vec2(0.32 + 0.3 * e.w, h4 - 0.02 + 0.2 * smoothstep(-0.2, 0.9, e.w));
  float disc = smoothstep(0.075, 0.065, length((uv - sun) * vec2(iResolution.x / iResolution.y, 1.0)));
  float rise = smoothstep(-0.1, 0.5, e.w);
  col = mix(col, iColC, disc * 0.85 * rise);
  col += iColC * 0.12 * rise * exp(-length((uv - sun) * vec2(iResolution.x / iResolution.y, 1.0)) * 7.0);
  for (int i = 4; i >= 0; i--) {
    float fi = float(i);
    float depth = fi / 4.0;
    float h = 0.12 + step_ * fi + tall * ridge(uv.x * (1.0 + 0.3 * fi) + t * (0.3 + 0.1 * fi), fi * 7.3, rough);
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
