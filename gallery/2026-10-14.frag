// Cobalt Aperture, Slowly Opening - art of the day 2026-10-14
// A Turrell-like opening in a lit cobalt wall wakes as a small high window at dawn, swells into a pale sky-filled field at noon, sinks and widens through the evening, and narrows to a single blue slit by night, while faint inset frames record each hour of the day's music.
float sdRR(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 fragColor, in vec2 fragCoord){
  vec2 R = iResolution;
  vec2 uv = (fragCoord - 0.5 * R) / R.y;
  float a = R.x / R.y;
  float s = min(a, 1.0);
  float c = iClock;
  float day = smoothstep(5.0, 12.0, c) * (1.0 - smoothstep(15.0, 22.0, c));
  float eve = smoothstep(14.0, 19.0, c) * (1.0 - smoothstep(21.0, 24.0, c));
  vec2 hs = vec2((0.10 + 0.16 * day + 0.14 * eve) * s, max(0.022, 0.025 + 0.30 * day - 0.04 * eve));
  hs.x += 0.015 * sin(iTime * 0.0043) * s;
  hs.y *= 1.0 + 0.06 * sin(iTime * 0.0027 + 1.3);
  hs *= 1.0 + 0.04 * iBreath;
  vec2 cen = vec2(0.03 * sin(iTime * 0.011 + iSong * 6.2832) + 0.02 * sin(iTime * 0.0031), 0.16 - 0.16 * smoothstep(4.0, 12.0, c) - 0.12 * smoothstep(13.0, 21.0, c) + 0.012 * sin(iTime * 0.007));
  cen.x *= s;
  cen.x += 0.003 * sin(iBeatPhase * 6.2832);
  float soft = mix(0.035, 0.012, iTension) + 0.008 * sin(iTime * 0.017);
  float d = sdRR(uv - cen, hs, 0.02);
  float inside = 1.0 - smoothstep(-soft, soft, d);
  vec3 ground = mix(iColA, iColB, clamp(0.42 + 0.18 * day + 0.12 * eve + 0.18 * uv.y, 0.0, 1.0));
  float spill = exp(-max(d, 0.0) * mix(9.0, 5.0, iBright));
  ground = mix(ground, iColB * 1.12, spill * 0.35);
  float k = 0.22 + 0.48 * day + 0.08 * eve + 0.07 * sin(iKey) + 0.05 * sin(iTime * 0.0021);
  vec3 ap = mix(iColB, iColC, clamp(k, 0.0, 0.8));
  ap *= 0.9 + 0.1 * smoothstep(-0.25, 0.0, d);
  float rings = 0.0;
  for (int i = 0; i < 24; i++) {
    float hr = float(i);
    float on = step(hr, c);
    float r = 0.035 + hr * 0.011;
    float x = (d - r) / 0.0035;
    rings += exp(-x * x) * iDay[i] * on;
  }
  ground = mix(ground, mix(iColB, iColC, 0.5), clamp(rings * 0.18, 0.0, 0.3));
  vec3 col = mix(ground, ap, inside);
  col += (hash(fragCoord + fract(iTime * 0.01)) - 0.5) * 0.01;
  col = clamp(col, 0.0, 0.92);
  fragColor = vec4(col, 1.0);
}