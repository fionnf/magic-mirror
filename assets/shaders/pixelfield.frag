// Pixel field: a soft vertical gradient of big glowing squares - warm at the top, through yellow and
// green to blue at the bottom - each square a little blurred, like light behind a coarse diffuser.
// The bands drift very slowly and the whole gradient climbs the wall over the day.
vec3 ramp(float k){
  k = clamp(k, 0.0, 1.0);
  return k < 0.5 ? mix(iColA, iColB, k * 2.0) : mix(iColB, iColC, k * 2.0 - 1.0);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.02 + iClock * 0.1;
  float cell = 8.0;                                        // squares of 8 x 8 LEDs
  vec2 id = floor(fc / cell), f = fract(fc / cell) - 0.5;
  vec2 cuv = (id + 0.5) * cell / iResolution;
  float k = clamp(1.02 - cuv.y * 1.05 + 0.06 * sin(cuv.x * 5.0 + t * 2.0) + 0.1 * sin(t), 0.0, 1.0);
  float body = smoothstep(0.62, 0.15, abs(cuv.x - 0.5 - 0.05 * sin(cuv.y * 4.0 + t)) * 1.6);   // fades to the sides
  float sq = smoothstep(0.5, 0.3, max(abs(f.x), abs(f.y)));
  vec3 col = ramp(k) * body * (0.35 + 0.65 * sq) * (0.95 + 0.05 * iBreath);
  o = vec4(col, 1.0);
}
