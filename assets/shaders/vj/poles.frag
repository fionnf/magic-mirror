// Flow poles (GPU port of display/shapes.py FlowPoles): 64 short streamlines (an 8 x 8 comb of
// seeds, slightly jittered) bending around a slowly turning ring of six poles - vortices and sinks in
// turn - with the poles marked by dots. Each pixel walks the flow backward one streamline length and
// checks whether it passes the seed it would have come from, so there is no per-strand loop. Along
// the way it tracks how much neighbouring streamlines spread apart (from the field's Jacobian), so the
// line distance is measured in screen pixels: lines stay one even, continuous width, and the seams
// between vortices (where the trace is unreliable) are faded out instead of twinkling. Shades as
// on the CPU (the ice palette's luminance, then the scene colours). The bass swells the lines and
// the pole dots.
const vec2 JIT[64] = vec2[64](
  vec2(0.38, -1.05), vec2(-0.83, -4.88), vec2(3.60, 2.29), vec2(-0.65, 1.55),
  vec2(0.56, -1.11), vec2(1.96, -0.62), vec2(-0.66, -1.58), vec2(0.91, -0.20),
  vec2(1.09, -1.21), vec2(0.25, -1.78), vec2(1.68, 0.38), vec2(0.66, 0.82),
  vec2(-2.02, 1.57), vec2(4.11, -3.28), vec2(-3.46, -3.01), vec2(1.68, 0.26),
  vec2(2.16, 1.44), vec2(0.42, 0.57), vec2(-0.34, 1.74), vec2(-2.26, -0.84),
  vec2(0.49, 3.60), vec2(-1.53, -2.16), vec2(-1.13, 1.94), vec2(-0.47, 2.65),
  vec2(-3.75, 2.26), vec2(2.07, -2.84), vec2(0.31, 2.43), vec2(0.18, 2.00),
  vec2(4.75, 0.55), vec2(-0.56, -1.54), vec2(1.30, -0.39), vec2(-0.36, -0.21),
  vec2(1.30, -2.13), vec2(-3.06, -4.87), vec2(2.40, 0.15), vec2(3.02, -0.02),
  vec2(-1.48, 0.96), vec2(-0.15, -2.51), vec2(-1.77, 3.53), vec2(0.71, 0.83),
  vec2(-0.55, -1.38), vec2(1.78, -0.21), vec2(-1.52, -0.27), vec2(-1.81, 0.38),
  vec2(2.26, -1.67), vec2(2.86, -1.34), vec2(0.31, -1.67), vec2(-0.44, 0.09),
  vec2(-0.87, -1.41), vec2(-1.36, -1.64), vec2(-3.14, -0.53), vec2(0.80, 1.82),
  vec2(1.29, 4.91), vec2(0.64, -0.91), vec2(3.74, -2.09), vec2(1.94, -1.91),
  vec2(0.71, -3.94), vec2(1.80, -0.32), vec2(-1.94, 3.36), vec2(1.53, 0.09),
  vec2(-1.49, -0.09), vec2(-0.33, 1.45), vec2(1.60, -1.34), vec2(-1.10, -1.06));
