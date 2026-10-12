// Paper lantern: one warm disc of light behind paper, its folds faintly visible, the wall around it
// falling into dark. It sways very slowly; the bass makes the paper glow a little from within.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.012;
  vec2 c = vec2(0.03 * sin(t), 0.06 + 0.015 * sin(t * 0.7 + 1.0));
  vec2 p = uv - c;
  float d = length(p * vec2(1.0, 0.86));
  float R = 0.3;
  float folds = 0.5 + 0.5 * cos(atan(p.y, p.x) * 14.0 + 0.6 * sin(t * 2.0));
  float inside = smoothstep(R, R - 0.012, d);
  float shade = 1.0 - smoothstep(0.0, R, d) * 0.55;
  float within = 0.9 + 0.25 * iBreath;
  vec3 paper = mix(iColB, iColC, shade * within) * (0.95 + 0.05 * folds * smoothstep(0.3, 1.0, d / R));
  float spill = exp(-max(d - R, 0.0) * 5.5) * 0.55;
  vec3 col = iColA * 0.7 + iColB * spill;
  col = mix(col, paper, inside);
  float cord = smoothstep(0.006, 0.0, abs(p.x)) * smoothstep(R * 0.86, R * 0.86 + 0.3, p.y) * step(p.y, 0.6);
  col = mix(col, iColA * 0.5, cord * 0.8);
  col += (hash(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
