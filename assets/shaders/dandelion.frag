// Dandelion: a glowing seed head of fine radial lines, each tipped with a point of light, turning
// imperceptibly. Through the day a few seeds drift off (iClock); treble makes the tips sparkle.
// Over tens of minutes the head changes: full and round or thinned and ragged, an inner crown of
// shorter seeds opening and closing, the stems straight or gently curled, the heart bright or dim.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
vec3 head(vec2 uv, float N, float L0, float rag, float curl, float density, float rot, float layer){
  float r = length(uv), a = atan(uv.y, uv.x) + rot + curl * r * r * 3.0;
  float sector = 6.2832 / N;
  float k = floor(a / sector + 0.5);
  float da = (a - k * sector) * r;                        // distance across the stem, in wall units
  float id = mod(k, N) + layer * 97.0;
  float here = smoothstep(density + 0.08, density - 0.08, hash(id * 3.7));         // thinned seeds fade
  float gone = layer > 0.5 ? 0.0 : step(hash(id * 2.1) * 24.0, iClock - 6.0);       // this seed has flown
  float L = L0 * (1.0 + rag * (hash(id) - 0.5));
  float stem = smoothstep(0.0065, 0.0015, abs(da)) * smoothstep(L + 0.004, L - 0.01, r) * smoothstep(0.03, 0.09, r);
  float tip = exp(-pow((r - L) / 0.016, 2.0)) * smoothstep(0.012, 0.0, abs(da)) * (0.85 + 0.4 * iBright * hash(id + floor(iTime * 0.2)));
  float keep = here * (1.0 - gone);
  return vec3(stem * keep, tip * keep, gone * here);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.01;
  vec4 e = iEvolve;
  float r = length(uv);
  float density = 0.82 + 0.16 * e.x;                       // the share of seeds still on the head
  vec3 outer = head(uv, 56.0, 0.33 + 0.02 * e.z, 0.12 + 0.18 * (0.5 + 0.5 * e.y), 0.06 * e.w, density, t * 0.3, 0.0);
  float crown = smoothstep(-0.2, 0.7, e.z);                // an inner crown of short seeds
  vec3 inner = head(uv, 40.0, 0.12 + 0.11 * crown, 0.2, -0.05 * e.w, 0.7, -t * 0.2 + 0.05, 1.0);
  vec3 col = iColA * 0.7 + iColB * (0.38 + 0.12 * e.y) * exp(-r * r * 7.0);
  col += iColB * outer.x * 0.95 + iColC * outer.y;
  col += (iColB * inner.x * 0.8 + iColC * inner.y * 0.8) * crown;
  // the seeds that flew drift outward as single points of light
  float a = atan(uv.y, uv.x) + t * 0.3;
  float sector = 6.2832 / 56.0, k = floor(a / sector + 0.5);
  float away = iClock - 6.0 - hash(mod(k, 56.0) * 2.1) * 24.0;
  vec2 fly = vec2(cos(k * sector - t * 0.3), sin(k * sector - t * 0.3)) * (0.33 + away * 0.03);
  float fd = length(uv - fly);
  col += iColC * 0.5 * step(0.0, away) * exp(-fd * fd * 4000.0) * step(length(fly), 0.75);
  col += iColC * exp(-r * r * (260.0 - 120.0 * e.w)) * 0.7;      // the heart
  o = vec4(min(col, vec3(1.0)), 1.0);
}
