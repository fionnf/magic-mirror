// Blue ring: a soft, out-of-focus ring of light - cyan and azure, with a thin warm fringe on its
// outer edge like chromatic aberration - floating in the dark. It drifts in and out of focus very
// slowly; the bass sharpens it a touch. Over the day it slides from one side of the wall to the other.
// Over tens of minutes it stretches into an ellipse and back, thickens and thins, its edge waves
// with two to five soft swells, and a second, fainter ring drifts out of it and melts back in.
float ringAt(vec2 uv, float R, float blur, float stretch, float lobes, float t, out float a){
  vec2 q = uv * vec2(1.0 - stretch, 1.0 + stretch);
  float r = length(q); a = atan(q.y, q.x);
  float f = floor(lobes);                               // whole numbers of swells, blended: no seam
  float Rw = R + 0.012 * mix(sin(a * f + t), sin(a * (f + 1.0) - t * 0.7), smoothstep(0.0, 1.0, lobes - f));
  return r - Rw;
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  uv.x -= 0.12 * sin(iClock * 0.26);
  vec4 e = iEvolve;
  float t = iTime * 0.02;
  float blur = (0.045 + 0.03 * sin(iTime * 0.017) - 0.012 * iBreath) * (1.0 + 0.35 * e.y);
  float a;
  float d = ringAt(uv, 0.28, blur, 0.12 * e.x, 3.5 + 1.5 * e.z, t, a);
  float ring = exp(-pow(d / blur, 2.0));
  float outer = exp(-pow((d - blur * 1.1) / (blur * 0.7), 2.0));
  float inner = exp(-pow((d + blur * 0.9) / (blur * 0.8), 2.0));
  float side = 0.6 + 0.4 * cos(a - 0.8);
  vec3 col = iColB * ring * side + iColC * inner * 0.6 * side + iColA * outer * 0.5;
  float twin = smoothstep(0.0, 0.8, e.w);               // a second ring, part of the cycle
  if (twin > 0.0) {
    vec2 off = 0.13 * twin * vec2(cos(t * 0.7 + 2.0 * e.x), sin(t * 0.7 + 2.0 * e.x));
    float a2, d2 = ringAt(uv - off, 0.28 - 0.1 * twin, blur * 1.3, -0.08 * e.x, 3.0, -t, a2);
    col += (iColB * 0.55 + iColC * 0.15) * twin * exp(-pow(d2 / (blur * 1.3), 2.0)) * (0.6 + 0.4 * cos(a2 - 0.8));
  }
  o = vec4(col, 1.0);
}
