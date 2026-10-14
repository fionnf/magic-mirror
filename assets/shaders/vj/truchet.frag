// Truchet (music): GPU port of shapes.Truchet. 16 px tiles each holding two quarter-circle arcs
// (radius 8) in one of two orientations; every tile flips at its own slow rate, so long ribbons
// keep re-forming. Each tile has a fixed grey level, mapped through the scene palette as the CPU
// path does. A flip cross-fades over a moment instead of popping. The bass swells the ribbons.
// Unlike the CPU piece (which leaves the lower rows of a tall wall empty) it fills any wall.
vec3 pal(float v){
  float i = clamp(v, 0.0, 1.0) * 255.0;
  if (i < 25.0) return mix(iColA * 0.55, iColA, i / 25.0);
  if (i < 140.0) return mix(iColA, iColB, (i - 25.0) / 115.0);
  return mix(iColB, iColC, (i - 140.0) / 105.0);
}
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
vec2 lineProf(float d, float hw){
  float ad = abs(d);
  float core = clamp(hw + 0.5 - ad, 0.0, 1.0);
  float e = max(ad - (hw - 0.65), 0.0);
  float glow = 0.28 * (1.0 + 1.2 * (hw - 0.65)) * exp(-e * e / 2.88);
  return vec2(core, glow);
}
// distance to the two arcs of a tile in orientation f (local coords q in 0..T)
float arcs(vec2 q, float T, float f){
  float h = T * 0.5;
  float d1, d2;
  if (f > 0.5) { d1 = abs(length(q) - h);                 d2 = abs(length(q - vec2(T)) - h); }
  else         { d1 = abs(length(q - vec2(T, 0.0)) - h);  d2 = abs(length(q - vec2(0.0, T)) - h); }
  return min(d1, d2);
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 R = iResolution;
  vec2 p = vec2(fc.x - 0.5, R.y - fc.y - 0.5);            // CPU pixel coords, y down
  float T = 16.0;
  float hw = 0.65 + 0.75 * iBass + 0.1 * iEnergy;
  vec2 ij = floor(p / T);
  vec2 q = p - ij * T;
  float ph = hash(ij), rate = 0.01 + 0.03 * hash(ij + 17.3);
  float c = ph * 1000.0 + iTime * rate * 12.0;
  float now = mod(floor(c), 2.0), before = 1.0 - now;
  float fade = smoothstep(0.0, 0.05, fract(c));            // a quick cross-fade on each flip
  vec2 a = lineProf(arcs(q, T, now), hw), b = lineProf(arcs(q, T, before), hw);
  vec2 l = mix(b, a, fade);
  float v = 0.2 + 0.7 * mod(ij.x * 7.0 + ij.y * 3.0, 10.0) / 10.0;
  float field = clamp((0.85 * l.x + l.y) * v * 1.1, 0.0, 1.0);
  o = vec4(pal(field), 1.0);
}
