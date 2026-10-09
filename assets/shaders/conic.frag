// Conic tiles: one conic gradient per panel of the wall, each sweeping once from its own
// corner (deep shadow, blue, a pale edge), so the seams fall exactly on the panel edges. The
// sweeps turn very slowly; the key leans them, each song re-deals the corners.
float h1(float n){ return fract(sin(n * 91.345) * 47453.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  vec2 cell = floor(uv * iPanels);
  vec2 p = fract(uv * iPanels);
  float id = cell.x + cell.y * iPanels.x;
  float t = iTime * 0.012;
  float corner = floor(h1(id + 3.0 + floor(iSong * 7.0)) * 4.0);
  vec2 c = vec2(mod(corner, 2.0), floor(corner / 2.0));
  vec2 q = abs(p - c);                                // the corner becomes the origin
  float k = atan(q.y, q.x) / 1.5708;                  // 0..1 across the quarter turn
  if (h1(id * 5.7) > 0.5) k = 1.0 - k;                // half the tiles sweep the other way
  k = clamp(k + 0.18 * sin(t * (0.6 + h1(id)) + id + iKey * 3.0), 0.0, 1.0);
  vec3 col = mix(iColA, iColB, smoothstep(0.05, 0.75, k));
  col = mix(col, iColC, smoothstep(0.78, 1.0, k) * (0.9 + 0.1 * iBreath));
  o = vec4(col, 1.0);
}
