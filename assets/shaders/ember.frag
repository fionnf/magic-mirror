// Ember: one soft flame-shaped glow rising from the bottom of the wall, like a candle seen through
// frosted glass. It leans and breathes very slowly; the bass feeds it.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - vec2(0.5 * iResolution.x, 0.0)) / iResolution.y;
  float t = iTime * 0.03;
  float lean = 0.08 * sin(t) + 0.04 * (noise(vec2(t * 0.7, 1.0)) - 0.5);
  float x = uv.x - lean * uv.y;
  float h = 0.72 + 0.12 * iBreath + 0.04 * sin(t * 1.7);
  float body = exp(-pow(x / (0.17 * (1.0 - uv.y * 0.8)), 2.0)) * smoothstep(h, 0.05, uv.y) * smoothstep(-0.02, 0.1, uv.y);
  float core = exp(-pow(x / 0.05, 2.0)) * smoothstep(h * 0.55, 0.08, uv.y) * smoothstep(0.0, 0.12, uv.y);
  float flick = 0.92 + 0.08 * noise(vec2(uv.y * 4.0 - t * 2.0, t));
  vec3 col = iColA * 0.65;
  col += iColB * 0.35 * exp(-length(vec2(x, uv.y - 0.25)) * 3.5);
  col = mix(col, iColB, body * flick);
  col = mix(col, iColC, core * flick);
  col += (hash(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
