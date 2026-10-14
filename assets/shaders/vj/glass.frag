// Stained glass (music): 22 drifting Voronoi cells, each a flat glowing tone brighter towards its
// centre, with dark lead lines - the GPU port of light_art.StainedGlass (same seeds, same drift) as
// music mode shows it (luminance through the scene palette). The bass makes the panes breathe:
// the cells push outward from the middle and their glow spreads.
const float BX[22] = float[22](0.8050,0.5153,0.0539,0.4085,0.0488,0.6524,0.4349,0.8977,0.3924,0.6767,0.5556,0.8797,0.6792,0.2273,0.8722,0.7075,0.5034,0.2033,0.8062,0.1490,0.4485,0.2355);
const float BY[22] = float[22](0.8079,0.2858,0.3834,0.0453,0.9992,0.2345,0.9742,0.8442,0.4930,0.0608,0.2715,0.0642,0.8701,0.8954,0.0185,0.0012,0.4367,0.3249,0.3165,0.6985,0.7989,0.3198);
const float P0[22] = float[22](5.0232,0.0913,2.3103,3.4927,4.2968,0.6725,5.0147,2.3894,6.2277,4.4770,3.0112,0.0058,5.8007,5.1700,5.3885,1.6211,5.4283,0.0172,5.5875,5.3930,3.7307,4.3791);
const float P1[22] = float[22](3.1844,5.8606,5.9724,1.5080,2.9128,4.3472,1.2185,4.4793,4.5447,5.3231,6.0195,2.6388,2.0558,0.9876,5.2049,3.0884,1.7502,1.2256,3.0175,2.1182,4.6313,0.0359);
const float P2[22] = float[22](3.1801,0.5390,2.5084,4.6561,1.3935,3.9902,2.4521,3.8466,5.0795,2.5197,1.9925,3.9654,6.2100,2.5440,0.8779,3.4741,2.8079,2.1457,2.8559,4.9842,3.1485,0.2453);
const float HU[22] = float[22](0.2136,0.2032,0.0490,0.2172,0.6009,0.8861,0.3495,0.3664,0.4167,0.6803,0.7853,0.9410,0.3757,0.7068,0.3416,0.8240,0.2306,0.8710,0.5051,0.7253,0.5350,0.3161);
vec3 pal(float s){                       // scene palette: iColA/B/C are LUT entries 25/140/245 of the
  vec3 s0 = 0.5 * iColA;                 // scene's 4-stop ramp; rebuild the 4 stops (within ~5%)
  vec3 s1 = s0 + (iColA - s0) / 0.2941;
  vec3 s2 = s1 + (iColB - s1) / 0.6471;
  vec3 s3 = s2 + (iColC - s2) / 0.8824;
  float x = clamp(s, 0.0, 1.0) * 3.0;
  vec3 c = x < 1.0 ? mix(s0, s1, x) : x < 2.0 ? mix(s1, s2, x - 1.0) : mix(s2, s3, x - 2.0);
  return clamp(c, 0.0, 1.0);
}
float jewelLum(float x){                 // luminance of the piece's own 'jewel' ramp
  x = clamp(x, 0.0, 1.0) * 3.0;
  return x < 1.0 ? mix(0.0316, 0.1727, x) : x < 2.0 ? mix(0.1727, 0.4235, x - 1.0) : mix(0.4235, 0.9067, x - 2.0);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 R = iResolution / 3.0;                        // the piece works on a 1/3-size grid
  vec2 p = vec2(fc.x - 0.5, iResolution.y - fc.y - 0.5) / 3.0;
  float t = iTime;
  float push = 0.025 * iBass + 0.01 * iEnergy;
  float d1 = 1e9, d2 = 1e9; int c = 0;
  for (int i = 0; i < 22; i++){
    vec2 s = vec2(BX[i] + 0.09 * sin(t * 0.11 + P0[i]), BY[i] + 0.09 * cos(t * 0.09 + P1[i]));
    s += (s - 0.5) * push * 2.0 + push * vec2(sin(t * 0.7 + P2[i] * 3.0), cos(t * 0.6 + P1[i] * 2.0));
    vec2 q = p - s * R;
    float d = dot(q, q);
    if (d < d1){ d2 = d1; d1 = d; c = i; } else if (d < d2){ d2 = d; }
  }
  float edge = clamp((sqrt(d2) - sqrt(d1)) / 1.7, 0.0, 1.0);          // 0 on the lead line
  edge = smoothstep(0.0, 1.0, edge);
  float v = fract(HU[c] + 0.12 * sin(t * 0.2 + P2[c]));
  float glow = 0.55 + 0.45 * exp(-d1 / (R.x * R.x * 0.012 * (1.0 + 0.9 * iBass)));
  float lum = jewelLum(v * 0.85 + 0.1) * edge * glow;
  o = vec4(pal(clamp(pow(lum, 0.85) * 1.15, 0.0, 1.0)), 1.0);
}
