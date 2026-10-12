// Ink drop: one orb of ink on soft paper, its edge bleeding into the fibres. The paper's warmth
// and the ink's depth are the only two colours; the orb drifts and swells with the breath.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.01;
  vec2 c = vec2(0.05 * sin(t), 0.04 * cos(t * 0.7));
  vec2 p = uv - c;
  float a = atan(p.y, p.x);
  float R = 0.27 + 0.02 * iBreath + 0.012 * sin(a * 3.0 + t * 2.0) + 0.02 * (noise(vec2(a * 1.5, t)) - 0.5);
  float d = length(p) - R;
  float fibre = noise(fc * 0.35) * 0.6 + noise(fc * 0.9) * 0.4;
  float bleed = smoothstep(0.05 + 0.03 * fibre, -0.01, d);
  float ink = smoothstep(0.012, -0.012, d);
  vec3 paper = mix(iColC, iColB, 0.22 + 0.12 * fibre) * 0.72;
  paper *= 1.0 - 0.25 * length(uv);
  vec3 wet = mix(iColB, iColA, 0.6 + 0.4 * smoothstep(0.0, -0.2, d));
  vec3 col = mix(paper, mix(paper, wet, 0.45), bleed * (0.6 + 0.4 * fibre));
  col = mix(col, wet, ink);
  col = mix(col, iColB * 0.9, ink * smoothstep(-0.03, 0.0, d) * 0.5);   // the dried rim, darker
  col += (hash(fc) - 0.5) * 0.03;
  o = vec4(col, 1.0);
}
