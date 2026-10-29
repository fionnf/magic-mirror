// Aurora: one northern night over a dark mountain line that plays out once every hour, the lights rising, folding, bursting overhead and fading into dawn.
// :00 night, a few stars, a faint arc low in the north above the mountains; by :10 it has risen and
// brightened, its hem starting to ripple; at :20 it has folded into tall curtains of fine vertical rays
// drifting slowly sideways, a second fainter curtain behind; at :30 a corona bursts overhead, the rays
// tilting until they all converge on a point above the top of the frame; at :40 it breaks into soft
// patches that pulse slowly; at :50 it has faded to a quiet low glow while the first blue of dawn climbs
// from the mountains, and by the hour the dawn has sunk back into night and the faint arc is waiting.
// Each stage rests a moment and then flows into the next over most of its ten minutes - the curtain is
// one sheet of light whose hem, height, rays and perspective change continuously, never a cross-fade.
// Lit as light, not surface: a white-hot lower hem (light colour) fading up through the mid colour into
// the dark colour at the top of the rays, the sky and the mountain ridge catching its glow.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n2(vec2 p){ return sin(p.x * 1.7 + sin(p.y * 1.3)) * 0.5 + sin(p.y * 2.3 - p.x * 0.7) * 0.5; }

// the six moments of the hour:
// a = (hem height, bow of the arc, fold depth, curtain height)
// b = (brightness, rays, corona, patches)
// c = (dawn, stars, back curtain, ripple)
void stage(int k, out vec4 a, out vec4 b, out vec4 c){
  if (k == 0)      { a = vec4(0.300, 0.050, 0.004, 0.050); b = vec4(0.72, 0.10, 0.0, 0.0); c = vec4(0.0, 1.00, 0.00, 0.2); }
  else if (k == 1) { a = vec4(0.340, 0.060, 0.022, 0.100); b = vec4(0.90, 0.45, 0.0, 0.0); c = vec4(0.0, 0.80, 0.30, 1.0); }
  else if (k == 2) { a = vec4(0.360, 0.015, 0.095, 0.200); b = vec4(1.10, 0.85, 0.0, 0.0); c = vec4(0.0, 0.55, 0.75, 0.7); }
  else if (k == 3) { a = vec4(0.380, 0.000, 0.030, 0.170); b = vec4(0.95, 1.00, 1.0, 0.0); c = vec4(0.0, 0.40, 0.40, 0.4); }
  else if (k == 4) { a = vec4(0.370, 0.030, 0.060, 0.150); b = vec4(1.05, 0.30, 0.0, 1.0); c = vec4(0.0, 0.65, 0.30, 0.3); }
  else             { a = vec4(0.300, 0.050, 0.010, 0.110); b = vec4(0.55, 0.05, 0.0, 0.0); c = vec4(1.0, 0.25, 0.00, 0.1); }
}

float folds(float u, float t, float f){
  return 0.55 * sin(u * 4.1 * f + t * 0.065) + 0.30 * sin(u * 7.3 * f - t * 0.10 + 1.3)
       + 0.15 * sin(u * 13.7 * f + t * 0.17 + 0.4);
}

// the hem of a curtain at ray coordinate u: a low arc or folded sheet, bending into a ring round the
// corona point as the corona comes
float hem(float u, float t, vec4 a, vec4 c, float co, float drift, float ring, float fade){
  float arc = a.x + a.y * (1.0 - u * u * 4.0) + a.z * folds(u + drift, t, 1.0 + 0.15 * iEvolve.x)
            + c.w * 0.006 * sin(u * 31.0 - t * 1.3);
  float cor = 1.08 - ring / sqrt(1.0 + u * u / 0.4) + a.z * fade * folds(u * 0.7 + drift, t, 1.0);
  return mix(arc, cor, co);
}

float rays(float u, float t, float d){
  return 0.5 + 0.5 * (0.5 * sin(u * 41.0 * d + t * 0.23 + 2.0 * sin(u * 7.0 - t * 0.05))
                    + 0.3 * sin(u * 89.0 * d - t * 0.31 + 1.7) + 0.2 * sin(u * 157.0 * d + t * 0.17));
}

// one curtain: returns its light, and its height above the hem in hh
float curtain(float x, float y, float t, vec4 a, vec4 b, vec4 c, float drift, float ring, float soft, out float hh){
  float co = b.z;
  float P = mix(1.0, max(1.08 - y, 0.02) / 0.63, co);   // perspective: vertical rays tilt to converge overhead
  float u = x / P;
  float fade = smoothstep(0.18, 0.55, P);               // rays wash into a soft glow where they converge
  float c0 = hem(u, t, a, c, co, drift, ring, fade);
  float e = 0.006;
  float cp = (hem(u + e, t, a, c, co, drift, ring, fade) - c0) / e;
  float h = y - c0;
  hh = h;
  float rn = rays(u + drift * 0.3, t, 1.0 + 0.2 * iEvolve.y);
  float R = b.y * mix(1.0, fade, co);
  float H = a.w * (0.75 + 0.6 * rn * R);                 // the rays reach up to different heights
  float below = exp(-h * h / (0.00016 + 0.006 * b.w + soft)); // patches spill below the hem
  float above = exp(-max(h, 0.0) / H) * (0.72 + 0.28 * exp(-max(h, 0.0) / 0.018));
  float prof = h < 0.0 ? below : above;
  float m = mix(1.0, 0.70 + 0.65 * rn, R * smoothstep(0.0, 0.12, h));   // a solid band above the hem, rays above it
  float edgeOn = 1.0 + 0.5 * min(cp * cp * 12.0, 1.0); // brighter where the sheet folds edge-on
  return b.x * prof * m * edgeOn;
}

