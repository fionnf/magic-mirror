// Node garden (GPU port of display/shapes.py NodeGarden): 28 nodes drifting on slow Lissajous paths;
// neighbours closer than 0.3 of the width are joined by fine lines that fade with distance, and each
// node is a small bright dot. Each pixel only gathers the nodes within reach of itself (a line can only
// pass through it if both its ends are within reach), then joins those pairs, so the loops stay short.
// The bass swells the lines and dots and lets the web reach a little further (new links fade in).
const vec4 PH[28] = vec4[28](
  vec4(3.92560, 5.63450, 4.87131, 1.41430),
  vec4(1.88504, 5.48592, 0.03307, 5.15731),
  vec4(5.00560, 2.93863, 1.90304, 1.74851),
  vec4(1.60058, 2.79508, 3.16856, 3.47596),
  vec4(6.25174, 4.97792, 3.90729, 6.21067),
  vec4(1.35214, 1.00613, 3.84675, 0.27596),
  vec4(0.22407, 3.23350, 2.92777, 5.75981),
  vec4(3.95154, 3.22866, 3.12037, 1.55439),
  vec4(0.07407, 1.20829, 4.34596, 1.25981),
  vec4(2.32069, 0.02345, 5.21270, 0.97002),
  vec4(1.68052, 5.52849, 3.20149, 5.32010),
  vec4(4.01742, 4.65832, 0.57459, 3.39838),
  vec4(3.18881, 5.47201, 2.26874, 3.75660),
  vec4(0.37210, 2.43433, 2.02867, 0.94325),
  vec4(5.12660, 2.38292, 6.14654, 3.70515),
  vec4(3.79975, 4.00662, 4.24811, 0.94695),
  vec4(2.76517, 1.50446, 2.52769, 0.60730),
  vec4(6.07796, 1.35023, 4.21869, 1.88664),
  vec4(5.48920, 4.15871, 0.82655, 5.30707),
  vec4(5.93427, 5.67660, 3.57784, 0.91349),
  vec4(1.20867, 5.82725, 3.46861, 1.13387),
  vec4(5.55188, 4.02907, 3.57768, 2.36309),
  vec4(2.58080, 1.50399, 0.23900, 5.50265),
  vec4(2.93735, 3.43915, 2.02319, 4.71832),
  vec4(0.15824, 2.33732, 0.19060, 0.77176),
  vec4(6.07369, 4.13074, 2.68922, 3.28909),
  vec4(5.48124, 2.16164, 3.70703, 4.29354),
  vec4(2.23200, 3.25994, 4.80575, 5.70965));
const vec4 FR[28] = vec4[28](
  vec4(0.05208, 0.11467, 0.04041, 0.10024),
  vec4(0.10484, 0.05094, 0.07351, 0.10522),
  vec4(0.04114, 0.09028, 0.10344, 0.08104),
  vec4(0.09807, 0.05811, 0.05588, 0.06905),
  vec4(0.05435, 0.06768, 0.11585, 0.08587),
  vec4(0.06721, 0.06172, 0.11616, 0.07556),
  vec4(0.11843, 0.08124, 0.08169, 0.11172),
  vec4(0.09942, 0.08645, 0.07413, 0.11026),
  vec4(0.07293, 0.11382, 0.04550, 0.07440),
  vec4(0.08156, 0.11608, 0.06008, 0.10448),
  vec4(0.09412, 0.09737, 0.09037, 0.11772),
  vec4(0.06661, 0.07186, 0.05623, 0.04406),
  vec4(0.05703, 0.11324, 0.10721, 0.04899),
  vec4(0.08830, 0.07834, 0.08757, 0.09274),
  vec4(0.06453, 0.11691, 0.07727, 0.09025),
  vec4(0.09082, 0.05471, 0.04495, 0.07292),
  vec4(0.10112, 0.10522, 0.09840, 0.04906),
  vec4(0.11307, 0.10416, 0.11022, 0.08186),
  vec4(0.11325, 0.04373, 0.04242, 0.04162),
  vec4(0.06022, 0.05989, 0.05500, 0.08536),
  vec4(0.04312, 0.08723, 0.05328, 0.09423),
  vec4(0.04169, 0.06485, 0.11507, 0.08307),
  vec4(0.10493, 0.09264, 0.08886, 0.05530),
  vec4(0.08595, 0.04317, 0.10413, 0.11681),
  vec4(0.10832, 0.04406, 0.06709, 0.06544),
  vec4(0.04902, 0.09013, 0.10380, 0.06510),
  vec4(0.10902, 0.10377, 0.05033, 0.10135),
  vec4(0.11061, 0.05578, 0.08589, 0.09110));
