// Aura: a soft rounded field of light, dark at one corner and glowing at the other - like light
// through frosted glass. The glow breathes with the bass and leans with the key.
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(12.9898, 78.233))) * 43758.5453); }
float sdRound(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.03;
  float d = sdRound(uv, vec2(0.30, 0.38), 0.16);
  float card = 1.0 - smoothstep(-0.02, 0.06, d);
  vec2 hot = vec2(0.06 * sin(t + iKey * 6.283), -0.22 + 0.04 * cos(t * 0.7)) ;
  float g = exp(-dot(uv - hot, uv - hot) * (5.5 - 1.5 * iBreath));
  float shade = smoothstep(0.55, -0.35, uv.y + 0.25 * uv.x);
  vec3 col = mix(iColA, iColB, clamp(g * 1.2, 0.0, 1.0));
  col = mix(col, iColC, smoothstep(0.35, 1.0, g) * 0.8);
  col *= mix(0.55, 1.0, 1.0 - shade * 0.6);
  vec3 room = iColA * 0.35;
  col = mix(room, col, card) + iColB * 0.05 * exp(-max(d, 0.0) * 14.0);
  col += (grain(fc) - 0.5) * 0.025;
  o = vec4(col, 1.0);
}
