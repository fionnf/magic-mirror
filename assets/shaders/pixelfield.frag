// Pixel field: a soft vertical gradient of big glowing squares - warm at the top, through yellow and
// green to blue at the bottom - each square a little blurred, like light behind a coarse diffuser.
// The bands drift very slowly and the whole gradient climbs the wall over the day.
// Over tens of minutes (iEvolve) the squares grow and shrink (6 to 12 LEDs, one size melting into
// the next), the column of light narrows or opens to the edges, slow clouds of light move through
// it, and the bands of colour crowd together or spread out.
vec3 ramp(float k){
  k = clamp(k, 0.0, 1.0);
  return k < 0.5 ? mix(iColA, iColB, k * 2.0) : mix(iColB, iColC, k * 2.0 - 1.0);
}
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
vec3 field(vec2 fc, float cell, float t, vec4 e){
  vec2 id = floor(fc / cell), f = fract(fc / cell) - 0.5;
  vec2 cuv = (id + 0.5) * cell / iResolution;
  float cloud = noise(cuv * vec2(2.2, 1.6) + vec2(t * 0.6, -t * 0.4)) - 0.5;   // slow clouds of light
  float bands = 1.05 + 0.3 * e.z;                          // the colour bands crowd or spread
  float k = clamp(1.02 - cuv.y * bands + 0.06 * sin(cuv.x * 5.0 + t * 2.0) + 0.1 * sin(t) + 0.35 * cloud * (0.6 + 0.4 * e.y), 0.0, 1.0);
  float width = 1.6 - 0.55 * e.x;                          // narrow column .. open to the edges
  float body = smoothstep(0.62, 0.15, abs(cuv.x - 0.5 - 0.05 * sin(cuv.y * 4.0 + t)) * width);
  float sq = smoothstep(0.5, 0.3, max(abs(f.x), abs(f.y)));
  return ramp(k) * body * (0.35 + 0.65 * sq);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  vec4 e = iEvolve;
  float t = iTime * 0.02 + iClock * 0.1;
  float s = 9.0 + 3.0 * e.w;                               // 6 .. 12 LEDs, in steps of two
  float lo = 2.0 * floor(s * 0.5), a = smoothstep(0.3, 0.7, (s - lo) * 0.5);
  vec3 col = mix(field(fc, lo, t, e), field(fc, lo + 2.0, t, e), a);
  o = vec4(col * (0.95 + 0.05 * iBreath), 1.0);
}
