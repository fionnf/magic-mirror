// Strata: horizontal bands of colour like sediment or a sunset seen through slats, drifting
// sideways at different speeds, each band its own tint between shadow and highlight.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
float hashv(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.015;
  float n = 14.0;
  float yb = uv.y * n;
  float i = floor(yb), f = fract(yb);
  float wobble = 0.04 * sin(uv.x * 6.0 + t * (1.0 + hash(i)) * 2.0 + i);
  f = fract(yb + wobble);
  float shade = hash(i * 1.7) * 0.6 + 0.3 * sin(i * 0.7 + t * 0.5 * (0.5 + hash(i * 3.3)));
  float warm = smoothstep(0.0, 1.0, (i + 0.5) / n);
  vec3 tone = mix(mix(iColA, iColB, warm), iColC, clamp(shade, 0.0, 1.0) * (0.35 + 0.5 * warm));
  float edge = smoothstep(0.0, 0.08, f) * smoothstep(1.0, 0.92, f);
  vec3 col = tone * (0.75 + 0.25 * edge);
  float grain = hashv(vec2(floor(fc.x * 0.5), i)) * 0.08;
  col *= 1.0 - grain;
  col *= 1.0 - 0.3 * pow(abs(uv.x - 0.5) * 2.0, 2.0);
  o = vec4(col, 1.0);
}
