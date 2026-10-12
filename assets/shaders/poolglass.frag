// Pool light: the net of light that sunlight makes on the floor of a pool, slowed to a crawl, in
// one hue family. The bass deepens the water; the key leans the tint.
vec2 hash2(vec2 p){ return fract(sin(vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)))) * 43758.5453); }
float caustic(vec2 p, float t){
  vec2 i = floor(p), f = fract(p);
  float m = 1.0, m2 = 1.0;
  for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++) {
    vec2 g = vec2(float(x), float(y));
    vec2 o = hash2(i + g);
    o = 0.5 + 0.4 * sin(t + 6.2832 * o);
    float d = length(g + o - f);
    if (d < m) { m2 = m; m = d; } else if (d < m2) { m2 = d; }
  }
  return m2 - m;
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.05;
  float c1 = caustic(uv * 3.2 + vec2(t * 0.1, 0.0), t);
  float c2 = caustic(uv * 5.1 - vec2(0.0, t * 0.07), t * 1.3 + 2.0);
  float net = smoothstep(0.12, 0.0, c1) * 0.8 + smoothstep(0.09, 0.0, c2) * 0.5;
  float depth = 0.6 + 0.3 * iBreath;
  vec3 water = mix(iColA, iColB, 0.45 + 0.15 * cos(iKey * 6.2832));
  vec3 col = water * (0.7 + 0.3 * (1.0 - depth));
  col = mix(col, iColC, net * 0.55 * (1.0 - 0.3 * depth));
  col *= 1.0 - 0.4 * dot(uv, uv);
  o = vec4(col, 1.0);
}
