// Ridges (music): GPU port of shapes.Ridges ("Night Ridges"). 34 stacked contour lines of a
// slowly evolving wave landscape; each is filled black below, so near (lower) ridges hide far
// ones. The line grey rises with nearness and is mapped through the scene palette as on the CPU.
// The bass lifts the ridges higher and swells the lines. On a tall wall the row pitch is kept
// (more rows) so nothing stretches.
vec3 pal(float v){
  float i = clamp(v, 0.0, 1.0) * 255.0;
  if (i < 25.0) return mix(iColA * 0.55, iColA, i / 25.0);
  if (i < 140.0) return mix(iColA, iColB, (i - 25.0) / 115.0);
  return mix(iColB, iColC, (i - 140.0) / 105.0);
}
vec2 lineProf(float d, float hw){
  float ad = abs(d);
  float core = clamp(hw + 0.5 - ad, 0.0, 1.0);
  float e = max(ad - (hw - 0.65), 0.0);
  float glow = 0.28 * (1.0 + 1.2 * (hw - 0.65)) * exp(-e * e / 2.88);
  return vec2(core, glow);
}
// ridge k at x: y (down) and slope dy/dx
vec2 ridge(float x, float k, float n, float base, float lift, float t){
  float depth = k / n;
  float amp = (6.0 + depth * 18.0) * lift;
  float a1 = x * 0.05 + t * 0.2 + k * 0.4, a2 = x * 0.021 - t * 0.13 + k * 0.17, a3 = x * 0.11 + k * 0.9 - t * 0.3;
  float s1 = sin(a1), s2 = sin(a2);
  float y = base - amp * (0.5 + 0.5 * s1 * s2 + 0.35 * sin(a3));
  float sl = -amp * (0.5 * (0.05 * cos(a1) * s2 + 0.021 * s1 * cos(a2)) + 0.0385 * cos(a3));
  return vec2(y, sl);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 R = iResolution;
  vec2 p = vec2(fc.x - 0.5, R.y - fc.y - 0.5);            // CPU pixel coords, y down
  float t = iTime;
  float n = floor(34.0 * R.y / R.x + 0.5);
  float top = R.y * 0.22, sp = R.y * 0.78 / n;
  float lift = 1.0 + 0.45 * iBass;
  float hw = 0.65 + 0.55 * iBass + 0.1 * iEnergy;
  // first row that can reach this pixel: its highest point 1.35 * amp above its base
  float m = 1.35 * lift;
  float ks = floor((p.y + 4.0 - top + m * 6.0) / (sp - m * 18.0 / n)) ;
  ks = min(ks, n - 1.0);
  float core = 0.0, glow = 0.0, front = 1e5;
  float kHit = -1.0;
  for (int i = 0; i < 64; i++) {
    float k = ks - float(i);
    if (k < 0.0) break;
    vec2 r = ridge(p.x, k, n, top + k * sp, lift, t);
    float d = (p.y - r.x) * inversesqrt(1.0 + r.y * r.y);
    float v = 0.15 + 0.8 * k / n;
    if (r.x <= front + 0.5 && d > -4.0) {                   // line visible here (not hidden by nearer ridges)
      vec2 l = lineProf(d, hw);
      core = max(core, l.x * v);
      glow += l.y * v;
    }
    front = min(front, r.x);
    if (r.x <= p.y) { kHit = k; break; }                    // pixel is under this ridge: farther ones hidden
  }
  // glow of the next two farther lines spilling down onto this ridge
  for (int i = 1; i <= 2; i++) {
    float k = kHit - float(i);
    if (k < 0.0) break;
    vec2 r = ridge(p.x, k, n, top + k * sp, lift, t);
    if (r.x > front) continue;
    front = r.x;
    float d = (p.y - r.x) * inversesqrt(1.0 + r.y * r.y);
    glow += lineProf(d, hw).y * (0.15 + 0.8 * k / n);
  }
  float field = clamp((0.75 * core + 0.85 * glow) * 1.1, 0.0, 1.0);
  o = vec4(pal(field), 1.0);
}
