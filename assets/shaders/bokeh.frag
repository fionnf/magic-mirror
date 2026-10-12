// Bokeh: a few large out-of-focus lights drifting in the dark, each a soft disc with a brighter
// rim, the way city lights look through a rainy window. The bass brings them closer.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.012;
  vec3 col = iColA * 0.6;
  for (int i = 0; i < 9; i++) {
    float fi = float(i);
    vec2 c = vec2(sin(t * (0.5 + 0.3 * hash(fi)) + fi * 2.0), cos(t * (0.4 + 0.3 * hash(fi + 9.0)) + fi)) * vec2(0.55, 0.42);
    float R = (0.07 + 0.07 * hash(fi + 3.0)) * (1.0 + 0.25 * iBreath);
    float d = length(uv - c);
    float disc = smoothstep(R, R - 0.02, d);
    float rim = smoothstep(R - 0.03, R - 0.012, d) * smoothstep(R, R - 0.008, d);
    vec3 tone = mix(iColB, iColC, hash(fi + 5.0));
    col += tone * (disc * 0.24 + rim * 0.3) * (0.6 + 0.4 * hash(fi + 7.0));
  }
  col *= 1.0 - 0.3 * dot(uv, uv);
  o = vec4(min(col, vec3(1.0)), 1.0);
}
