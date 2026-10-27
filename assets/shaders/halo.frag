// Halo: a dark rounded form standing in front of a glowing wall, the light escaping around its
// edges; the halo swells a little with the bass.
// Over tens of minutes the form changes: a tall tablet, a pill, almost a disc; the light spreads
// wide or hugs the edge; and the form slowly parts down the middle, light pouring through the
// slit, then closes again.
float sdRound(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  vec4 e = iEvolve;
  float t = iTime * 0.015;
  vec2 p = uv - vec2(0.02 * sin(t), 0.0);
  vec2 b = vec2(0.22 * (1.0 + 0.18 * e.x), 0.34 * (1.0 - 0.18 * e.x));
  float rr = min(b.x, b.y) * (0.3 + 0.65 * (0.5 + 0.5 * e.z));   // corners: soft .. fully round
  float d = sdRound(p, b, rr);
  float part = smoothstep(0.15, 0.9, e.w);              // the form parts, part of the cycle
  if (part > 0.0) {
    float gap = 0.035 * part;
    vec2 hb = vec2(b.x * 0.5, b.y);
    float hr = min(rr, hb.x * 0.9);
    float dl = sdRound(p + vec2(hb.x + gap, 0.012 * part), hb, hr);
    float dr = sdRound(p - vec2(hb.x + gap, 0.012 * part), hb, hr);
    d = mix(d, min(dl, dr), smoothstep(0.0, 0.25, part));
  }
  float spread = 11.0 * (1.0 - 0.3 * e.y) - 3.0 * iBreath;
  float glow = exp(-max(d, 0.0) * spread);
  vec3 col = mix(iColA * 0.6, iColB, glow * 0.9);
  col = mix(col, iColC, exp(-max(d, 0.0) * 28.0) * 0.8);
  col = mix(col, iColA * 0.25, smoothstep(0.004, -0.004, d));
  col += (grain(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
