// Ink orbs: two soft spheres of ink that touch at a single point, darkest where they meet and
// fading outward into the paper; they drift a hair apart and together with the bass.
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(127.1, 311.7))) * 43758.5453); }
float sphere(vec2 p, vec2 pole, vec2 dir, float r){
  vec2 c = pole + dir * r;                       // the circle sits on its pole
  float inside = smoothstep(r * 1.05, r * 0.75, length(p - c));
  float k = clamp(length(p - pole) / (2.0 * r), 0.0, 1.0);
  return inside * pow(1.0 - k, 1.6);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02;
  float gap = 0.006 + 0.018 * iBreath;
  float r = 0.26 + 0.006 * sin(t * 2.0);
  float a = sphere(uv, vec2(0.0, gap), vec2(0.0, 1.0), r);
  float b = sphere(uv, vec2(0.0, -gap), vec2(0.0, -1.0), r * 0.9);
  float ink = clamp(a + b, 0.0, 1.0);
  vec3 paper = iColC * (0.62 - 0.06 * uv.y);
  vec3 col = mix(paper, iColB, smoothstep(0.0, 0.55, ink));
  col = mix(col, iColA, smoothstep(0.45, 1.0, ink));
  col += (grain(fc) - 0.5) * 0.025;
  o = vec4(col, 1.0);
}
