// Eclipse: a dark disc whose rim burns - a thin hot ring and a cool inner glow - on black; the
// ring's brightest point travels slowly round with the key, the corona breathes with the bass.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02;
  float r = length(uv), a = atan(uv.y, uv.x);
  float R = 0.33;
  float hot = 0.6 + 0.4 * cos(a - (t + iKey * 6.283) - 2.2);
  float ring = exp(-pow((r - R) / (0.012 + 0.006 * iBreath), 2.0)) * hot;
  float corona = exp(-max(r - R, 0.0) * (9.0 - 3.0 * iBreath)) * step(R, r) * (0.35 + 0.4 * hot);
  float inner = smoothstep(R, R * 0.2, r) * smoothstep(-0.9, 0.6, -uv.y * 1.2 + uv.x * 0.3);
  vec3 col = iColA * 0.15;
  col += iColB * corona * 0.8;
  col += mix(iColB, iColC, 0.6) * inner * 0.55 * step(r, R);
  col += iColC * ring;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
