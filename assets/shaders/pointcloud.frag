// Point cloud: a sphere made only of points of light, turning imperceptibly, the near points
// brighter than the far ones. The bass breathes its radius; treble makes the points sharper.
// Over tens of minutes the sphere opens into a ring of points and closes back into a ball, it tips
// towards you and away, the points gather into bands or spread evenly, and they swell into soft
// lanterns or shrink to pinpricks.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  vec4 e = iEvolve;
  float t = iTime * 0.02;
  float R = 0.34 + 0.03 * iBreath;
  vec3 col = iColA * 0.55 + iColB * 0.2 * exp(-dot(uv, uv) * 5.0);
  float size = 1.0 + 0.45 * e.w;                                   // pinpricks .. lanterns
  float sharp = (3600.0 + 1500.0 * iBright) / (size * size);
  float torus = smoothstep(-0.1, 0.9, e.x);                        // ball .. ring
  float band = 0.5 * smoothstep(0.0, 0.9, e.y);                    // points gather into bands
  float tilt = 0.4 + 0.3 * e.z + 0.5 * torus;              // a ring is seen more from above
  float ct = cos(tilt), st = sin(tilt);
  for (int i = 0; i < 64; i++) {
    float fi = float(i);
    float y = 1.0 - 2.0 * (fi + 0.5) / 64.0;                       // fibonacci sphere
    y = mix(y, sign(y) * pow(abs(y), 0.55), band);
    float rr = sqrt(max(0.0, 1.0 - y * y));
    float th = fi * 2.399963 + t;
    vec3 qs = vec3(cos(th) * rr, y, sin(th) * rr);
    float phi = y * 3.14159;
    vec3 qt = vec3(cos(th) * (0.72 + 0.28 * cos(phi)), 0.28 * sin(phi), sin(th) * (0.72 + 0.28 * cos(phi)));
    vec3 q = mix(qs, qt, torus);
    q.yz = mat2(ct, -st, st, ct) * q.yz;
    vec2 pt = q.xy * R;
    float depth = 0.5 + 0.5 * q.z;
    float d = dot(uv - pt, uv - pt);
    col += mix(iColB, iColC, depth) * (exp(-d * sharp) + 0.25 * exp(-d * 500.0 / size)) * (0.2 + 0.8 * depth);
  }
  col += (hash(fc.x + fc.y * 777.0) - 0.5) * 0.02;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
