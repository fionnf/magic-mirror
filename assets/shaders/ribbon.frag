// Ribbon: one wide band of silk folding over itself in slow motion, lit from one side so each
// fold turns from the shadow tone to the highlight. Rising tension tightens the folds.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.03;
  vec3 col = iColA * 0.7;
  float acc = 0.0;
  for (int i = 0; i < 3; i++) {
    float fi = float(i);
    float ph = t * (0.6 + 0.2 * fi) + fi * 2.1;
    float y = 0.15 * sin(uv.x * (1.6 + 0.3 * fi + 0.4 * iTension) + ph) + 0.12 * sin(uv.x * 0.7 - ph * 0.6) + (fi - 1.0) * 0.05;
    float w = 0.09 + 0.03 * sin(uv.x * 2.3 + ph * 1.3);
    float d = abs(uv.y - y) - w;
    float band = smoothstep(0.004, -0.004, d);
    float slope = cos(uv.x * (1.6 + 0.3 * fi) + ph);
    float lit = 0.5 + 0.5 * slope;
    vec3 silk = mix(iColB, iColC, lit * lit * 0.9);
    silk *= 0.75 + 0.25 * smoothstep(-w, w, uv.y - y);
    col = mix(col, silk, band * (1.0 - acc * 0.35));
    acc = max(acc, band);
  }
  col *= 1.0 - 0.3 * dot(uv, uv);
  o = vec4(col, 1.0);
}
