// Arches: flat cut-paper arches in two tones, one inside the other, slowly sliding apart and back
// like a colonnade seen from a moving train. The song re-seeds their widths.
// Over tens of minutes the colonnade changes: three to five arches (the innermost rising out of
// the floor and sinking back), thick bands or thin ones,
// tall narrow doorways or low wide ones, and the sliding grows from gentle to a clear sway.
float hash(float n){ return fract(sin(n * 91.7) * 43758.5453); }
float arch(vec2 p, float w, float h){                      // 0 inside a rounded-top arch
  float top = h - w;
  float dy = p.y < top ? 0.0 : length(vec2(p.x, p.y - top)) - w;
  float dx = abs(p.x) - w;
  return p.y < top ? max(dx, -p.y - 0.0) : dy;
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02;
  vec4 e = iEvolve;
  vec3 col = iColA;
  float seed = floor(iSong * 7.0);
  float n = 4.0 + 1.0 * e.x;                               // 3 .. 5 arches, the innermost fading in and out
  float stepW = 0.07 + 0.02 * e.y;                         // band thickness
  float stepH = 0.11 + 0.035 * e.z;                        // tall doorways .. low ones
  float sway = 0.035 * (1.0 + 0.35 * e.w);
  for (int i = 0; i < 5; i++) {
    float fi = float(i);
    float grow = clamp(n - fi, 0.0, 1.0);                  // a new arch rises out of the floor
    if (grow <= 0.0) break;
    float w = 0.36 - fi * (stepW + 0.01 * hash(seed + fi));
    float h = (0.64 - fi * stepH) * grow;
    if (w < 0.03) break;
    float sx = sway * sin(t * (0.7 + 0.2 * fi) + fi * 1.4) * fi;
    float d = arch(uv - vec2(sx, -0.45), w, h);
    vec3 tone = mod(fi, 2.0) < 1.0 ? iColB : iColC * 0.85;
    col = mix(col, tone, smoothstep(0.004, -0.004, d));
  }
  float floor_ = smoothstep(-0.44, -0.46, uv.y);
  col = mix(col, iColA * 0.6, floor_);
  o = vec4(col, 1.0);
}
