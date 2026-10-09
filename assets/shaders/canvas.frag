// Canvas: a tall gradient from deep blue to warm light with one soft orb low in the field.
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(39.3468, 11.135))) * 24634.6345); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.025;
  float y = uv.y + 0.06 * sin(uv.x * 2.2 + t) + 0.03 * sin(uv.x * 4.1 - t * 1.3);
  vec3 col = mix(iColC * 0.75, iColB, smoothstep(0.0, 0.55, y));
  col = mix(col, iColA, smoothstep(0.45, 1.0, y));
  vec2 orb = vec2(0.5 + 0.08 * sin(t * 0.8 + iSong * 6.283), 0.30 + 0.03 * sin(t));
  vec2 q = (uv - orb) * vec2(iResolution.x / iResolution.y, 1.0);
  float r = 0.10 + 0.025 * iBreath;
  float glow = exp(-dot(q, q) / (r * r));
  col = mix(col, iColC, glow * 0.75);
  col += (grain(fc) - 0.5) * 0.03;
  o = vec4(col, 1.0);
}
