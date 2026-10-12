// Cut curves: flat mid-century paper shapes - a big swept curve and a counter-curve in two tones
// on a third, no gradients, the edges just soft enough for the LEDs. They slide past each other
// over minutes; each song re-seeds the composition a little.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.015;
  float s = iSong * 3.0;
  float e = 1.6 / iResolution.y;
  vec3 col = iColB;
  // a large disc, cut off by a sweeping curve
  vec2 c1 = vec2(0.15 + 0.06 * sin(t), -0.1 + 0.04 * cos(t * 0.7)) + 0.05 * (hash(s) - 0.5);
  float d1 = length(uv - c1) - 0.42;
  float cut = uv.y - (0.08 * sin(uv.x * 3.0 + t + s) - 0.05);
  col = mix(col, iColC, smoothstep(e, -e, max(d1, cut)));
  // a counter-curve of the dark tone, like a wave or a hill
  float hill = uv.y + 0.28 - 0.18 * sin(uv.x * 2.2 - t * 1.3 + s * 2.0) - 0.05 * sin(uv.x * 5.0 + t);
  col = mix(col, iColA, smoothstep(e, -e, hill));
  // one small full disc of the light tone, a sun or a dot
  vec2 c2 = vec2(-0.3 + 0.1 * sin(t * 0.5 + s), 0.3);
  col = mix(col, iColC, smoothstep(e, -e, length(uv - c2) - 0.07));
  o = vec4(col * 0.88, 1.0);
}
