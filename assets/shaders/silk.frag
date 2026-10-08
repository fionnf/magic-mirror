// Silk: slow domain-warped flow, like fabric drifting under water. Two hues.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(hash(i), hash(i+vec2(1,0)), f.x), mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), f.x), f.y); }
float fbm(vec2 p){ float v = 0.0, a = 0.5; for (int i = 0; i < 5; i++){ v += a*noise(p); p = p*2.03 + 1.7; a *= 0.5; } return v; }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution.y;
  float t = iTime * 0.045;
  vec2 q = vec2(fbm(uv*1.6 + t), fbm(uv*1.6 - t*0.7 + 3.1));
  vec2 r = vec2(fbm(uv*1.6 + 2.5*q + t*0.6), fbm(uv*1.6 + 2.5*q - t*0.4 + 8.2));
  float v = fbm(uv*1.6 + 3.0*r + 0.3*iBass);
  v = smoothstep(0.15, 0.85, v);
  vec3 col = mix(iColA, iColB, v);
  col = mix(col, iColC, smoothstep(0.75, 1.0, v) * 0.7);
  o = vec4(col, 1.0);
}
