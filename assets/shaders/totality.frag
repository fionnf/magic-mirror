// Totality: a total solar eclipse danced once round the clock face every hour - the sun alone and glowing, the dark moon sliding across it to a pearly corona and back.
// :00 the sun hangs alone, gently glowing. :05 the dark moon arrives from the upper right and takes a
// bite, by :13 a broad crescent sun with the moon's silhouette standing in its glow. :20 only a thin
// crescent is left, and at :24 it shrinks to a single bead - the diamond ring flashes, a thin red rim
// of chromosphere beside it. :26 to :34 totality: a black disc in a pearly corona, two long streamers
// and fine plumes drifting slowly outward, a few red prominences licking the edge. :36 the second
// diamond ring flashes on the other side, :40 a thin crescent reopens there, :47 a broad crescent,
// and by :55 the moon has slid away to the lower left and the full sun glows alone again.
// Lit as eclipse light, kept soft for a room: a warm white disc darkening to gold at the limb, a glow
// that hugs whatever is left of the sun and dims the room as the sun narrows, a pearl-white corona
// cooling to blue at its tips, the prominences and flash rim in the deep red.
float ease(float a, float b, float m){ return smoothstep(a, b, m); }

// where the moon is, in sun radii along its path, at minute m of the hour (rests at every stage)
float moonAt(float m){
  float o = 3.2;
  o = mix(o, 1.35, ease(5.0, 13.0, m));       // arrives, takes a bite
  o = mix(o, 0.30, ease(13.0, 20.0, m));      // the bite deepens to a thin crescent
  o = mix(o, 0.13, ease(20.0, 24.0, m));      // the diamond ring
  o = mix(o, 0.03, ease(24.0, 27.0, m));      // totality
  o = mix(o, -0.03, ease(27.0, 33.0, m));
  o = mix(o, -0.13, ease(33.0, 36.0, m));     // the second diamond ring
  o = mix(o, -0.30, ease(36.0, 40.0, m));     // the crescent reopens on the other side
  o = mix(o, -1.35, ease(40.0, 47.0, m));
  o = mix(o, -3.2, ease(47.0, 55.0, m));      // slides away
  return o;
}

// how much of the sun's face is still showing (sun radius 1, moon radius rm, centres d apart)
float showing(float d, float rm){
  d = abs(d);
  if (d >= 1.0 + rm) return 1.0;
  if (d <= rm - 1.0) return 0.0;
  float a1 = acos(clamp((d * d + 1.0 - rm * rm) / (2.0 * d), -1.0, 1.0));
  float a2 = acos(clamp((d * d + rm * rm - 1.0) / (2.0 * d * rm), -1.0, 1.0));
  float k = (-d + 1.0 + rm) * (d + 1.0 - rm) * (d - 1.0 + rm) * (d + 1.0 + rm);
  float lens = a1 + rm * rm * a2 - 0.5 * sqrt(max(k, 0.0));
  return 1.0 - lens / 3.14159;
}

float wrapA(float a){ return atan(sin(a), cos(a)); }

