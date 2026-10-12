// Rain on glass: thin threads of light slide down very slowly, each a different length and pace,
// over a dark blurred window with a soft glow somewhere outside. Treble adds finer drops.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  float t = iTime * 0.04;
  vec3 col = iColA * 0.7 + iColB * 0.35 * exp(-length((uv - vec2(0.65, 0.6)) * vec2(1.0, 1.4)) * 2.5);
  float n = 22.0 + 8.0 * iBright;
  for (int i = 0; i < 30; i++) {
    float fi = float(i);
    if (fi >= n) break;
    float x = hash(fi * 3.1);
    float speed = 0.3 + 0.7 * hash(fi * 5.7);
    float len = 0.08 + 0.3 * hash(fi * 7.9);
    float y = fract(hash(fi * 2.3) - t * speed * 0.3);
    float dx = abs(uv.x - x) * iResolution.x / iResolution.y;
    float along = (uv.y - y) / len;
    float line = smoothstep(0.012, 0.0, dx) * step(0.0, along) * step(along, 1.0) * along * along;
    float drop = exp(-dot(vec2(dx, uv.y - y) * vec2(1.0, 1.0), vec2(dx, uv.y - y)) * 4000.0);
    col += iColC * (line * 0.45 + drop * 0.9) * (0.5 + 0.5 * hash(fi));
  }
  col *= 1.0 - 0.35 * dot(uv - 0.5, uv - 0.5);
  o = vec4(min(col, vec3(1.0)), 1.0);
}
