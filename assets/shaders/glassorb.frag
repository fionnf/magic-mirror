// Glass orb: one soft, slightly lumpy body of deep violet glass on black, its rim catching a cold
// white light from the upper left and a blue glow along the bottom edge. It turns very slowly and
// its outline breathes with the bass; through the day the light walks round its rim.
// Over tens of minutes (iEvolve) it changes form: near-round to squashed and lobed (3 to 6 soft
// lobes), a second droplet budding off, drifting round and melting back, the veins inside thickening
// and thinning, the rim sharpening and the halo spreading.
float n2(vec2 p){ return sin(p.x * 1.7 + sin(p.y * 1.3)) * 0.5 + sin(p.y * 2.3 - p.x * 0.7) * 0.5; }
float smin(float a, float b, float k){ float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0); return mix(b, a, h) - k * h * (1.0 - h); }

float shape(vec2 uv, float t){
  vec4 e = iEvolve;
  float ang = 1.2 * e.w + t * 0.4;                      // the squash turns slowly
  vec2 q = mat2(cos(ang), -sin(ang), sin(ang), cos(ang)) * uv;
  q *= vec2(1.0 + 0.14 * e.x, 1.0 - 0.14 * e.x);        // round <-> an egg on its side
  float a = atan(q.y, q.x), r = length(q);
  float k = 4.5 + 1.5 * e.z;                            // 3 .. 6 lobes, blended between whole numbers
  float lobes = mix(sin(a * floor(k) + t * 2.0), sin(a * (floor(k) + 1.0) - t * 1.3), smoothstep(0.0, 1.0, fract(k)));
  float amp = 0.012 + 0.024 * (0.5 + 0.5 * e.y);         // nearly smooth .. clearly lumpy
  float edge = 0.34 + amp * lobes + 0.012 * sin(a * 2.0 - t) + 0.012 * iBreath;
  float d = r - edge;
  float bud = smoothstep(0.05, 0.75, e.w);              // a second droplet, only in part of the cycle
  if (bud > 0.0) {
    float ba = t * 0.5 + 2.0 * e.z, br = mix(0.12, 0.30 + 0.16 * (0.5 + 0.5 * e.x), bud);   // grows out from inside
    vec2 bc = br * vec2(cos(ba), sin(ba));
    d = smin(d, length(uv - bc) - 0.13 * bud, 0.09);    // melts into the body when close
  }
  return d;
}

void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  float t = iTime * 0.03;
  vec4 e = iEvolve;
  float d = shape(uv, t);                               // < 0 inside the glass
  vec2 h = vec2(0.004, 0.0);
  vec2 nrm = normalize(vec2(shape(uv + h.xy, t) - shape(uv - h.xy, t), shape(uv + h.yx, t) - shape(uv - h.yx, t)) + 1e-6);
  float body = smoothstep(0.01, -0.02, d);
  float depth = clamp(-d / 0.34, 0.0, 1.0);
  vec2 L = normalize(vec2(cos(2.4 + iClock * 0.26), sin(2.4 + iClock * 0.26)));   // the key light moves with the day
  float rimW = 0.018 + 0.008 * e.z;                     // a crisp edge .. a soft one
  float rim = exp(-pow(d / rimW, 2.0));
  float lit = pow(max(dot(nrm, L), 0.0), 2.0);
  float under = pow(max(dot(nrm, -L), 0.0), 3.0);
  float veins = (0.06 + 0.07 * (0.5 + 0.5 * e.y)) * n2(uv * (3.5 + 1.5 * e.x) + t);
  vec3 col = iColA * 0.15;
  col = mix(col, mix(iColA * 0.9, iColB * (0.4 + 0.12 * e.x), pow(1.0 - depth, 2.0) * 0.8 + veins), body);
  col += iColC * rim * (0.25 + 1.2 * lit);              // the white edge light
  col += iColB * rim * under * 1.3;                     // a blue glow along the far edge
  col += iColC * 0.12 * body * smoothstep(0.5, 0.0, length(uv - L * 0.2));   // a soft inner sheen
  col += iColB * 0.07 * exp(-d * (11.0 - 4.0 * e.w)) * step(0.0, d);       // a faint halo in the room
  o = vec4(col, 1.0);
}
