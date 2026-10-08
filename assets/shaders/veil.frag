// Ink veil: slow smoky volumes rising, one hue, very quiet.
float hash(vec2 p){ return fract(sin(dot(p, vec2(41.3, 289.1))) * 23758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(hash(i), hash(i+vec2(1,0)), f.x), mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), f.x), f.y); }
float fbm(vec2 p){ float v = 0.0, a = 0.55; for (int i = 0; i < 6; i++){ v += a*noise(p); p = p*2.1 + 4.2; a *= 0.5; } return v; }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution.y;
  float t = iTime * 0.03;
  vec2 p = uv * 2.2 + vec2(0.0, -t*1.4);
  float d = fbm(p + 0.6*fbm(p*0.7 + t));
  float v = smoothstep(0.35, 0.95, d) * (0.6 + 0.4*uv.y);
  vec3 col = mix(iColA, iColB, v);
  col += iColC * pow(v, 4.0) * 0.35;
  o = vec4(col, 1.0);
}