vec3 pal(float v){
  v = clamp(v, 0.0, 1.0);
  if (v < 0.098) return mix(iColA * 0.5, iColA, v / 0.098);   // the palette's darkest end (black field)
  return v < 0.549 ? mix(iColA, iColB, (v - 0.098) / 0.451)
                   : mix(iColB, iColC, clamp((v - 0.549) / 0.412, 0.0, 1.0));
}
// luminance of the CPU piece's ice palette at v (0..1)
float iceLum(float v){
  vec3 c = v < 0.3333 ? mix(vec3(8, 12, 40), vec3(30, 90, 200), v * 3.0)
         : v < 0.6667 ? mix(vec3(30, 90, 200), vec3(90, 220, 255), v * 3.0 - 1.0)
                      : mix(vec3(90, 220, 255), vec3(240, 250, 255), v * 3.0 - 2.0);
  return dot(c, vec3(0.3, 0.59, 0.11)) / 255.0;
}
vec2 PP[6];
// unit flow direction at q; k = how fast neighbouring streamlines spread apart there (per pixel
// travelled), from the field's Jacobian - lets the trace measure line distance in screen pixels
vec2 flow(vec2 q, out float k){
  vec2 v = vec2(0.0);
  float jxx = 0.0, jyy = 0.0, jc = 0.0;              // symmetric part of the Jacobian (all n.J.n needs)
  for (int i = 0; i < 6; i += 2){
    vec2 d = q - PP[i];                              // vortex
    float ir = 1.0 / (dot(d, d) + 30.0);
    vec2 f = vec2(-d.y, d.x) * ir;
    v += f;
    float a2 = 2.0 * ir;
    jxx -= f.x * d.x * a2; jyy -= f.y * d.y * a2; jc -= (f.x * d.y + f.y * d.x) * a2;
    d = q - PP[i + 1];                               // sink
    ir = 1.0 / (dot(d, d) + 30.0);
    f = -d * ir;
    v += f;
    a2 = 2.0 * ir;
    jxx += -ir - f.x * d.x * a2; jyy += -ir - f.y * d.y * a2; jc -= (f.x * d.y + f.y * d.x) * a2;
  }
  float L = length(v) + 1e-6;
  vec2 u = v / L;                                    // n = (-u.y, u.x)
  k = (u.y * u.y * jxx + u.x * u.x * jyy - u.x * u.y * jc) / L;
  return u;
}
void mainImage(out vec4 o, in vec2 fc){
  float W = iResolution.x, H = iResolution.y;
  vec2 p = vec2(fc.x - 0.5, H - fc.y - 0.5);          // image coordinates, y down like the CPU piece
  float t = iTime;
  float rad = W * (0.27 + 0.03 * sin(t * 0.07));
  for (int k = 0; k < 6; k++){
    float a = t * 0.05 + float(k) * 1.0471976;
    PP[k] = vec2(W, H) * 0.5 + rad * vec2(cos(a), sin(a));
  }
  float bass = clamp(iBass, 0.0, 1.0);
  float w = 0.4 + 0.8 * bass + 0.15 * iEnergy;        // half width of the line core
  float sig = 1.2 + 0.5 * bass, inv = 1.0 / (2.0 * sig * sig);
  vec2 g0 = vec2(W, H) * 0.06, gs = vec2(W, H) * 0.88 / 7.0;
  // walk back along the flow; at each step look at the nearest seed and how close the path passes it
  const int N = 16;
  float h = 3.6;                                     // 16 x 3.6 = the CPU's 18 x 3.2 line length
  vec2 q = p;
  float best = 1e3, bestI = 0.0, A = 0.0, bestA = 0.0, mA = 0.0;
  for (int i = 0; i <= N; i++){
    vec2 c = clamp(floor((q - g0) / gs + 0.5), 0.0, 7.0);
    int idx = int(c.y) * 8 + int(c.x);
    vec2 s = g0 + c * gs + JIT[idx];
    float kk;
    vec2 qn = q - flow(q, kk) * h;
    vec2 ab = qn - q;                                  // distance from the seed to this step's segment
    float u = (i == N) ? 0.0 : clamp(dot(s - q, ab) / dot(ab, ab), 0.0, 1.0);
    vec2 e = s - q - ab * u;                           // seed offset from this step's segment
    vec2 tn = ab * inversesqrt(max(dot(ab, ab), 1e-6));
    // the across-path part, carried forward to the pixel: neighbouring streamlines spread or squeeze
    // along the way (exp(A)), so this is the distance on screen; the nearest line on screen wins
    float d = length(vec2(dot(e, tn), (e.x * tn.y - e.y * tn.x) * exp(clamp(A, -4.0, 4.0))));
    if (d < best){ best = d; bestI = float(idx); bestA = mA; }   // mA: the largest spread on the way
    mA = max(mA, abs(A));
    A += kk * h;                                       // log spread of neighbouring lines, pixel -> here
    q = qn;
  }
  // where neighbouring paths split hard (a seam between vortices) the trace is not trustworthy and
  // would leave isolated twinkling pixels - fade the line out there
  float keep = 1.0 - smoothstep(1.0, 2.0, abs(bestA));
  float lum = iceLum(0.15 + 0.8 * mod(bestI * 7.0, 23.0) / 23.0);
  float line = keep * lum * (clamp(w + 0.5 - best, 0.0, 1.0) * 0.85 + 0.38 * exp(-best * best * inv));
  float dots = 0.0;
  for (int k = 0; k < 6; k++){
    float nd = max(length(p - PP[k]) - (2.0 + 1.0 * bass), 0.0);
    float l = (k & 1) == 0 ? 0.933 : 0.7;     // sinks: brighter than the CPU dot, standing in for its pile of converging lines
    dots = max(dots, l * (clamp(1.0 - nd, 0.0, 1.0) * 0.85 + 0.45 * exp(-nd * nd * inv)));
  }
  float v = max(line, dots);
  v = clamp(pow(v, 0.85) * 1.15, 0.0, 1.0);
  o = vec4(pal(v), 1.0);
}