void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float x = (uv.x - 0.5) * iResolution.x / iResolution.y, y = uv.y;
  float t = iTime;

  float p = fract(iClock) * 6.0;                         // where we are in the hour, 0..6
  int k = int(floor(p));
  float s = smoothstep(0.15, 1.0, fract(p));             // rest a moment, then flow into the next
  vec4 a0, b0, c0, a1, b1, c1;
  stage(k, a0, b0, c0);
  stage(k == 5 ? 0 : k + 1, a1, b1, c1);
  vec4 a = mix(a0, a1, s), b = mix(b0, b1, s), c = mix(c0, c1, s);
  b.x *= 1.0 + 0.06 * iBreath;

  // the mountains
  float ridge = 0.165 + 0.045 * sin(x * 4.3 + 0.8 + 0.4 * iEvolve.w) + 0.022 * sin(x * 9.7 + 2.1)
              + 0.009 * sin(x * 23.0 + 0.3) + 0.004 * sin(x * 51.0);
  float land = smoothstep(0.002, -0.002, y - ridge);

  // the sky: near-black night, the first blue of dawn rising from the horizon
  float above = max(y - ridge, 0.0);
  vec3 col = iColA * (0.10 + 0.08 * (1.0 - y));
  float sky = max(y - 0.15, 0.0);                        // level contours: the dawn lies flat behind the ridge
  col += iColA * 2.9 * sqrt(c.x) * exp(-sky / (0.02 + 0.24 * c.x));   // climbing from the ridge
  col += iColC * 0.10 * c.x * exp(-sky / 0.05);

  // the two curtains, the far one higher, fainter and drifting the other way
  float drift = t * 0.008;
  float h1, h2;
  float L1 = curtain(x, y, t, a, b, c, drift, 0.62, 0.0, h1);
  vec4 a2 = a; a2.x += 0.10; a2.z *= 0.8; a2.w *= 0.8;
  float L2 = 0.0; h2 = 1.0;
  if (c.z > 0.001) L2 = c.z * 0.5 * curtain(x + 0.21, y, t * 0.8, a2, b, c, -drift * 0.7 + 3.0, 0.50, 0.004, h2);

  // patches: the sheet gathers into soft pools of light along its hem, each pulsing at its own pace
  float xx = x + t * 0.006, cell = floor(xx / 0.2), pools = 0.0;
  if (b.w > 0.001) for (int i = -1; i <= 1; i++) {
    float id = cell + float(i), hs = hash(vec2(id, 7.3));
    float cx = (id + 0.5 + 0.5 * (hs - 0.5)) * 0.2 + 0.03 * sin(t * 0.07 + hs * 9.0);
    float w = 0.055 + 0.03 * hash(vec2(id, 2.1));
    float hc = 0.025 + 0.035 * hash(vec2(id, 5.7)) + 0.012 * sin(t * 0.11 + id);
    float pu = 0.5 + 0.5 * sin(t * (0.35 + 0.35 * hs) + hs * 6.28 + 2.0 * iEvolve.z);
    float dx = (xx - cx) / w, dh = (h1 - hc) / (0.035 + 0.015 * hs);
    pools += (0.55 + 0.6 * pu) * exp(-dx * dx - dh * dh);
  }
  L1 = mix(L1, b.x * 1.25 * pools + 0.2 * L1, b.w);
  L2 *= 1.0 - 0.8 * b.w;

  vec3 tint1 = mix(iColB, iColC, 0.75 * exp(-abs(h1) / 0.02));
  tint1 = mix(tint1, mix(iColB, iColA * 2.2, 0.65), smoothstep(0.04, 0.32, h1));
  vec3 tint2 = mix(iColB, iColA * 2.2, 0.35 + 0.5 * smoothstep(0.0, 0.25, h2));
  vec3 aur = tint1 * L1 + tint2 * L2;
  aur += iColC * 0.45 * max(L1 - 0.85, 0.0) * (1.0 - 0.7 * b.w);             // the hottest light whitens
  float glow = b.x * (1.0 - 0.5 * b.w);
  aur += iColB * 0.07 * glow * smoothstep(0.85, 0.25, y);  // the sky lit by it

  // stars, dimmed under the lights and at dawn
  vec2 g = fc / 9.0, id = floor(g);
  float hs = hash(id);
  vec2 sp = vec2(hash(id + 0.37), hash(id + 1.91)) * 0.6 + 0.2;
  vec2 sd = (fract(g) - sp) * 9.0;
  float star = step(0.955, hs) * exp(-dot(sd, sd) / 0.55) * (0.7 + 0.3 * sin(t * (0.8 + 2.0 * hs) + hs * 40.0));
  star *= c.y * clamp(1.0 - 1.4 * (L1 + L2), 0.0, 1.0) * smoothstep(0.0, 0.03, above);
  col += iColC * 1.3 * star;

  col += aur * (1.0 - land);

  // the mountains: dark, the ridge catching the glow of the sky
  float rimLight = clamp(0.62 + 0.3 * glow * (1.0 - 0.6 * b.z) + 0.8 * c.x, 0.0, 1.0);
  vec3 ground = iColA * 0.10;
  col = mix(col, ground, land);
  col += mix(iColB, iColC, 0.5) * rimLight * 0.75 * exp(-pow((y - ridge + 0.004) / 0.005, 2.0));
  o = vec4(col, 1.0);
}
