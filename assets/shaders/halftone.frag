// Halftone wave: a field of dots on black whose size follows a slow, folding surface - like a
// sheet of light points bending in space; the fold deepens with the bass, the gradient runs
// through the palette.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.025;
  vec2 q = uv * 1.6;
  float h = sin(q.x * 2.1 + sin(q.y * 1.7 + t) * 1.4 + t) * 0.5 + sin(q.y * 2.6 - t * 0.8 + q.x) * 0.35;
  float r = length(uv);
  float body = smoothstep(0.62, 0.25, r + 0.08 * h);                // a soft overall form
  float s = clamp(0.5 + 0.5 * h * (1.0 + 0.4 * iBreath), 0.0, 1.0) * body;
  vec2 g = fc / 4.0;                                                 // a dot every 4 pixels
  vec2 cell = fract(g) - 0.5;
  float d = smoothstep(0.5 * s + 0.05, 0.5 * s - 0.08, length(cell));
  vec3 c = mix(iColB, iColC, clamp(uv.y + 0.5 + 0.3 * h, 0.0, 1.0));
  c = mix(iColA * 2.0, c, smoothstep(0.0, 0.5, s));
  o = vec4(c * d, 1.0);
}
