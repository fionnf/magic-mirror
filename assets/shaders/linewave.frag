// Line wave: forty fine parallel lines laid side by side like a ribbon of contour, folding into a
// slow wave whose edge ripples. The colour runs across the ribbon from green through blue to violet.
// The bass pushes the wave; the ribbon's fold travels down the wall over the day.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.006 + iClock * 0.25;
  float y = uv.y;
  float shape = 0.5 + 0.18 * sin(y * 5.0 + t) + 0.08 * sin(y * 11.0 - t * 1.3) + 0.006 * iBreath;
  float x = (uv.x - shape + 0.32) / 0.6;                 // 0..1 across the ribbon
  float inside = step(0.0, x) * step(x, 1.0);
  float lines = 22.0;            // about one line every 3 LEDs, so they never shimmer
  float f = fract(x * lines);
  float w = smoothstep(0.42, 0.18, abs(f - 0.5));
  float k = clamp(x + 0.15 * sin(y * 3.0 + t), 0.0, 1.0);
  vec3 col = k < 0.5 ? mix(iColA, iColB, k * 2.0) : mix(iColB, iColC, k * 2.0 - 1.0);
  float fade = smoothstep(0.0, 0.08, x) * smoothstep(1.0, 0.85, x);
  o = vec4(col * w * inside * fade * 0.95, 1.0);
}
