// Line fan: hundreds of fine vertical lines rising from the bottom of the wall to different heights,
// their tops tracing a long soft wave; deep rose at the root fading through pink to violet at the
// tips. The wave rolls slowly sideways and rises a little with the bass; higher in the evening.
// Over tens of minutes the skyline changes: one long swell or several crests, a gentle line or
// steep peaks, a valley opening in the middle and closing, the light reaching deep or staying high.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.03;
  vec4 e = iEvolve;
  float lineX = fract(fc.x / 3.0);
  float line = smoothstep(0.5, 0.15, abs(lineX - 0.5));
  float evening = 0.08 * sin((iClock - 6.0) * 0.26);
  float freq = 4.0 + 2.0 * e.y;                            // one swell .. several crests
  float amp = 0.15 + 0.07 * e.x;
  float valley = 0.22 * smoothstep(0.0, 0.8, e.w) * exp(-pow((uv.x - 0.5 - 0.15 * sin(t * 0.3)) / 0.16, 2.0));
  float top = 0.55 + evening + amp * sin(uv.x * freq + t) + 0.06 * sin(uv.x * 11.0 - t * 1.4) + 0.03 * iBreath - valley;
  float depth = 0.6 + 0.2 * e.z;                           // how far down the light reaches
  float body = smoothstep(top, top - 0.25, uv.y) * smoothstep(top - depth, top - depth * 0.35, uv.y);
  float k = clamp((top - uv.y) / 0.5, 0.0, 1.0);
  vec3 col = mix(iColC, mix(iColB, iColA, k), k) * line * body;
  col += iColA * 0.08 * smoothstep(top, 0.0, uv.y);
  o = vec4(col, 1.0);
}
