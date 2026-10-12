// Escape: two dark slabs in front of a lit wall, the light escaping in the gap between them and
// around their edges. The gap opens and closes over minutes; the bass pushes more light through.
float sdBox(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.012;
  float gap = 0.035 + 0.03 * (0.5 + 0.5 * sin(t)) + 0.02 * iBreath;
  float tilt = 0.08 * sin(t * 0.6);
  mat2 R = mat2(cos(tilt), -sin(tilt), sin(tilt), cos(tilt));
  vec2 p = R * uv;
  float d1 = sdBox(p - vec2(-0.27 - gap * 0.5, 0.0), vec2(0.27, 0.42), 0.03);
  float d2 = sdBox(p - vec2(0.27 + gap * 0.5, 0.03), vec2(0.27, 0.4), 0.03);
  float d = min(d1, d2);
  vec3 wall = iColA * 0.7 + iColB * 0.2 * exp(-length(uv) * 2.0);
  float leak = exp(-max(d, 0.0) * 22.0);
  vec3 col = wall + iColC * leak * 0.95 + iColB * exp(-max(d, 0.0) * 7.0) * 0.5;
  col = mix(col, iColA * 0.3, smoothstep(0.004, -0.004, d));
  col += (hash(fc) - 0.5) * 0.02;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
