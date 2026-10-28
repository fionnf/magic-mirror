// Crystal: the life of one ice crystal once round the clock face every hour - a hexagonal plate that grows into a snowflake, melts to a drop of water and freezes again.
// :00 a small hexagonal plate of ice, cut into six facets like a low pyramid. :10 six arms have grown
// out of its corners, each with a pointed hexagonal tip. :20 side branches sprout along the arms at
// sixty degrees, and by :30 it is a full dendritic snowflake, little fronds on every branch, glinting
// as the light walks over its facets. From :32 it melts: the fronds and branches draw back and wear
// round, the arms shorten and their points blunt into a soft six-lobed star by :40, which gathers
// into a single clear droplet at :50.
// From :52 the droplet freezes again, its round edge squaring off into the hexagonal plate of :00.
// Six-fold throughout (one 30-degree sector, mirrored). Lit as cut ice: each facet takes the cold light
// flat, a key light that walks round with the day and sweeps across once an hour, white glints where a
// facet catches it, a thin bright edge, a faint cold glow in the room; the water drop is lit as a dome
// with one bright highlight and a caustic crescent on its far side.
float smin(float a, float b, float k){ float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0); return mix(b, a, h) - k * h * (1.0 - h); }

// a spike of ice from o along angle th: half width w, a 120-degree point at length l
float spike(vec2 q, vec2 o, float th, float l, float w){
  vec2 u = vec2(cos(th), sin(th)), p = q - o;
  p = vec2(dot(p, u), abs(dot(p, vec2(-u.y, u.x))));
  float d = max(p.y - w, 0.5 * (p.x - l) + 0.866 * p.y);
  return max(d, -p.x - w);
}
// the same arm worn round by melting: a capsule of radius w out to l
float capsule(vec2 q, vec2 o, float th, float l, float w){
  vec2 u = vec2(cos(th), sin(th)), p = q - o;
  return length(p - u * clamp(dot(p, u), 0.0, l)) - w;
}

// the form through the hour: keyframes (plate radius, arm length, arm width, branches) and
// (fronds, softness, water-roundness, wetness of the light)
vec4 keyA(int k){
  if (k == 0) return vec4(0.150, 0.140, 0.030, 0.00);   // hexagonal plate
  if (k == 1) return vec4(0.080, 0.340, 0.026, 0.00);   // six arms
  if (k == 2) return vec4(0.070, 0.370, 0.022, 0.75);   // branches
  if (k == 3) return vec4(0.066, 0.390, 0.019, 1.00);   // full dendrite
  if (k == 4) return vec4(0.115, 0.220, 0.050, 0.00);   // melting, rounded
  return vec4(0.120, 0.100, 0.055, 0.00);               // the droplet
}
vec4 keyB(int k){
  if (k == 0) return vec4(0.0, 0.004, 0.0, 0.0);
  if (k == 1) return vec4(0.0, 0.004, 0.0, 0.0);
  if (k == 2) return vec4(0.0, 0.004, 0.0, 0.0);
  if (k == 3) return vec4(1.0, 0.003, 0.0, 0.0);
  if (k == 4) return vec4(0.0, 0.070, 0.0, 0.85);
  return vec4(0.0, 0.080, 1.0, 1.0);
}

vec4 PA, PB;   // the current form

float crystal(vec2 uv){
  float r = length(uv), a = atan(uv.x, uv.y);          // angle from straight up: arms point up and down
  a = abs(mod(a + 0.5236, 1.0472) - 0.5236);            // fold into one 30-degree sector, mirrored
  vec2 q = r * vec2(cos(a), sin(a));
  float Rp = PA.x, L = PA.y, w = PA.z, B1 = PA.w, B2 = PB.x, k = PB.y;
  float d = dot(q, vec2(0.866, 0.5)) - Rp * 0.866;     // the hexagonal plate
  float arm = mix(spike(q, vec2(0.0), 0.0, L, w), capsule(q, vec2(0.0), 0.0, L - w, w), smoothstep(0.01, 0.07, k));
  d = smin(d, arm, k);                                  // the arm, its point wearing round as it melts
  float gb = smoothstep(0.0, 0.25, B1), gf = smoothstep(0.0, 0.3, B2);
  for (int i = 0; i < 3; i++) {
    float fi = float(i);
    float x = L * (0.40 + 0.20 * fi + 0.025 * iEvolve.x);
    float l = L * B1 * (0.31 - 0.04 * fi - 0.05 * fi * fi) * (1.0 + 0.08 * iEvolve.y);
    float wb = w * 0.8 * smoothstep(0.0, 0.7, B1);     // thinning as it draws back, so no nubs are left behind
    float br = mix(spike(q, vec2(x, 0.0), 1.0472, l, wb), capsule(q, vec2(x, 0.0), 1.0472, max(l - wb, 0.0), wb), smoothstep(0.004, 0.03, k));
    d = smin(d, br + 0.3 * (1.0 - gb), k);   // a vanished branch lifts out of reach
    for (int j = 0; j < 2; j++) {                        // fronds off the branch, parallel to the arm
      float s = l * (0.45 + 0.3 * float(j));
      vec2 o = vec2(x, 0.0) + s * vec2(0.5, 0.866);
      d = smin(d, spike(q, o, 0.0, B2 * l * (0.42 - 0.18 * float(j)) * (1.0 + 0.15 * iEvolve.z), w * 0.6 * smoothstep(0.0, 0.7, B2)) + 0.3 * (1.0 - gf), k);
    }
  }
  d -= k * 0.25;
  return mix(d, r - 0.165, PB.z);                       // the droplet
}

