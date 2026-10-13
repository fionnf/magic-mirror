// Halftone wave: a big sheet of dots folding slowly through space, dot size following the fold, a
// dark hollow where the sheet turns away. Violet at the top, blue through the middle, green where it
// comes towards you. The bass deepens the fold; through the day the hollow drifts across the wall.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02 + iClock * 0.21;
  vec2 q = uv * 2.2;
  float fold = sin(q.x * 1.3 + sin(q.y * 1.1 + t) * 1.6 + t * 0.7) + 0.6 * sin(q.y * 1.9 - t * 0.6 + q.x * 0.8);
  vec2 hole = vec2(0.18 * sin(t * 0.8), 0.12 * cos(t * 0.6)) - vec2(0.05, 0.0);
  float hollow = smoothstep(0.05, 0.42, length((uv - hole) * vec2(1.0, 1.3)));
  float sheet = smoothstep(0.95, 0.35, abs(uv.x + 0.25 * uv.y - 0.1 * fold) * 1.05);   // the sheet's extent
  float s = clamp((0.55 + 0.35 * fold * (1.0 + 0.3 * iBreath)) * hollow * sheet, 0.0, 1.0);
  vec2 g = fc / 4.0;                                      // a dot every 4 LEDs
  vec2 c = fract(g) - 0.5;
  float dot_ = smoothstep(0.5 * s + 0.06, 0.5 * s - 0.06, length(c));
  float k = clamp(0.5 - uv.y * 0.9 + 0.25 * uv.x + 0.15 * fold, 0.0, 1.0);   // violet -> blue -> green
  vec3 col = k < 0.5 ? mix(iColA, iColB, k * 2.0) : mix(iColB, iColC, k * 2.0 - 1.0);
  o = vec4(col * dot_ * (0.55 + 0.6 * s), 1.0);
}
