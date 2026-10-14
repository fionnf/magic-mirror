// Weave (music): GPU port of shapes.WovenGrid. Twenty-two horizontal threads (dim) and
// twenty-two vertical threads (bright, on top) displaced by travelling waves like cloth.
// Grey thread brightness -> scene palette, as the CPU path does. The bass swells the threads
// (wider, softer glow) and makes the cloth billow a little more.
vec3 pal(float v){
  float i = clamp(v, 0.0, 1.0) * 255.0;
  if (i < 25.0) return mix(iColA * 0.55, iColA, i / 25.0);
  if (i < 140.0) return mix(iColA, iColB, (i - 25.0) / 115.0);
  return mix(iColB, iColC, (i - 140.0) / 105.0);
}
// 1 px anti-aliased core that widens with hw, plus the CPU's 1.2 px gaussian glow
vec2 lineProf(float d, float hw){
  float ad = abs(d);
  float core = clamp(hw + 0.5 - ad, 0.0, 1.0);
  float e = max(ad - (hw - 0.65), 0.0);
  float glow = 0.28 * (1.0 + 1.2 * (hw - 0.65)) * exp(-e * e / 2.88);
  return vec2(core, glow);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 R = iResolution;
  vec2 p = vec2(fc.x - 0.5, R.y - fc.y - 0.5);            // CPU pixel coords, y down
  float t = iTime;
  float n = 22.0;
  float nh = floor(n * R.y / R.x + 0.5);                   // same thread pitch on a tall wall
  float sx = R.x / n, sy = R.y / nh;
  float amp = 1.0 + 0.35 * iBass;
  float hw = 0.65 + 0.5 * iBass + 0.1 * iEnergy;
  float coreH = 0.0, coreV = 0.0, covV = 0.0, glow = 0.0;
  // horizontal threads: y = base + 4 sin(.045x + .5t + .5k) + 2 sin(.09x - .31t)
  float kc = floor(p.y / sy);
  for (int j = -1; j <= 1; j++) {
    float k = kc + float(j);
    if (k < 0.0 || k >= nh) continue;
    float a1 = p.x * 0.045 + t * 0.5 + k * 0.5, a2 = p.x * 0.09 - t * 0.31;
    float y = (k + 0.5) * sy + amp * (sin(a1) * 4.0 + sin(a2) * 2.0);
    float sl = amp * (0.18 * cos(a1) + 0.18 * cos(a2));
    vec2 l = lineProf((p.y - y) * inversesqrt(1.0 + sl * sl), hw);
    float v = 0.1 + 0.4 * k / nh;
    coreH = max(coreH, l.x * v);
    glow += l.y * v;
  }
  // vertical threads, drawn on top
  kc = floor(p.x / sx);
  for (int j = -1; j <= 1; j++) {
    float k = kc + float(j);
    if (k < 0.0 || k >= n) continue;
    float a1 = p.y * 0.045 - t * 0.43 + k * 0.5, a2 = p.y * 0.08 + t * 0.27;
    float x = (k + 0.5) * sx + amp * (sin(a1) * 4.0 + sin(a2) * 2.0);
    float sl = amp * (0.18 * cos(a1) + 0.16 * cos(a2));
    vec2 l = lineProf((p.x - x) * inversesqrt(1.0 + sl * sl), hw);
    float v = 0.55 + 0.4 * k / n;
    coreV = max(coreV, l.x * v);
    covV = max(covV, l.x);
    glow += l.y * v;
  }
  float core = max(coreV * 1.15, 0.8 * coreH * (1.0 - covV));
  float field = clamp((0.85 * core + glow) * 1.1, 0.0, 1.0);
  o = vec4(pal(field), 1.0);
}
