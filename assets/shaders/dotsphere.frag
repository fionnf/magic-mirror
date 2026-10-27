// Dot sphere: a lattice of light points wrapped round a softly deformed, slowly turning sphere
// on black, with a faint glow; the deformation breathes with the bass.
// Over tens of minutes the body goes from nearly round to clearly lobed (two to five swells), it
// squashes and tips, the lattice grows finer or coarser, and the points gather into bands of
// latitude or spread evenly again.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  vec4 e = iEvolve;
  float t = iTime * 0.03;
  vec2 q = uv * vec2(1.0 + 0.1 * e.x, 1.0 - 0.1 * e.x);
  float ang = atan(q.y, q.x);
  float k = 3.5 + 1.5 * e.z;                            // 2 .. 5 swells
  float lob = mix(sin(ang * floor(k) + t * 2.0), sin(ang * (floor(k) + 1.0) - t * 1.4), smoothstep(0.0, 1.0, fract(k)));
  float R = 0.33 + 0.012 * iBreath + (0.015 + 0.03 * (0.5 + 0.5 * e.y)) * lob;
  float r = length(q) / R;
  vec3 col = iColA * 0.3;
  if (r < 1.0) {
    float z = sqrt(1.0 - r * r);
    vec3 n = vec3(q / R, z);
    float tilt = 0.4 * e.w;
    n.yz = mat2(cos(tilt), -sin(tilt), sin(tilt), cos(tilt)) * n.yz;
    float lon = atan(n.x, n.z) + t, lat = asin(clamp(n.y, -1.0, 1.0));
    float dens = 1.0 + 0.22 * e.x;                       // finer .. coarser lattice
    vec2 cell = fract(vec2(lon * 9.0 * dens, lat * 11.0 * dens)) - 0.5;
    float d = smoothstep(0.32, 0.12, length(cell));
    float bands = mix(1.0, 0.25 + 0.75 * smoothstep(0.2, 0.9, 0.5 + 0.5 * cos(lat * 7.0 + t)), smoothstep(0.0, 0.9, e.y));
    vec3 c = mix(iColB, iColC, smoothstep(-0.7, 0.9, n.y + 0.4 * n.x));
    col += c * d * bands * (0.45 + 0.75 * z) + c * 0.08 * z;
  }
  col += mix(iColB, iColC, 0.5) * 0.12 * exp(-pow(max(r - 1.0, 0.0) * 6.0, 2.0)) * step(1.0, r);
  o = vec4(col, 1.0);
}
