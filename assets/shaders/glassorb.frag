// Glass orb: one soft, slightly lumpy body of deep violet glass on black, its rim catching a cold
// white light from the upper left and a blue glow along the bottom edge. It turns very slowly and
// its outline breathes with the bass; through the day the light walks round its rim.
float n2(vec2 p){ return sin(p.x * 1.7 + sin(p.y * 1.3)) * 0.5 + sin(p.y * 2.3 - p.x * 0.7) * 0.5; }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  float t = iTime * 0.03;
  float a = atan(uv.y, uv.x), r = length(uv);
  float edge = 0.36 + 0.025 * sin(a * 3.0 + t * 2.0) + 0.018 * sin(a * 5.0 - t * 1.3) + 0.012 * iBreath;
  float d = r - edge;                                   // < 0 inside the glass
  float body = smoothstep(0.01, -0.02, d);
  float depth = clamp(-d / edge, 0.0, 1.0);
  vec2 L = normalize(vec2(cos(2.4 + iClock * 0.26), sin(2.4 + iClock * 0.26)));   // the key light moves with the day
  vec2 nrm = uv / max(r, 1e-3);
  float rim = exp(-pow(d / 0.018, 2.0));
  float lit = pow(max(dot(nrm, L), 0.0), 2.0);
  float under = pow(max(dot(nrm, -L), 0.0), 3.0);
  vec3 col = iColA * 0.15;
  col = mix(col, mix(iColA * 0.9, iColB * 0.45, pow(1.0 - depth, 2.0) * 0.8 + 0.08 * n2(uv * 4.0 + t)), body);
  col += iColC * rim * (0.25 + 1.2 * lit);              // the white edge light
  col += iColB * rim * under * 1.3;                     // a blue glow along the far edge
  col += iColC * 0.12 * body * smoothstep(0.5, 0.0, length(uv - L * edge * 0.55)) ;  // a soft inner sheen
  col += iColB * 0.06 * exp(-d * 9.0) * step(0.0, d);  // a faint halo in the room
  o = vec4(col, 1.0);
}
