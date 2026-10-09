// Glass blob: a single soft glass form on black, its inside a slow swirl of the palette's tints
// with a bright rim; the swirl turns with the key, the form breathes with the bass.
float sdBlob(vec2 p, float t){ float a = atan(p.y, p.x);
  return length(p) - (0.33 + 0.035 * sin(a * 2.0 + t) + 0.025 * sin(a * 3.0 - t * 0.7)); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.05;
  uv *= 1.0 - 0.03 * iBreath;
  float d = sdBlob(uv, t);
  vec3 col = iColA * 0.2;
  if (d < 0.02) {
    float inside = smoothstep(0.02, -0.02, d);
    vec2 q = uv * 2.4;
    float sw = sin(q.x * 1.7 + sin(q.y * 2.3 + t) + iKey * 6.283) + sin(q.y * 1.3 - t * 0.6 + q.x);
    vec3 body = mix(iColB, iColC * 0.85, 0.5 + 0.35 * sw);
    body = mix(body, iColA, smoothstep(0.0, 0.35, length(uv - vec2(-0.08, 0.1))) * 0.35);
    float rim = smoothstep(-0.06, 0.0, d);
    float hi = exp(-pow(length(uv - vec2(-0.12, 0.16)) / 0.05, 2.0));
    col = mix(col, body + rim * iColC * 0.45 + hi * 0.25, inside);
  }
  o = vec4(col, 1.0);
}
