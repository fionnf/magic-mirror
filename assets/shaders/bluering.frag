// Blue ring: a soft, out-of-focus ring of light - cyan and azure, with a thin warm fringe on its
// outer edge like chromatic aberration - floating in the dark. It drifts in and out of focus very
// slowly; the bass sharpens it a touch. Over the day it slides from one side of the wall to the other.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  uv.x -= 0.12 * sin(iClock * 0.26);
  float r = length(uv), a = atan(uv.y, uv.x);
  float R = 0.28 + 0.01 * sin(a * 2.0 + iTime * 0.02);
  float blur = 0.045 + 0.03 * sin(iTime * 0.017) - 0.012 * iBreath;
  float ring = exp(-pow((r - R) / blur, 2.0));
  float outer = exp(-pow((r - R - blur * 1.1) / (blur * 0.7), 2.0));
  float inner = exp(-pow((r - R + blur * 0.9) / (blur * 0.8), 2.0));
  float side = 0.6 + 0.4 * cos(a - 0.8);
  vec3 col = iColB * ring * side + iColC * inner * 0.6 * side + iColA * outer * 0.5;
  o = vec4(col, 1.0);
}
