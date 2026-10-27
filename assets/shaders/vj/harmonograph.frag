// Harmonograph (music): GPU port of shapes.Harmonograph. Two decaying pendulums draw a looping
// rose (u = 0..16pi, decay exp(-0.02u)); the frequencies a ~ 3, b ~ 5 drift slowly so the figure
// keeps re-weaving. Colour runs along the curve (outer loops dim, inner loops bright gold) and
// goes through luminance -> scene palette, as the CPU path does.
//
// Instead of testing ~1500 segments per pixel, the curve is found where it crosses the pixel's
// row: y(u) = py has two solutions per turn of the y pendulum (about 80 in all), each found in
// closed form (asin) plus one fixed-point and one Newton step. Crossings far from the pixel in x
// are dropped after the cheap first estimate. The bass swells the line and its glow.
vec3 pal(float v){
  float i = clamp(v, 0.0, 1.0) * 255.0;
  if (i < 25.0) return mix(iColA * 0.55, iColA, i / 25.0);
  if (i < 140.0) return mix(iColA, iColB, (i - 25.0) / 115.0);
  return mix(iColB, iColC, (i - 140.0) / 105.0);
}
float goldLum(float v){
  v = clamp(v, 0.0, 1.0) * 3.0;
  return v < 1.0 ? mix(0.047, 0.389, v) : v < 2.0 ? mix(0.389, 0.725, v - 1.0) : mix(0.725, 0.949, v - 2.0);
}
float fasin(float x){                       // asin, |err| < 7e-5
  float a = abs(x);
  float r = 1.5707288 + a * (-0.2121144 + a * (0.0742610 - 0.0187293 * a));
  r = 1.5707963 - sqrt(1.0 - a) * r;
  return x < 0.0 ? -r : r;
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 R = iResolution;
  float t = iTime;
  float S = min(R.x, R.y) * 0.46;
  vec2 q = vec2(fc.x - 0.5, R.y - fc.y - 0.5) - 0.5 * R;   // CPU pixel coords about the centre, y down
  float a = 3.0 + 0.5 * sin(t * 0.03);
  float b = 5.0 + 0.5 * cos(t * 0.021);
  float pa = t * 0.1, py = 1.9 + t * 0.07;
  float U = 16.0 * 3.14159265;
  float hw = 0.55 + 0.6 * iBass + 0.1 * iEnergy;
  float qn = q.y / S;
  float core = 0.0, glow = 0.0;
  // turn k of the y pendulum: phase B = b u + py runs over [2 pi k - pi/2, 2 pi k + 3 pi/2)
  float k0 = floor((py + 1.5708) / 6.2832);
  float k1 = floor((py + b * U + 1.5708) / 6.2832);
  float uc = (6.2832 * k0 + 1.5708 - py) / b;               // centre of the first turn
  float Dk = exp(-0.02 * uc), Dstep = exp(-0.02 * 6.2832 / b);
  for (int kk = 0; kk < 48; kk++) {
    float k = k0 + float(kk);
    if (k > k1) break;
    float Dc = Dk;
    Dk *= Dstep;
    // the whole turn lies inside |x|, |y| <= S D: skip it if the pixel is outside
    float box = S * Dc * 1.015 + 3.0;
    if (abs(q.x) > box || abs(q.y) > box) continue;
    float ucc = (6.2832 * k + 1.5708 - py) / b;
    for (int br = 0; br < 2; br++) {
      float sgn = br == 0 ? 1.0 : -1.0;
      float base = 6.2832 * k + (br == 0 ? 0.0 : 3.14159265);
      // first estimate: y ~ D (0.7 sin B + 0.3 sin(1.01 a u + 2.2)), the 0.3 term where sin B = 0
      float u = (base - py) / b;
      float D = Dc * (1.0 - 0.02 * (u - ucc));
      float w = (qn / D - 0.3 * sin(1.01 * a * u + 2.2)) / 0.7;
      float th = fasin(clamp(w, -1.0, 1.0));
      u = (base + sgn * th - py) / b;
      if (u < -0.1 || u > U + 0.1) continue;
      D = Dc * (1.0 - 0.02 * (u - ucc));
      float X = S * D * (0.7 * sin(a * u + pa) + 0.3 * sin(b * u + 0.5));
      if (abs(X - q.x) > 30.0) continue;                   // this crossing is far from the pixel
      // refine: the 0.3 term at the estimate
      w = (qn / D - 0.3 * sin(1.01 * a * u + 2.2)) / 0.7;
      th = fasin(clamp(w, -1.0, 1.0));
      u = (base + sgn * th - py) / b;
      if (u < -0.05 || u > U + 0.05) continue;
      D = Dc * (1.0 - 0.02 * (u - ucc));
      // one Newton step on y(u) = q.y, then the curve point, its tangent and the distance
      float yb = b * u + py, ya = 1.01 * a * u + 2.2;
      float Y = S * D * (0.7 * sin(yb) + 0.3 * sin(ya));
      float dY = S * D * (0.7 * b * cos(yb) + 0.303 * a * cos(ya)) - 0.02 * Y;
      u -= clamp((Y - q.y) / (abs(dY) > 1.0 ? dY : 1.0), -0.06, 0.06);
      u = clamp(u, 0.0, U);
      D = Dc * (1.0 - 0.02 * (u - ucc));
      float xa = a * u + pa, xb = b * u + 0.5; yb = b * u + py; ya = 1.01 * a * u + 2.2;
      vec2 sn = vec2(0.7 * sin(xa), 0.3 * sin(xb)), sy = vec2(0.7 * sin(yb), 0.3 * sin(ya));
      vec2 P = S * D * vec2(sn.x + sn.y, sy.x + sy.y);
      vec2 dP = S * D * vec2(0.7 * a * cos(xa) + 0.3 * b * cos(xb), 0.7 * b * cos(yb) + 0.303 * a * cos(ya)) - 0.02 * P;
      vec2 ddP = -S * D * vec2(a * a * sn.x + b * b * sn.y, b * b * sy.x + 1.0201 * a * a * sy.y);
      // closest point near the crossing: one Newton step on |P(u) - q|^2 using the curvature
      vec2 v = P - q;
      float del = -dot(v, dP) / max(dot(dP, dP) + dot(v, ddP), 0.25 * dot(dP, dP) + 1.0);
      del = clamp(del, -0.08, 0.08);
      v += del * dP + 0.5 * del * del * ddP;
      u += del;
      if (u < 0.0 || u > U) continue;
      float dist = length(v);
      float lum = goldLum(u / U);
      float ad = dist;
      float c = clamp(hw + 0.5 - ad, 0.0, 1.0);
      float e = max(ad - (hw - 0.65), 0.0);
      core = max(core, c * lum);
      float g = 0.3 * (1.0 + 1.2 * (hw - 0.65)) * exp(-e * e / 2.88) * lum;
      glow += g * (1.0 - 0.6 * glow);                    // overlapping lines don't stack up much (the CPU draws over)
    }
  }
  float L = min(0.75 * core + 0.95 * glow, 1.0);
  float field = clamp(pow(L, 0.85) * 1.15, 0.0, 1.0);
  o = vec4(pal(field), 1.0);
}
