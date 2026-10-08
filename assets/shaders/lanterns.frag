// Lanterns: a few soft glows drifting like paper lanterns on a dark pond.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5*iResolution) / iResolution.y;
  float t = iTime * 0.08;
  vec3 col = iColA;
  for (int i = 0; i < 6; i++){
    float fi = float(i);
    vec2 c = vec2(sin(t*(0.6+0.13*fi) + fi*1.9), cos(t*(0.5+0.11*fi) + fi*2.7)) * 0.42;
    float d = length(uv - c);
    float g = exp(-d*d*(14.0 - 4.0*sin(fi + t)));
    col += mix(iColB, iColC, 0.3 + 0.7*fract(fi*0.37)) * g * (0.35 + 0.15*iBass);
  }
  o = vec4(col, 1.0);
}
