// Topo: soft contour bands of a slow sand landscape, cream on dark earth, like raked sand or
// cut stone. The bass deepens the relief a little; the day's music raises its hills.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(hash(i), hash(i+vec2(1.0,0.0)), f.x), mix(hash(i+vec2(0.0,1.0)), hash(i+vec2(1.0,1.0)), f.x), f.y); }
float fbm(vec2 p){ float v = 0.0, a = 0.5; for (int i = 0; i < 4; i++){ v += a*noise(p); p = p*2.02 + 1.3; a *= 0.5; } return v; }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution.y;
  float t = iTime * 0.0035;
  float day = 0.0; for (int k = 0; k < 24; k++) day += iDay[k]; day /= 24.0;
  float h = fbm(uv * 1.3 + vec2(t, -t * 0.6)) * (1.0 + 0.08 * iBreath + 0.3 * day);
  float bands = fract(h * 8.0);
  float l = smoothstep(0.0, 0.08, bands) * smoothstep(0.42, 0.18, bands);     // soft ridge per band
  float region = smoothstep(0.42, 0.62, fbm(uv * 0.8 + 7.0 + t * 0.4));
  vec3 earth = mix(iColA, iColB, region * 0.7);
  vec3 col = mix(earth, iColC * mix(0.55, 0.85, region), l * mix(0.45, 0.85, region));
  o = vec4(col, 1.0);
}
