// Moon path: a small moon over still water and the long broken road of its light on the surface.
// The moon climbs with the evening (iClock); the bass lifts a slow swell through the reflection.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02;
  float horizon = -0.05;
  float up = 0.5 + 0.5 * sin((iClock - 15.0) / 24.0 * 6.2832);        // highest around 3 am
  vec2 m = vec2(0.18 * sin(t * 0.07), horizon + 0.12 + 0.3 * up);
  float r = 0.055 + 0.006 * iBreath;
  float d = length(uv - m);
  vec3 col = mix(iColA * 0.9, iColA * 0.45, smoothstep(horizon, 0.6, uv.y));
  col += iColB * 0.35 * exp(-d * d * 60.0);                              // sky glow
  col = mix(col, iColC, smoothstep(r + 0.004, r - 0.004, d));
  if (uv.y < horizon) {
    float depth = horizon - uv.y;
    float sw = 0.02 + 0.02 * iBreath;
    float wave = noise(vec2(uv.x * 14.0 + t * 0.5, depth * 28.0 - t * 0.9)) * 0.7 + 0.3 * noise(vec2(uv.x * 30.0 - t * 0.3, depth * 50.0 + t));
    float lane = exp(-pow((uv.x - m.x) / (0.04 + depth * 0.5), 2.0));
    float glint = smoothstep(0.5 - sw, 0.8, wave) * lane;
    col = mix(col, iColB, 0.35 * glint * (1.0 - depth * 0.8));
    col = mix(col, iColC, 0.6 * glint * glint * exp(-depth * 3.0));
    col = mix(col, iColA * 0.6, smoothstep(0.0, 0.01, depth) * 0.25);
  }
  col += (hash(fc) - 0.5) * 0.015;
  o = vec4(col, 1.0);
}
