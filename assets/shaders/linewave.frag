// Line wave: forty fine parallel lines laid side by side like a ribbon of contour, folding into a
// slow wave whose edge ripples. The colour runs across the ribbon from green through blue to violet.
// The bass pushes the wave; the ribbon's fold travels down the wall over the day.
// Over tens of minutes the ribbon changes: narrow or wide, a gentle bend or a deep fold, the lines
// close or open, and now and then it parts into two strands down the middle and closes again.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.006 + iClock * 0.25;
  vec4 e = iEvolve;
  float y = uv.y;
  float width = 0.6 + 0.1 * e.x;
  float bend = 1.0 + 0.35 * e.y;
  float shape = 0.5 + 0.18 * bend * sin(y * 5.0 + t) + 0.08 * sin(y * (11.0 + 3.0 * e.z) - t * 1.3) + 0.006 * iBreath;
  float x = (uv.x - shape + 0.53 * width) / width;         // 0..1 across the ribbon
  float inside = step(0.0, x) * step(x, 1.0);
  float lines = 22.0 + 3.0 * e.z;  // about one line every 3 LEDs or more, so they never shimmer
  float f = fract(x * lines);
  float w = smoothstep(0.42, 0.18, abs(f - 0.5));
  float part = smoothstep(0.1, 0.8, e.w) * (0.5 + 0.5 * sin(y * 3.0 - t * 0.7));   // a parting down the middle
  float half_ = 0.13 * part;
  float gap = (1.0 - smoothstep(half_, half_ + 0.03, abs(x - 0.5))) * smoothstep(0.02, 0.2, part);
  float k = clamp(x + 0.15 * sin(y * 3.0 + t), 0.0, 1.0);
  vec3 col = k < 0.5 ? mix(iColA, iColB, k * 2.0) : mix(iColB, iColC, k * 2.0 - 1.0);
  float fade = smoothstep(0.0, 0.08, x) * smoothstep(1.0, 0.85, x);
  o = vec4(col * w * inside * fade * (1.0 - gap) * 0.95, 1.0);
}
