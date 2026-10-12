// Threads: a fine cloth of thin lines, two layers at a slight angle, so a slow moiré wave rolls
// across the wall. One hue; the bass lets the cloth breathe; treble sharpens the weave.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02;
  float ang = 0.16 + 0.05 * sin(t * 0.5);
  mat2 R = mat2(cos(ang), -sin(ang), sin(ang), cos(ang));
  vec2 p1 = uv + 0.04 * vec2(sin(t), cos(t * 0.8));
  vec2 p2 = R * uv;
  float freq = 38.0 + 6.0 * iBright;
  float w = 0.62 - 0.08 * iBreath;
  float l1 = smoothstep(w, w + 0.2, 0.5 + 0.5 * sin(p1.y * freq + 2.0 * sin(p1.x * 2.0 + t)));
  float l2 = smoothstep(w, w + 0.2, 0.5 + 0.5 * sin(p2.x * freq * 1.03 - t * 2.0));
  float cloth = max(l1, l2) * 0.75 + l1 * l2 * 0.5;
  float field = 0.5 + 0.5 * sin(uv.x * 2.0 + t * 1.3) * sin(uv.y * 1.6 - t * 0.9);
  vec3 col = mix(iColA * 0.7, iColB, cloth * (0.5 + 0.5 * field));
  col = mix(col, iColC, l1 * l2 * field * 0.5);
  col *= 1.0 - 0.45 * dot(uv, uv);
  o = vec4(col, 1.0);
}
