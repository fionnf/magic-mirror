// Tide: soft horizontal bands breathing in and out, like light on a slow sea.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.06;
  float w = sin(uv.y*9.0 + t + sin(uv.x*3.0 + t*0.7)*0.8) * 0.5 + 0.5;
  float w2 = sin(uv.y*23.0 - t*1.3 + sin(uv.x*5.0 - t*0.5)*0.6) * 0.5 + 0.5;
  float v = smoothstep(0.2, 0.9, w*0.7 + w2*0.3);
  vec3 col = mix(iColA, iColB, v);
  col = mix(col, iColC, pow(v, 5.0) * 0.5 * (0.7 + 0.3*iEnergy));
  o = vec4(col, 1.0);
}
