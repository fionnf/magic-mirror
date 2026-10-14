// Nebula (music): three layers of slowly shifting, warped sine clouds with a few twinkling stars -
// the GPU port of light_art.Nebula as music mode shows it (luminance through the scene palette).
// The bass makes the clouds billow: the warp deepens and the layers swell a little.
vec3 pal(float s){                       // scene palette: iColA/B/C are LUT entries 25/140/245 of the
  vec3 s0 = 0.5 * iColA;                 // scene's 4-stop ramp; rebuild the 4 stops (within ~5%)
  vec3 s1 = s0 + (iColA - s0) / 0.2941;
  vec3 s2 = s1 + (iColB - s1) / 0.6471;
  vec3 s3 = s2 + (iColC - s2) / 0.8824;
  float x = clamp(s, 0.0, 1.0) * 3.0;
  vec3 c = x < 1.0 ? mix(s0, s1, x) : x < 2.0 ? mix(s1, s2, x - 1.0) : mix(s2, s3, x - 2.0);
  return clamp(c, 0.0, 1.0);
}
float duskLum(float x){                  // luminance of the piece's own 'dusk' ramp
  x = clamp(x, 0.0, 1.0) * 3.0;
  return x < 1.0 ? mix(0.0466, 0.2227, x) : x < 2.0 ? mix(0.2227, 0.5306, x - 1.0) : mix(0.5306, 0.8231, x - 2.0);
}
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  float W = iResolution.x;
  vec2 pix = vec2(fc.x - 0.5, iResolution.y - fc.y - 0.5);
  float x = pix.x / W, y = pix.y / W;               // width units: no stretch on a tall wall
  float t = iTime;
  float b = iBass;
  float w1 = 1.4 + 0.6 * b + 0.2 * iEnergy, w2 = 1.3 + 0.6 * b + 0.2 * iEnergy;
  float zoom = 1.0 - 0.06 * b;                       // clouds swell around the middle
  x = 0.5 + (x - 0.5) * zoom; y = 0.5 * iResolution.y / W + (y - 0.5 * iResolution.y / W) * zoom;
  float v = 0.0;
  for (int k = 0; k < 3; k++){
    vec3 L = k == 0 ? vec3(3.0, 2.2, 0.05) : k == 1 ? vec3(5.5, 4.1, -0.07) : vec3(9.5, 7.0, 0.09);
    float amp = 0.55 / float(k + 1);
    v += amp * sin(x * L.x * 3.0 + sin(y * L.y * 2.0 + t * L.z * 3.0 + 0.5 * b) * w1 + t * L.z)
             * cos(y * L.y * 3.0 + sin(x * L.x * 2.0 - t * L.z * 2.0) * w2);
  }
  v = pow(clamp(0.5 + v * 0.7, 0.0, 1.0), 1.6);
  float lum = duskLum(v);
  float star = step(0.9975, hash(pix));
  lum += star * (0.5 + 0.5 * sin(pix.x * 7.0 + t * 1.3 + pix.y)) * 200.0 / 255.0;
  o = vec4(pal(clamp(pow(min(lum, 1.0), 0.85) * 1.15, 0.0, 1.0)), 1.0);
}
