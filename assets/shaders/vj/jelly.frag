// Jellyfish (music): five soft bells drifting slowly upward with tendrils trailing below - the GPU
// port of organic.Jelly (same seeds and paths) as music mode shows it (grey through the scene
// palette). The bass swells the bells and lengthens their sway; unlike the CPU piece the whole
// frame no longer brightens with the bass (no flashing), it sits at a steady level instead.
const vec3 JP[5] = vec3[5](vec3(1.5752,5.9456,1.1889), vec3(1.1260,2.1973,1.4478), vec3(4.2104,0.7227,5.6288),
                           vec3(5.3891,0.0178,3.4004), vec3(0.6710,1.6200,2.6181));
const float JS[5] = float[5](0.1218,0.1228,0.1549,0.1081,0.1032);
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
  float W = iResolution.x, hy = iResolution.y / W;
  vec2 p = vec2(fc.x - 0.5, iResolution.y - fc.y - 0.5) / W;   // width units, top-down
  float t = iTime, b = iBass;
  float acc = 0.0;
  for (int i = 0; i < 5; i++){
    vec3 ph = JP[i];
    float cx = 0.5 + 0.38 * sin(t * 0.05 + ph.x);
    float cy = (0.9 - fract(t * 0.02 + ph.y * 0.1) * 1.1) * hy;   // rising slowly
    float s = JS[i] * (1.0 + 0.32 * b + 0.08 * sin(t * 1.3 + ph.z));
    vec2 d = (p - vec2(cx, cy)) / s;
    if (d.y < -1.8 || d.y > 6.5 || abs(d.x) > 2.6) continue;     // nothing of this jelly here
    float bell = exp(-(d.x * d.x + (d.y < 0.0 ? d.y * d.y * 2.2 : d.y * d.y * 0.9)) * 1.6);
    float rr = length(d) - 1.0;
    float rim = exp(-rr * rr * 9.0) * 0.6;
    float tl = (p.y - cy) / (s * 3.5);
    float along = clamp(tl, 0.0, 1.0) * clamp(1.6 - tl, 0.0, 1.0);
    if (along > 0.0){
      for (int k = 0; k < 4; k++){                               // tendrils
        float fk = float(k);
        float tx = cx + (fk - 1.5) * s * 0.35 + 0.02 * sin(t * 0.8 + fk + float(i))
                 + (0.03 + 0.012 * b) * sin(p.y * 18.0 / hy + t * 1.1 + fk);
        float e = p.x - tx;
        acc += exp(-e * e * 2500.0) * along * 0.35;
      }
    }
    acc += bell * 0.9 + rim;
  }
  float v = pow(clamp(acc, 0.0, 1.0), 0.9) * 0.8;               // steady (the CPU used 0.75 + 0.25 * bass)
  o = vec4(pal(v), 1.0);
}
