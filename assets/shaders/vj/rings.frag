// Ripple rings (GPU port of display/shapes.py RadialRings): 18 concentric rings round the centre,
// each wobbling with its own few-lobed wave, neighbours turning opposite ways - a slow ripple.
// Shade runs from dark (inner) to light (outer). The bass opens the rings outward a little and
// swells their lines and glow.
vec3 pal(float v){
  v = clamp(v, 0.0, 1.0);
  if (v < 0.098) return mix(iColA * 0.5, iColA, v / 0.098);   // the palette's darkest end (black field)
  return v < 0.549 ? mix(iColA, iColB, (v - 0.098) / 0.451)
                   : mix(iColB, iColC, clamp((v - 0.549) / 0.412, 0.0, 1.0));
}
void mainImage(out vec4 o, in vec2 fc){
  float W = iResolution.x, H = iResolution.y;
  vec2 p = vec2(fc.x - 0.5, H - fc.y - 0.5) - vec2(W, H) * 0.5;   // y down like the CPU piece
  float r = length(p), a = atan(p.y, p.x + 1e-3);
  float bass = clamp(iBass, 0.0, 1.0);
  float grow = 1.0 + 0.07 * bass;                 // rings open outward with the bass
  float w = 0.35 + 0.8 * bass + 0.15 * iEnergy;   // half width of the line core
  float sig = 1.2 + 0.5 * bass;
  float gk = (0.3 + 0.12 * bass), inv = 1.0 / (2.0 * sig * sig);
  float span = (min(W, H) * 0.47 - 6.0) / 18.0;
  float core = 0.0, glow = 0.0;
  for (int k = 0; k < 18; k++){
    float fk = float(k);
    float m = 3.0 + mod(fk, 4.0);
    float amp = 1.5 + fk * 0.28;
    float ph = a * m + iTime * (0.35 + 0.03 * fk) * (mod(fk, 2.0) > 0.5 ? 1.0 : -1.0);
    float rk = (6.0 + fk * span + amp * sin(ph)) * grow;
    float slope = amp * m * cos(ph) * grow / max(r, 4.0);
    float d = abs(r - rk) / sqrt(1.0 + slope * slope);
    float shade = fk / 18.0;
    core = max(core, shade * clamp(w + 0.5 - d, 0.0, 1.0));
    glow += shade * exp(-d * d * inv);
  }
  float v = clamp((core * 0.85 + glow * gk) * 1.1, 0.0, 1.0);
  o = vec4(pal(v), 1.0);
}
