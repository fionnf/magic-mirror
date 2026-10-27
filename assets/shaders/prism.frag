// Prism: one line of white light falling from the top of the wall that splits into a wide, soft
// spectral fan as it falls; the fan opens a little with the bass and drifts with the key.
// Over tens of minutes the light changes: a narrow fan or one spread across the whole wall, the
// colours in three bands or melted together, the fan tilting, and a second fainter beam splitting
// off beside it and fading away.
vec3 beam(vec2 uv, float x0, float spread, float tilt, float sharp, float t){
  float y = 1.0 - uv.y;                                    // 0 at the top
  float x = uv.x - x0 - tilt * y * y;
  float s = y * spread;                                    // widens towards the bottom
  vec3 col = vec3(0.0);
  for (int i = 0; i < 5; i++){
    float fi = float(i) / 4.0;                              // across the fan: shadow tone .. highlight
    float off = (fi - 0.5) * s * 1.1 + 0.015 * sin(t + iKey * 6.283 + fi * 3.0);
    float band = exp(-pow((x - off) / max(s * sharp, 0.004), 2.0)) * smoothstep(0.02, 0.35, y);
    vec3 c = fi < 0.5 ? mix(iColA, iColB, fi * 2.0) : mix(iColB, iColC, fi * 2.0 - 1.0);
    col += c * band * 0.55;
  }
  float line = exp(-pow(x / 0.006, 2.0)) * smoothstep(0.7, 0.0, y);
  return col + mix(iColC, vec3(1.0), 0.5) * line * 0.9;
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.02;
  vec4 e = iEvolve;
  float spread = 0.42 + 0.18 * e.x + 0.06 * iBreath;
  float sharp = 0.24 + 0.1 * e.y;                          // banded .. melted together
  float tilt = 0.1 * e.z;
  vec3 col = beam(uv, 0.5 + 0.01 * sin(t), spread, tilt, sharp, t);
  float two = smoothstep(0.1, 0.85, e.w);                  // a second, fainter beam
  col += beam(uv, 0.5 + 0.22 * two, spread * 0.6, -tilt, sharp, t + 2.0) * 0.55 * two;
  col += iColB * 0.06 * smoothstep(1.0, 0.0, uv.y);         // a little light in the room
  o = vec4(min(col, vec3(1.0)), 1.0);
}
