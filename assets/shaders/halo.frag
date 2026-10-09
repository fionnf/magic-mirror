// Halo: a dark rounded form standing in front of a glowing wall, the light escaping around its
// edges; the halo swells a little with the bass.
float sdRound(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.015;
  vec2 p = uv - vec2(0.02 * sin(t), 0.0);
  float d = sdRound(p, vec2(0.22, 0.34), 0.07);
  float glow = exp(-max(d, 0.0) * (11.0 - 3.0 * iBreath));
  vec3 col = mix(iColA * 0.6, iColB, glow * 0.9);
  col = mix(col, iColC, exp(-max(d, 0.0) * 28.0) * 0.8);
  col = mix(col, iColA * 0.25, smoothstep(0.004, -0.004, d));
  col += (grain(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
