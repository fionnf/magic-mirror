// Point cloud: a sphere made only of points of light, turning imperceptibly, the near points
// brighter than the far ones. The bass breathes its radius; treble makes the points sharper.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02;
  float R = 0.36 + 0.03 * iBreath;
  vec3 col = iColA * 0.55 + iColB * 0.2 * exp(-dot(uv, uv) * 5.0);
  float sharp = 3600.0 + 1500.0 * iBright;
  for (int i = 0; i < 64; i++) {
    float fi = float(i);
    float y = 1.0 - 2.0 * (fi + 0.5) / 64.0;                       // fibonacci sphere
    float rr = sqrt(1.0 - y * y);
    float th = fi * 2.399963 + t;
    vec3 q = vec3(cos(th) * rr, y, sin(th) * rr);
    float tilt = 0.4; q.yz = mat2(cos(tilt), -sin(tilt), sin(tilt), cos(tilt)) * q.yz;
    vec2 pt = q.xy * R;
    float depth = 0.5 + 0.5 * q.z;
    float d = dot(uv - pt, uv - pt);
    col += mix(iColB, iColC, depth) * (exp(-d * sharp) + 0.25 * exp(-d * 500.0)) * (0.2 + 0.8 * depth);
  }
  col += (hash(fc.x + fc.y * 777.0) - 0.5) * 0.02;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
