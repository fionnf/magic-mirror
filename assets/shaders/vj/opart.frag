// Op art (music): Bridget-Riley-like stripes bent by slow waves, the GPU port of artsy.OpArt as
// music mode shows it (luminance through the scene palette). The bass bends the stripes further;
// the stripe edges are anti-aliased with fwidth so they never shimmer.
vec3 pal(float s){                       // scene palette: iColA/B/C are LUT entries 25/140/245 of the
  vec3 s0 = 0.5 * iColA;                 // scene's 4-stop ramp; rebuild the 4 stops (within ~5%)
  vec3 s1 = s0 + (iColA - s0) / 0.2941;
  vec3 s2 = s1 + (iColB - s1) / 0.6471;
  vec3 s3 = s2 + (iColC - s2) / 0.8824;
  float x = clamp(s, 0.0, 1.0) * 3.0;
  vec3 c = x < 1.0 ? mix(s0, s1, x) : x < 2.0 ? mix(s1, s2, x - 1.0) : mix(s2, s3, x - 2.0);
  return clamp(c, 0.0, 1.0);
}
void mainImage(out vec4 o, in vec2 fc){
  float W = iResolution.x;
  float x = (fc.x - 0.5) / W;
  float y = (iResolution.y - fc.y - 0.5) / W;      // top-down, width units (no stretch)
  float t = iTime;
  float amp = 1.0 + 0.55 * iBass + 0.1 * iEnergy;
  float bend = (0.07 * sin(y * 9.0 + t * 0.35) + 0.05 * sin(y * 17.0 - t * 0.22 + x * 3.0)) * amp;
  float v = sin((x + bend + 0.075 * y) * 62.0 + t * 0.4);
  float k = min(3.0, 1.3 / max(length(vec2(dFdx(v), dFdy(v))), 1e-4));   // soft edge, >= ~1.5 px wide
  float s = clamp(v * k, -1.0, 1.0) * 0.5 + 0.5;
  float glow = 0.5 + 0.5 * sin(y * 3.0 + t * 0.1);
  float lum = mix(0.7552, 0.1020, s) * (0.65 + 0.35 * glow);
  o = vec4(pal(clamp(pow(lum, 0.85) * 1.15, 0.0, 1.0)), 1.0);
}
