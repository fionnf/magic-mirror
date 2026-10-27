// Tide: soft horizontal bands breathing in and out, like light on a slow sea.
// Over tens of minutes (iEvolve) the bands come closer or spread out, lean a little, sharpen into
// lines or melt into a haze, and bright crests gather and fade.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  vec4 e = iEvolve;
  float t = iTime * 0.06;
  float y = uv.y + 0.12 * e.y * (uv.x - 0.5);              // the bands lean a little
  float n = 9.0 * (1.0 + 0.4 * e.x);                       // few broad bands .. many narrow ones
  float w = sin(y * n + t + sin(uv.x * 3.0 + t * 0.7) * 0.8) * 0.5 + 0.5;
  float w2 = sin(y * n * 2.55 - t * 1.3 + sin(uv.x * 5.0 - t * 0.5) * 0.6) * 0.5 + 0.5;
  float lo = 0.2 + 0.12 * e.z, hi = 0.9 - 0.12 * e.z;      // haze .. crisp lines
  float v = smoothstep(lo, hi, w * 0.7 + w2 * 0.3);
  vec3 col = mix(iColA, iColB, v);
  col = mix(col, iColC, pow(v, 5.0 - 2.0 * e.w) * (0.5 + 0.2 * e.w) * (0.7 + 0.3 * iEnergy));
  o = vec4(col, 1.0);
}
