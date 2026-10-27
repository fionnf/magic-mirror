// Dot ring: a wide ring of halftone dots around an empty dark centre, the dots growing toward the
// ring's middle and fading at both edges. The colour runs round the ring - magenta, orange, violet -
// and the whole ring turns at the pace of a clock hand. It swells a little with the bass.
// Over tens of minutes the ring's outline goes from nearly round to two to six soft lobes, the band
// widens and narrows, the dots grow fuller or sparer, and a thinner inner ring fills in and fades.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  vec4 e = iEvolve;
  float t = iTime * 0.015 + iClock * 0.26;
  float r = length(uv), a = atan(uv.y, uv.x);
  float k = 4.0 + 2.0 * e.z;                            // 2 .. 6 lobes, blended
  float lob = mix(sin(a * floor(k) + t * 3.0), sin(a * (floor(k) + 1.0) - t * 2.0), smoothstep(0.0, 1.0, fract(k)));
  float wob = (0.022 + 0.018 * (0.5 + 0.5 * e.y)) * lob + 0.015 * sin(a * 2.0 - t);
  float mid = 0.3 + wob + 0.01 * iBreath;
  float w = 0.12 * (1.0 + 0.3 * e.x);                   // band width
  float band = exp(-pow((r - mid) / w, 2.0));
  float inner = smoothstep(0.1, 0.8, e.w) * exp(-pow((r - mid * 0.52) / (w * 0.35), 2.0));
  band = max(band, inner * 0.85);
  vec2 c = fract(fc / 4.0) - 0.5;
  float s = clamp(band * (0.9 + 0.2 * e.y), 0.0, 1.0);  // fuller or sparer dots
  float dot_ = smoothstep(0.5 * s + 0.06, 0.5 * s - 0.06, length(c));
  float h = fract((a + t) / 6.2832);
  vec3 col = h < 0.33 ? mix(iColA, iColB, h * 3.0) : h < 0.66 ? mix(iColB, iColC, h * 3.0 - 1.0) : mix(iColC, iColA, h * 3.0 - 2.0);
  o = vec4(col * dot_ * (0.5 + 0.6 * band), 1.0);
}
