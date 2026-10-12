// Orbit: a dark disc with a single bright point travelling round it, leaving a fading arc of
// light; one full turn an hour, so the arc is a clock. Rising tension draws the orbit tighter.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float r = length(uv);
  float a = atan(uv.y, uv.x);
  float ph = fract(iClock) * 6.2832 - 1.5708;                 // one turn an hour, from the top
  float R = 0.34 - 0.05 * iTension;
  vec3 col = iColA * 0.6 + iColB * 0.25 * exp(-r * r * 3.0);
  float disc = smoothstep(0.004, -0.004, r - 0.19);
  col = mix(col, iColA * 0.35, disc);
  col += iColB * 0.5 * exp(-abs(r - 0.19) * 30.0) * (1.0 - disc);      // the rim
  float back = mod(ph - a, 6.2832);                           // angle since the point passed
  float trail = exp(-back * 0.9) * (1.0 - smoothstep(0.0, 0.02, abs(r - R) - 0.004));
  col += iColB * trail * 0.8;
  vec2 pt = vec2(cos(ph), sin(ph)) * R;
  float d = length(uv - pt);
  col += iColC * exp(-d * d * 900.0) + iColC * 0.4 * exp(-d * 14.0);
  o = vec4(min(col, vec3(1.0)), 1.0);
}
