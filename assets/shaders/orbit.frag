// Orbit: a dark disc with a single bright point travelling round it, leaving a fading arc of
// light; one full turn an hour, so the arc is a clock. Rising tension draws the orbit tighter.
// Over tens of minutes the orbit stretches into an ellipse and rounds again, the trail lengthens
// to a full ring or shortens to a comet's tail, the disc grows and shrinks, faint rings gather
// round it, and a small second moon appears on its own inner orbit and fades away.
float orbitR(float a, float R, float ecc, float w){ return R * (1.0 - ecc) / (1.0 + ecc * cos(a - w)) * (1.0 + ecc); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  vec4 e = iEvolve;
  float r = length(uv);
  float a = atan(uv.y, uv.x);
  float ph = fract(iClock) * 6.2832 - 1.5708;                 // one turn an hour, from the top
  float R = 0.31 - 0.05 * iTension;
  float ecc = 0.16 * (0.5 + 0.5 * e.x), w = 1.2 * e.z;        // round .. elliptical, its axis turning
  float Ra = orbitR(a, R, ecc, w);
  float disc_r = 0.19 * (1.0 + 0.18 * e.z);
  vec3 col = iColA * 0.6 + iColB * 0.25 * exp(-r * r * 3.0);
  float disc = smoothstep(0.004, -0.004, r - disc_r);
  col = mix(col, iColA * 0.35, disc);
  col += iColB * 0.5 * exp(-abs(r - disc_r) * 30.0) * (1.0 - disc);      // the rim
  float rings = smoothstep(0.0, 0.8, e.y) * (1.0 - disc);                // faint rings gather
  col += iColB * 0.12 * rings * pow(0.5 + 0.5 * cos((r - disc_r) * 120.0), 8.0) * smoothstep(0.12, 0.0, r - disc_r);
  float back = mod(ph - a, 6.2832);                           // angle since the point passed
  float decay = 0.9 * (1.0 - 0.6 * (0.5 + 0.5 * e.w));        // a comet's tail .. most of a ring
  float trail = exp(-back * decay) * (1.0 - smoothstep(0.0, 0.02, abs(r - Ra) - 0.004));
  col += iColB * trail * 0.8;
  vec2 pt = vec2(cos(ph), sin(ph)) * orbitR(ph, R, ecc, w);
  float d = length(uv - pt);
  col += iColC * exp(-d * d * 900.0) + iColC * 0.4 * exp(-d * 14.0);
  float moon = smoothstep(0.2, 0.9, -e.w);                    // a second, inner moon in part of the cycle
  if (moon > 0.0) {
    float mp = -ph * 1.6 + 2.0;
    float Rm = disc_r + 0.055;
    float mback = mod(a - mp, 6.2832);
    col += iColB * 0.5 * moon * exp(-mback * 1.6) * (1.0 - smoothstep(0.0, 0.015, abs(r - Rm) - 0.002));
    vec2 mpt = vec2(cos(mp), sin(mp)) * Rm;
    float dm = length(uv - mpt);
    col += iColC * moon * (0.7 * exp(-dm * dm * 1800.0) + 0.25 * exp(-dm * 20.0));
  }
  o = vec4(min(col, vec3(1.0)), 1.0);
}
