// Ember: one soft flame-shaped glow rising from the bottom of the wall, like a candle seen through
// frosted glass. It leans and breathes very slowly; the bass feeds it; the room around it is lit.
// Over tens of minutes the fire changes: tall and slender or low and broad, standing straight or
// leaning far, and now and then a second smaller flame parts from it and merges back.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
vec2 flame(vec2 uv, float x0, float lean, float h, float w){   // (body, core)
  float x = uv.x - x0 - lean * uv.y;
  float body = exp(-pow(x / (w * (1.0 - uv.y / (h * 1.25))), 2.0)) * smoothstep(h, 0.05, uv.y) * smoothstep(-0.02, 0.1, uv.y);
  float core = exp(-pow(x / (w * 0.3), 2.0)) * smoothstep(h * 0.55, 0.08, uv.y) * smoothstep(0.0, 0.12, uv.y);
  return vec2(body, core);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - vec2(0.5 * iResolution.x, 0.0)) / iResolution.y;
  float t = iTime * 0.03;
  vec4 e = iEvolve;
  float lean = (0.08 + 0.07 * e.z) * sin(t) + 0.04 * (noise(vec2(t * 0.7, 1.0)) - 0.5) + 0.06 * e.z;
  float h = 0.84 + 0.1 * e.y + 0.1 * iBreath + 0.04 * sin(t * 1.7);
  float w = 0.21 + 0.05 * e.x - 0.03 * e.y;                // slender .. broad
  float part = smoothstep(0.1, 0.8, e.w);                  // a second flame parting from the first
  float off = 0.16 * part;
  vec2 f1 = flame(uv, -off * 0.4, lean, h, w);
  vec2 f2 = flame(uv, off, lean * 0.8, h * (0.55 + 0.1 * e.x), w * 0.7) * part;
  float body = max(f1.x, f2.x), core = max(f1.y, f2.y);
  float flick = 0.92 + 0.08 * noise(vec2(uv.y * 4.0 - t * 2.0, t));
  vec3 col = iColA * 0.7;
  col += iColB * 0.45 * exp(-length(vec2(uv.x * 0.8, uv.y - 0.3)) * 2.2);   // the lit room
  col = mix(col, iColB, body * flick);
  col = mix(col, iColC, core * flick);
  col += (hash(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
