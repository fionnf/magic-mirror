// Ink orbs: two soft spheres of ink that touch at a single point, darkest where they meet and
// fading outward into the paper; they drift a hair apart and together with the bass.
// Over tens of minutes the pair tips from upright to leaning, one orb grows as the other shrinks,
// the ink soaks deeper or stays shallow, and the two slowly part, paper showing between them, then
// come back to touch.
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(127.1, 311.7))) * 43758.5453); }
float sphere(vec2 p, vec2 pole, vec2 dir, float r, float soak){
  vec2 c = pole + dir * r;                       // the circle sits on its pole
  float inside = smoothstep(r * 1.05, r * 0.75, length(p - c));
  float k = clamp(length(p - pole) / (2.0 * r), 0.0, 1.0);
  return inside * pow(1.0 - k, soak);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  vec4 e = iEvolve;
  float t = iTime * 0.02;
  float tilt = 0.45 * e.z;                       // upright .. leaning
  vec2 dir = vec2(sin(tilt), cos(tilt));
  float gap = 0.006 + 0.018 * iBreath + 0.035 * smoothstep(0.15, 0.9, e.w);   // they part, part of the cycle
  float r = 0.24 + 0.006 * sin(t * 2.0);
  float soak = 1.6 * (1.0 - 0.35 * e.y);         // deep, even ink .. a shallow wash
  float ra = r * (1.0 + 0.16 * e.x), rb = r * 0.9 * (1.0 - 0.16 * e.x);
  float a = sphere(uv, dir * gap, dir, ra, soak);
  float b = sphere(uv, -dir * gap, -dir, rb, soak);
  float ink = clamp(a + b, 0.0, 1.0);
  vec3 paper = iColC * (0.62 - 0.06 * uv.y);
  vec3 col = mix(paper, iColB, smoothstep(0.0, 0.55, ink));
  col = mix(col, iColA, smoothstep(0.45, 1.0, ink));
  col += (grain(fc) - 0.5) * 0.025;
  o = vec4(col, 1.0);
}
