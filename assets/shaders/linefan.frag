// Line fan: hundreds of fine vertical lines rising from the bottom of the wall to different heights,
// their tops tracing a long soft wave; deep rose at the root fading through pink to violet at the
// tips. The wave rolls slowly sideways and rises a little with the bass; higher in the evening.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.03;
  float lineX = fract(fc.x / 3.0);
  float line = smoothstep(0.5, 0.15, abs(lineX - 0.5));
  float evening = 0.08 * sin((iClock - 6.0) * 0.26);
  float top = 0.55 + evening + 0.15 * sin(uv.x * 4.0 + t) + 0.06 * sin(uv.x * 11.0 - t * 1.4) + 0.03 * iBreath;
  float body = smoothstep(top, top - 0.25, uv.y) * smoothstep(top - 0.6, top - 0.2, uv.y);
  float k = clamp((top - uv.y) / 0.5, 0.0, 1.0);
  vec3 col = mix(iColC, mix(iColB, iColA, k), k) * line * body;
  col += iColA * 0.08 * smoothstep(top, 0.0, uv.y);
  o = vec4(col, 1.0);
}
