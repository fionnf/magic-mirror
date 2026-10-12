// Burning rim: a dark disc, and only its edge alight - a thin ring of fire with a soft corona
// breathing outward. Rising tension makes the fire reach further; the key leans its colour.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02;
  float r = length(uv), a = atan(uv.y, uv.x);
  float R = 0.3;
  float flame = noise(vec2(a * 2.0 + t, t * 0.7)) * 0.6 + noise(vec2(a * 5.0 - t * 1.3, 3.0)) * 0.4;
  float reach = 0.09 + 0.07 * iTension + 0.08 * flame;
  float out_ = max(r - R, 0.0);
  float corona = exp(-out_ / reach);
  float rim = exp(-pow(out_ / 0.012, 2.0));
  vec3 fire = mix(iColB, iColC, 0.4 + 0.3 * cos(iKey * 6.2832));
  vec3 col = iColA * 0.55;
  col += fire * corona * 0.55 * (0.7 + 0.3 * flame);
  col += iColC * rim * 0.9;
  col = mix(col, iColA * 0.35, smoothstep(0.003, -0.003, r - R));
  col += (hash(fc) - 0.5) * 0.025;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
