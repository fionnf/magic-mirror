// Eclipse: a dark disc whose rim burns - a thin hot ring and a cool inner glow - on black; the
// ring's brightest point travels slowly round with the key, the corona breathes with the bass.
// Over tens of minutes the corona gathers into three to seven long streamers or smooths out, the
// burning ring thickens and thins, and the dark disc slides off-centre so a bright crescent opens
// on one side and closes again.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  vec4 e = iEvolve;
  float t = iTime * 0.02;
  float r = length(uv), a = atan(uv.y, uv.x);
  float R = 0.33;
  float hot = 0.6 + 0.4 * cos(a - (t + iKey * 6.283) - 2.2);
  float ringW = (0.012 + 0.006 * iBreath) * (1.0 + 0.45 * e.y);
  float ring = exp(-pow((r - R) / ringW, 2.0)) * hot;
  float n = 5.0 + 2.0 * e.z, f = floor(n);              // 3 .. 7 streamers, blended between whole numbers
  float rays = mix(0.5 + 0.5 * cos(a * f + t), 0.5 + 0.5 * cos(a * (f + 1.0) - t * 0.6), smoothstep(0.0, 1.0, n - f));
  float rayK = smoothstep(-0.3, 0.7, e.x);       // how strongly the corona breaks into streamers
  float fall = (9.0 - 3.0 * iBreath) * mix(1.0, 0.4 + 1.3 * (1.0 - rays), rayK);
  float corona = exp(-max(r - R, 0.0) * fall) * step(R, r) * (0.35 + 0.4 * hot);
  // the dark disc slides off-centre: a crescent of the lit face shows on one side
  vec2 off = 0.06 * smoothstep(0.0, 0.9, e.w) * vec2(cos(t * 0.5 + 1.0), sin(t * 0.5 + 1.0));
  float moon = smoothstep(0.0, 0.006, length(uv - off) - R * 0.97);   // 0 behind the disc
  float inner = smoothstep(R, R * 0.2, r) * smoothstep(-0.9, 0.6, -uv.y * 1.2 + uv.x * 0.3);
  vec3 col = iColA * 0.15;
  col += iColB * corona * 0.8;
  col += mix(iColB, iColC, 0.6) * inner * 0.55 * step(r, R);
  col += iColC * 0.8 * moon * step(r, R) * smoothstep(R, R - 0.06, r) * smoothstep(R * 0.4, R, r);
  col += iColC * ring;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
