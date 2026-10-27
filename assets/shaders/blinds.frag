// Blinds: late light through a venetian blind onto a wall - soft bars of warm light, blurred
// at the edges, that slide down the wall as the hour passes (iClock). The bass warms them.
// Over tens of minutes (iEvolve) the blind changes: fewer, wider slats or many fine ones, the
// angle of the light, the blur of the edges, and the window widening until a mullion's shadow
// splits the light in two.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  vec4 e = iEvolve;
  float t = iTime * 0.006;
  float slide = fract(iClock / 3.0) * 0.4;                        // the bars travel over three hours
  float tilt = 0.18 + 0.06 * sin(t) + 0.2 * e.y;
  float y = uv.y + uv.x * tilt + slide;
  float freq = 28.0 + 9.0 * e.x;                                  // 19 .. 37: wide slats .. fine ones
  float bar = 0.5 + 0.5 * sin(y * freq);
  float soft = clamp(0.25 + 0.15 * sin(t * 1.7) + 0.12 * e.z, 0.06, 0.48);
  float light = smoothstep(0.5 - soft, 0.5 + soft, bar);
  float wide = 0.55 + 0.12 * e.w;                                 // the window grows and shrinks
  float window = smoothstep(wide, wide - 0.4, abs(uv.x + 0.1 * sin(t))) * smoothstep(0.55 + 0.08 * e.w, 0.2, abs(uv.y));
  float mull = smoothstep(0.2, 0.7, e.w);                         // a mullion's shadow, only when wide
  window *= 1.0 - mull * 0.85 * smoothstep(0.035, 0.01, abs(uv.x + 0.1 * sin(t) - 0.02 * e.y));
  vec3 warm = mix(iColB, iColC, 0.5 + 0.2 * iBreath);
  vec3 col = iColA * 0.6;
  col = mix(col, warm, light * window * 0.85);
  col += iColB * window * 0.12;
  col += (hash(fc) - 0.5) * 0.03;
  o = vec4(col, 1.0);
}
