// Prism: one thin vertical line of white light on black that splits into a soft spectral fan
// as it falls; the fan opens a little with the bass and drifts with the key.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.02;
  float x = uv.x - 0.5 - 0.01 * sin(t);
  float spread = (1.0 - uv.y) * (0.16 + 0.04 * iBreath);           // widens towards the bottom
  float line = exp(-pow(x / 0.004, 2.0)) * (0.5 + 0.5 * uv.y + 0.4 * (1.0 - uv.y));
  vec3 col = vec3(0.0);
  for (int i = 0; i < 3; i++){
    float fi = float(i) - 1.0;
    float off = fi * spread * 0.35 + 0.02 * sin(t + iKey * 6.283 + fi);
    float band = exp(-pow((x - off) / max(spread * 0.45, 0.004), 2.0)) * smoothstep(0.95, 0.2, uv.y);
    vec3 c = i == 0 ? iColA : (i == 1 ? iColB : iColC);
    col += c * band * 0.7;
  }
  col += mix(iColC, vec3(1.0), 0.5) * line * 0.9;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