void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  float px = 1.0 / min(iResolution.x, iResolution.y);
  float t = iTime;
  float m = fract(iClock) * 60.0;                       // minute of the hour
  float R = 0.17, RM = 1.065;                           // sun radius; the moon is a touch larger
  float off = moonAt(m);
  float ao = abs(off);
  vec2 dir = normalize(vec2(1.0, 0.42));
  vec2 mc = dir * off * R;                              // the moon's centre
  float here = smoothstep(3.15, 2.7, ao);               // far off the moon is nothing at all (the loop seam)

  float r = length(uv), a = atan(uv.y, uv.x), rr = r / R;
  float dSun = r - R;
  float dMoon = length(uv - mc) - RM * R;
  float occ = mix(1.0, smoothstep(-px, px, dMoon), here);          // 1 where the moon is not in the way
  float vis = showing(off, RM);                                      // fraction of the sun still showing
  float dvis = max(dSun, -dMoon * here - (1.0 - here));              // distance to what is left of the sun

  float corA = smoothstep(0.38, 0.05, ao) * here;                    // the corona comes out as the glare goes
  float flash = smoothstep(0.34, 0.08, ao) * here;                   // red limb and prominences
  float bead = smoothstep(0.05, 0.10, ao) * smoothstep(0.30, 0.12, ao) * here;   // the diamond ring

  vec3 warm = iColC * iColC;                                         // the palette's light, warmer
  vec3 col = iColA * 0.05;

  // the glow round whatever is left of the sun, dimming the room as the sun narrows
  float g = max(dvis, 0.0);
  float glow = (0.55 * exp(-g / 0.03) + 0.16 * exp(-g / 0.12)) * pow(vis, 0.55) * (1.0 + 0.06 * sin(t * 0.4) + 0.08 * iBreath);
  col += warm * glow * occ;

  // the corona: two long streamers and fine plumes, pearl white cooling to blue, drifting outward
  float ax = 0.45 + 0.5 * iEvolve.x;
  float eq = pow(abs(cos(a - ax)), 5.0);
  float fine = 0.5 + 0.25 * sin(a * 11.0 + 1.5 * sin(a * 5.0 + 0.3 * iEvolve.y) + t * 0.02)
                   + 0.25 * sin(a * 17.0 - 2.0 * sin(a * 3.0) - t * 0.015);
  float w = 0.16 + (0.55 + 0.15 * iEvolve.z) * eq + 0.22 * fine * (1.0 - eq) + 0.03 * iBreath;
  float h = max(rr - 1.0, 0.0);
  float stream = 0.94 + 0.06 * sin(h * 9.0 - t * 0.25 + 3.0 * fine);
  float cor = pow(exp(-h / w), 0.7) * (0.7 + 0.3 * fine) * stream * step(1.0, rr);
  vec3 pearl = mix(iColC, iColB, smoothstep(0.1, 1.3, h));
  col += pearl * cor * 1.2 * corA * occ;

  // the chromosphere: a thin red rim just outside the limb, seen only beside the moon's edge
  float rim = exp(-pow((rr - 1.02) / 0.035, 2.0));
  col += (iColA * 2.8 + iColC * 0.06) * rim * flash * occ;

  // prominences: two leaning tongues and one arch of red gas on the limb
  float pr = 0.0;
  for (int i = 0; i < 2; i++) {
    float a0 = (i == 0 ? 2.35 : 5.2) + 0.25 * iEvolve.w * (i == 0 ? 1.0 : -1.0);
    float ht = i == 0 ? 0.3 : 0.22;
    float da = wrapA(a - a0) + h * (i == 0 ? 1.2 : -0.9) * (1.0 + 0.2 * sin(t * 0.05 + float(i)));
    pr += exp(-pow(da / (0.11 * (1.0 - 0.6 * h / ht)), 2.0)) * smoothstep(ht, ht * 0.4, h);
  }
  float a2 = 0.95 - 0.2 * iEvolve.w;
  vec2 foot = vec2(cos(a2), sin(a2)) * R;
  float arch = abs(length(uv - foot) - 0.2 * R) - 0.025 * R;
  pr += smoothstep(0.012 * R + px, 0.0, arch) * step(1.0, rr) * 0.9;
  col += (iColA * 3.2 + iColC * 0.08 * exp(-h / 0.04)) * min(pr, 1.0) * flash * occ * step(1.0, rr);

  // the sun's face: warm white darkening to gold at the limb, a faint slow stir of the surface
  float mu = sqrt(max(1.0 - rr * rr, 0.0));
  float limb = 0.74 + 0.26 * mu;
  float stir = 0.015 * sin(uv.x * 23.0 + sin(uv.y * 19.0 + t * 0.05) * 1.5 + t * 0.04);
  vec3 face = mix(warm * 0.95, iColC, mu) * (limb + stir) * 0.97;
  float disc = smoothstep(px, -px, dSun) * occ;
  col = mix(col, face, disc);

  // the moon itself is black: nothing of the sun shows through it
  col *= mix(1.0, 1.0 - smoothstep(px, -px, dMoon) * 0.9, here);

  // the diamond ring: one bead of the sun with a soft starburst, spilling over the moon's edge
  vec2 bp = -dir * (off < 0.0 ? -1.0 : 1.0) * R;
  vec2 q = uv - bp;
  float db = length(q);
  float spikes = (exp(-abs(q.x + q.y) / (0.006 + 0.03 * db)) + exp(-abs(q.x - q.y) / (0.006 + 0.03 * db))) * exp(-db / 0.07);
  col += iColC * bead * (1.2 * exp(-pow(db / 0.016, 2.0)) + 0.5 * exp(-db / 0.05) + 0.35 * spikes);

  o = vec4(col, 1.0);
}
