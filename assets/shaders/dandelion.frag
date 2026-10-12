// Dandelion: a glowing seed head of fine radial lines, each tipped with a point of light, turning
// imperceptibly. Through the day a few seeds drift off (iClock); treble makes the tips sparkle.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.01;
  float r = length(uv), a = atan(uv.y, uv.x) + t * 0.3;
  float N = 48.0;
  float sector = 6.2832 / N;
  float k = floor(a / sector + 0.5);
  float da = a - k * sector;
  float id = mod(k, N);
  float gone = step(hash(id * 2.1) * 24.0, iClock - 6.0);                 // this seed has flown
  float L = 0.36 + 0.05 * hash(id);
  float lineW = 0.0016 / max(r, 0.05);
  float stem = smoothstep(lineW, 0.0, abs(da)) * step(r, L) * smoothstep(0.03, 0.1, r);
  float tip = exp(-pow((r - L) / 0.012, 2.0)) * smoothstep(lineW * 3.0, 0.0, abs(da)) * (0.8 + 0.4 * iBright * hash(id + floor(iTime * 0.2)));
  vec3 col = iColA * 0.7 + iColB * 0.3 * exp(-r * r * 9.0);
  col += iColB * stem * 0.55 * (1.0 - gone);
  col += iColC * tip * (1.0 - gone);
  float fx = uv.x + 0.4 * (iClock - 6.0 - hash(id * 2.1) * 24.0) * 0.1, fy = uv.y;
  vec2 fly = vec2(cos(k * sector), sin(k * sector)) * (L + (iClock - 6.0 - hash(id * 2.1) * 24.0) * 0.03);
  float fd = length(uv - fly);
  col += iColC * 0.5 * gone * exp(-fd * fd * 1200.0) * step(length(fly), 0.75);
  col += iColC * exp(-r * r * 400.0) * 0.6;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
