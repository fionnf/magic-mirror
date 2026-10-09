// Cut paper: two flat colours in large interlocking curves, like a mid-century collage. The
// shapes shift very slowly; each song redraws them a little.
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.015 + iSong * 4.0;
  float a = step(length(uv - vec2(-0.55, 0.10 + 0.04 * sin(t))), 0.62 + 0.015 * iBreath);
  float b = step(length(uv - vec2(0.62, -0.05 + 0.04 * cos(t * 0.8))), 0.60);
  float c = step(uv.y, -0.18 + 0.22 * sin(uv.x * 2.0 + 0.7 + t * 0.5));
  float f = mod(a + b + c, 2.0);                 // alternate colour across every curve
  vec3 col = mix(iColC * 0.78, iColB, f);
  col *= 0.94 + 0.06 * (1.0 - length(uv));
  col += (grain(fc * 0.5) - 0.5) * 0.04;
  o = vec4(col, 1.0);
}
