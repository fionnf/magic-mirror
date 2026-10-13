// Dot sea: a field of fine light points rolling in long slow swells, seen low across the water;
// near points large and bright, the far ones fading into dark blue. The swell grows with the bass,
// and the sea rises and calms over the day.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.05;
  float calm = 0.6 + 0.4 * sin(iClock * 0.26);
  vec3 col = vec3(0.0);
  for (int row = 0; row < 34; row++){
    float z = float(row) / 34.0;                           // 0 near .. 1 far
    float persp = mix(1.0, 0.18, z);
    float yb = mix(0.02, 0.72, pow(z, 0.8));
    float xs = (uv.x - 0.5) / persp;
    float h = (sin(xs * 6.0 + t + z * 7.0) * 0.6 + sin(xs * 13.0 - t * 1.3 + z * 4.0) * 0.4) * 0.05 * persp * calm * (1.0 + 0.4 * iBreath);
    float y = yb + h;
    float spacing = 0.035;
    float gx = fract(xs / spacing) - 0.5;
    float d = length(vec2(gx * spacing * persp * iResolution.x, (uv.y - y) * iResolution.y));
    float r = mix(1.6, 0.6, z);
    float dot_ = smoothstep(r + 0.6, r - 0.4, d);
    vec3 c = mix(iColC, iColB, z) * mix(1.0, 0.25, z);
    col = max(col, c * dot_);
  }
  col += iColA * 0.25 * (1.0 - uv.y);
  o = vec4(col, 1.0);
}
