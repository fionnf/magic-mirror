// Dunes: ridged noise lit from the side, creeping very slowly.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(hash(i), hash(i+vec2(1,0)), f.x), mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), f.x), f.y); }
float ridged(vec2 p){ float v = 0.0, a = 0.5; for (int i = 0; i < 5; i++){ v += a*(1.0 - abs(2.0*noise(p) - 1.0)); p = p*2.0 + 3.3; a *= 0.5; } return v; }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution.y;
  float t = iTime * 0.02;
  vec2 p = uv * 1.8 + vec2(t, t*0.3);
  float h = ridged(p);
  float hx = ridged(p + vec2(0.01, 0.0));
  float light = clamp(0.5 + 12.0*(hx - h), 0.0, 1.0);
  vec3 col = mix(iColA, iColB, h);
  col = mix(col, iColC, light * h * 0.6);
  o = vec4(col, 1.0);
}
