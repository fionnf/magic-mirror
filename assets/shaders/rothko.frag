// Two fields: a painting of two soft colour fields meeting at a blurred edge that breathes over
// minutes, the way a Rothko seems to. Nothing else. The key tints the upper field.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.01;
  float edge = 0.48 + 0.05 * sin(t) + 0.03 * sin(t * 2.7 + 1.0) + 0.03 * (noise(vec2(uv.x * 3.0, t)) - 0.5);
  float soft = 0.06 + 0.04 * iBreath;
  float k = smoothstep(edge - soft, edge + soft, uv.y);
  vec3 upper = mix(iColC, iColB, 0.35 + 0.25 * cos(iKey * 6.2832));
  vec3 lower = mix(iColB, iColA, 0.55);
  vec3 col = mix(lower, upper, k);
  float cloud = noise(uv * 4.0 + vec2(t * 0.3, -t * 0.2)) * 0.5 + noise(uv * 9.0 - t * 0.4) * 0.25;
  col *= 0.86 + 0.2 * cloud;
  float frame = smoothstep(0.0, 0.07, uv.x) * smoothstep(1.0, 0.93, uv.x) * smoothstep(0.0, 0.07, uv.y) * smoothstep(1.0, 0.93, uv.y);
  col = mix(iColA * 0.55, col, 0.35 + 0.65 * frame);
  col += (hash(fc) - 0.5) * 0.025;
  o = vec4(col, 1.0);
}