void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y) * 1.08;
  float p = fract(iClock) * 6.0;                        // where we are in the hour, 0..6
  int k = int(floor(p));
  float s = smoothstep(0.15, 1.0, fract(p));            // rest a moment in each form, change for most of the stage
  int k2 = k == 5 ? 0 : k + 1;
  PA = mix(keyA(k), keyA(k2), s);
  PB = mix(keyB(k), keyB(k2), s);
  float sb = smoothstep(0.15, 0.75, fract(p));           // branches and fronds lead: drawn back before the arms soften
  PA.w = mix(keyA(k).w, keyA(k2).w, sb);
  PB.x = mix(keyB(k).x, keyB(k2).x, sb);
  float d = crystal(uv) - 0.004 * iBreath;
  vec2 h = vec2(0.006 + 0.08 * PB.y, 0.0);                // wider while it melts, so soft forms read soft
  vec2 e1 = vec2(0.0, 1.0), e2 = vec2(0.866, -0.5), e3 = vec2(-0.866, -0.5);   // three taps round a triangle
  vec2 g = (crystal(uv + h.x * e1) * e1 + crystal(uv + h.x * e2) * e2 + crystal(uv + h.x * e3) * e3) / (1.5 * h.x);
  vec2 gn = g / max(length(g), 0.75);                    // flatter along the ridges, where the facets meet
  float depth = max(-d, 0.0), wet = PB.w;
  // ice: a roof of flat facets rising from every edge; water: a dome
  float R = 0.17;
  float dm = clamp(R - depth, 0.0, R - 0.002);
  float dome = clamp(dm / sqrt(R * R - dm * dm), 0.0, 3.0);
  float r = length(uv), rd = min(r, 0.17);              // water swells into one round dome about the middle
  vec2 wt = mix(uv / max(r, 0.001) * rd / sqrt(0.0361 - rd * rd), gn * dome, smoothstep(0.04, 0.0, depth));
  vec3 N = normalize(vec3(-mix(gn * 0.9, wt, smoothstep(0.0, 0.7, wet)), 1.0));
  float la = 2.4 + iClock * 0.26 + 0.9 * sin(6.28318 * fract(iClock));   // walks with the day, sweeps once an hour
  vec3 Lt = normalize(vec3(cos(la), sin(la), 0.9 + 0.2 * iEvolve.w));
  float dif = max(dot(N, Lt), 0.0);
  float spec = pow(max(dot(N, normalize(Lt + vec3(0.0, 0.0, 1.0))), 0.0), mix(18.0, 60.0, wet));
  float edge = exp(-pow(d / 0.006, 2.0));
  vec3 ice = mix(iColB * 0.78, mix(iColB, iColC, 0.45), dif * dif);   // each facet flat in the cold light
  vec3 water = mix(iColB * 0.72, mix(iColB, iColC, 0.25), dif);
  float body = smoothstep(0.004, -0.004, d);
  float caustic = smoothstep(0.6, 0.95, dot(-gn, -Lt.xy)) * smoothstep(0.07, 0.0, depth) * wet * body;
  vec3 col = iColA * 0.12 + iColB * 0.10 * exp(-max(d, 0.0) * 9.0);   // the room, a faint cold glow
  col = mix(col, mix(ice, water, wet), body);
  col += iColC * body * spec * mix(0.9, 1.3, wet);       // glints
  col += iColC * caustic * 0.6;
  col += iColC * edge * (0.35 + 0.4 * dif);              // the bright cut edge
  o = vec4(col, 1.0);
}
