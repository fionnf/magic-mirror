// Blinds: late light through a venetian blind onto a wall - soft bars of warm light, blurred
// at the edges, that slide down the wall as the hour passes (iClock). The bass warms them.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.006;
  float slide = fract(iClock / 3.0) * 0.4;                        // the bars travel over three hours
  float tilt = 0.18 + 0.06 * sin(t);
  float y = uv.y + uv.x * tilt + slide;
  float bar = 0.5 + 0.5 * sin(y * 28.0);
  float soft = 0.25 + 0.15 * sin(t * 1.7);
  float light = smoothstep(0.5 - soft, 0.5 + soft, bar);
  float window = smoothstep(0.55, 0.15, abs(uv.x + 0.1 * sin(t))) * smoothstep(0.55, 0.2, abs(uv.y));
  vec3 warm = mix(iColB, iColC, 0.5 + 0.2 * iBreath);
  vec3 col = iColA * 0.6;
  col = mix(col, warm, light * window * 0.85);
  col += iColB * window * 0.12;
  col += (hash(fc) - 0.5) * 0.03;
  o = vec4(col, 1.0);
}
