// Dot sphere: a lattice of light points wrapped round a softly deformed, slowly turning sphere
// on black, with a faint glow; the deformation breathes with the bass.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.03;
  float ang = atan(uv.y, uv.x);
  float R = 0.37 + 0.012 * iBreath + 0.03 * sin(ang * 3.0 + t * 2.0) + 0.02 * sin(ang * 5.0 - t * 1.4);
  float r = length(uv) / R;
  vec3 col = iColA * 0.3;
  if (r < 1.0) {
    float z = sqrt(1.0 - r * r);
    vec3 n = vec3(uv / R, z);
    float lon = atan(n.x, n.z) + t, lat = asin(clamp(n.y, -1.0, 1.0));
    vec2 cell = fract(vec2(lon * 9.0, lat * 11.0)) - 0.5;
    float d = smoothstep(0.32, 0.12, length(cell));
    vec3 c = mix(iColB, iColC, smoothstep(-0.7, 0.9, n.y + 0.4 * n.x));
    col += c * d * (0.45 + 0.75 * z) + c * 0.08 * z;
  }
  col += mix(iColB, iColC, 0.5) * 0.12 * exp(-pow(max(r - 1.0, 0.0) * 6.0, 2.0)) * step(1.0, r);
  o = vec4(col, 1.0);
}
