// Flow lines (GPU port of display/shapes.py FlowDots(lines=True)): a comb of 30 strands released
// along the top edge and carried down through a slowly drifting two-wave field, each strand gently
// pulled back toward its own start. Instead of tracing every strand, each pixel follows the field
// backward to the top edge and learns which strand would reach it (strands never cross: the flow is a
// 1-D field per row), so the cost is one short loop per pixel. Strand shade runs dark (left) to light.
// The bass swells the lines and their glow.
float field(float x, float y, float H, float p1, float p2){
  float yy = y / H;
  return (sin(yy * 5.1 + x * 0.034 + p1) * 0.9 + sin(yy * 8.9 - x * 0.021 - p2) * 0.6) * (0.3 + yy * 1.1);
}
// the start x (top edge) of the strand that passes through (x, y)
float label(float x, float y, float H, float p1, float p2){
  const int N = 34;
  float h = (y + 2.0) / float(N);
  float a = x, b = 0.0;                   // position along the way = a + b * x0 (x0 unknown, solved at the end)
  float g1 = 1.0 + 0.012 * h;
  for (int i = 0; i < N; i++){
    float xe = a + b * (a / (1.0 - b));   // best guess of the position so far
    float f = field(xe, y, H, p1, p2);
    a = a * g1 - 1.2 * h * f;
    b = b * g1 - 0.012 * h;
    y -= h;
  }
  return a / (1.0 - b);
}
vec3 pal(float v){
  v = clamp(v, 0.0, 1.0);
  if (v < 0.098) return mix(iColA * 0.5, iColA, v / 0.098);   // the palette's darkest end (black field)
  return v < 0.549 ? mix(iColA, iColB, (v - 0.098) / 0.451)
                   : mix(iColB, iColC, clamp((v - 0.549) / 0.412, 0.0, 1.0));
}
void mainImage(out vec4 o, in vec2 fc){
  float W = iResolution.x, H = iResolution.y;
  vec2 p = vec2(fc.x - 0.5, H - fc.y - 0.5);          // image coordinates, y down like the CPU piece
  float p1 = iTime * 0.35, p2 = iTime * 0.23;
  float sp = W / 30.0;
  float s = label(p.x, p.y, H, p1, p2) / sp - 0.5;      // strand index (fractional)
  float k = floor(s + 0.5);
  float gr = max(length(vec2(dFdx(s), dFdy(s))), 1e-3);
  float d = abs(s - k) / gr;                            // distance to the strand in pixels
  float inside = step(-0.5, k) * step(k, 29.5);
  float bass = clamp(iBass, 0.0, 1.0);
  float w = 0.4 + 0.8 * bass + 0.15 * iEnergy;        // half width of the line core
  float core = clamp(w + 0.5 - d, 0.0, 1.0);
  float sig = 1.2 + 0.6 * bass;
  float glow = (0.38 + 0.15 * bass) * exp(-d * d / (2.0 * sig * sig));
  float shade = 0.15 + 0.8 * k / 30.0;
  float v = clamp((core * 0.85 + glow) * shade * 1.1 * inside, 0.0, 1.0);
  o = vec4(pal(v), 1.0);
}
