// Frosted: light through frosted glass - one soft glowing core in a blurred field, nothing sharp
// anywhere, a fine grain over all of it. The core drifts over minutes; the bass warms it.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.008;
  vec2 c = vec2(0.12 * sin(t * 1.3), 0.08 * cos(t * 0.9) + 0.04);
  vec2 p = uv - c;
  float wobble = noise(uv * 2.5 + t) - 0.5;
  float d = length(p * vec2(0.85, 1.0)) + 0.08 * wobble;
  float core = exp(-d * d * (9.0 - 2.0 * iBreath));
  float halo = exp(-d * 3.2);
  vec3 col = mix(iColA * 0.6, iColB, halo * 0.6);
  col = mix(col, iColC, core * 0.75);
  float veil = noise(uv * 6.0 - t * 0.5) * 0.5 + noise(uv * 13.0 + t) * 0.25;
  col *= 0.9 + 0.12 * veil;
  col += (hash(fc + floor(iTime * 0.1)) - 0.5) * 0.07;
  o = vec4(col, 1.0);
}