vec3 pal(float v){
  v = clamp(v, 0.0, 1.0);
  if (v < 0.098) return mix(iColA * 0.5, iColA, v / 0.098);   // the palette's darkest end (black field)
  return v < 0.549 ? mix(iColA, iColB, (v - 0.098) / 0.451)
                   : mix(iColB, iColC, clamp((v - 0.549) / 0.412, 0.0, 1.0));
}
float segd(vec2 p, vec2 a, vec2 b){
  vec2 ab = b - a;
  float h = clamp(dot(p - a, ab) / max(dot(ab, ab), 1e-4), 0.0, 1.0);
  return length(p - a - ab * h);
}
void mainImage(out vec4 o, in vec2 fc){
  float W = iResolution.x, H = iResolution.y;
  vec2 p = vec2(fc.x - 0.5, H - fc.y - 0.5);          // image coordinates, y down like the CPU piece
  float t = iTime;
  float bass = clamp(iBass, 0.0, 1.0);
  float reach = W * 0.30 * (1.0 + 0.12 * bass);
  float w = 0.4 + 0.8 * bass + 0.15 * iEnergy;        // half width of the line core
  float sig = 1.2 + 0.5 * bass, inv = 1.0 / (2.0 * sig * sig);
  // gather the nodes near this pixel (at most 12; a line whose end is further than 0.8 reach is faint)
  vec2 P[12]; float I[12]; int n = 0;
  float core = 0.0, glow = 0.0, glowL = 0.0;
  for (int i = 0; i < 28; i++){
    vec4 ph = PH[i], fr = FR[i];
    vec2 q = vec2(W * 0.5 + (sin(t * fr.x + ph.x) + 0.4 * sin(t * fr.z * 2.3 + ph.z)) * W * 0.36,
                  H * 0.5 + (cos(t * fr.y + ph.y) + 0.4 * sin(t * fr.w * 2.1 + ph.w)) * H * 0.36);
    float d = length(p - q);
    if (d < W * 0.24 + 3.0 && n < 12){ P[n] = q; I[n] = float(i); n++; }
    float nd = max(d - (1.25 + 1.0 * bass), 0.0);      // the node dot
    float c = 0.6 + 0.4 * mod(float(i), 5.0) / 5.0;
    core = max(core, c * clamp(1.0 - nd, 0.0, 1.0));
    glow += c * 1.4 * exp(-nd * nd * inv);
  }
  for (int a = 0; a < 11; a++){
    if (a >= n - 1) break;
    for (int b = a + 1; b < 12; b++){
      if (b >= n) break;
      float L = length(P[a] - P[b]);
      if (L >= reach) continue;
      float k = 1.0 - L / reach;
      float c = (0.25 + 0.7 * mod(I[a] + I[b], 9.0) / 9.0) * k;
      float d = segd(p, P[a], P[b]);
      core = max(core, c * clamp(w + 0.5 - d, 0.0, 1.0));
      glowL = max(glowL, c * exp(-d * d * inv));   // overlapping lines do not pile up (as on the CPU)
    }
  }
  float v = clamp((core * 0.85 + (glow + 1.3 * glowL) * (0.33 + 0.05 * bass)) * 1.1, 0.0, 1.0);
  o = vec4(pal(v), 1.0);
}
