// Dot ring: a wide ring of halftone dots around an empty dark centre, the dots growing toward the
// ring's middle and fading at both edges. The colour runs round the ring - magenta, orange, violet -
// and the whole ring turns at the pace of a clock hand. It swells a little with the bass.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  float t = iTime * 0.015 + iClock * 0.26;
  float r = length(uv), a = atan(uv.y, uv.x);
  float wob = 0.03 * sin(a * 3.0 + t * 3.0) + 0.02 * sin(a * 5.0 - t * 2.0);
  float mid = 0.3 + wob + 0.01 * iBreath;
  float band = exp(-pow((r - mid) / 0.12, 2.0));
  vec2 c = fract(fc / 4.0) - 0.5;
  float s = clamp(band * 1.05, 0.0, 1.0);
  float dot_ = smoothstep(0.5 * s + 0.06, 0.5 * s - 0.06, length(c));
  float h = fract((a + t) / 6.2832);
  vec3 col = h < 0.33 ? mix(iColA, iColB, h * 3.0) : h < 0.66 ? mix(iColB, iColC, h * 3.0 - 1.0) : mix(iColC, iColA, h * 3.0 - 2.0);
  o = vec4(col * dot_ * (0.5 + 0.6 * band), 1.0);
}
