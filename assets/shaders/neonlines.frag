// Neon lines: three thin rods of light in a dark room, each casting a soft fan of coloured light
// to one side - one turns its angle very slowly with the key; the bass widens their glow.
float rod(vec2 p, vec2 a, vec2 b){ vec2 pa = p - a, ba = b - a; float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0); return length(pa - ba * h); }
vec3 fan(vec2 p, vec2 a, vec2 b, vec3 hot, vec3 warm, float w){
  vec2 ba = normalize(b - a); vec2 n = vec2(-ba.y, ba.x);
  float d = rod(p, a, b);
  float side = dot(p - a, n);                    // light falls to one side only
  float along = clamp(dot(p - a, ba) / length(b - a), 0.0, 1.0);
  float spill = smoothstep(0.0, 0.02, side) * exp(-side * (3.2 - w)) * (0.4 + 0.6 * along) * step(0.0, dot(p - a, ba)) * step(dot(p - a, ba), length(b - a));
  float core = exp(-pow(d / (0.004 + 0.002 * w), 2.0));
  return warm * spill * 0.55 + hot * core;
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.01;
  float w = iBreath;
  float k = 0.25 * sin(t + iKey * 6.283);
  vec3 col = iColA * 0.6;
  col += fan(uv, vec2(-0.6, -0.02), vec2(0.0, -0.02), iColC, iColB, w);
  col += fan(uv, vec2(0.0, 0.08), vec2(0.55, 0.55 + k * 0.2), iColC, iColB, w);
  col += fan(uv, vec2(-0.05, -0.55), vec2(-0.05, -0.15), iColC, iColB, w);
  o = vec4(min(col, vec3(1.0)), 1.0);
}
