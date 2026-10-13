// Cross glow: four soft cushions of deep blue pressing together, light escaping along the seams
// between them as a glowing cross - violet near the centre, warming to gold at the far ends. The
// cushions breathe apart a little with the bass; the cross turns a few degrees over the day.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  float ang = 0.15 * sin(iClock * 0.26) + 0.04 * sin(iTime * 0.02);
  uv = mat2(cos(ang), -sin(ang), sin(ang), cos(ang)) * uv;
  vec2 q = abs(uv);
  float gap = 0.008 + 0.006 * iBreath;
  float seam = min(q.x, q.y);                              // distance to the cross
  float glow = exp(-seam / (0.02 + 0.06 * min(max(q.x, q.y), 0.6)));
  float cushion = smoothstep(0.0, 0.25, seam) * smoothstep(0.75, 0.2, max(q.x, q.y));
  float along = clamp(max(q.x, q.y) / 0.7, 0.0, 1.0);
  vec3 seamCol = mix(iColB, iColC, along);
  vec3 col = iColA * (0.25 + 0.6 * cushion) + seamCol * glow * (1.0 - 0.3 * along);
  col += vec3(1.0) * 0.4 * exp(-length(uv) / 0.03);       // a hot point where the seams meet
  o = vec4(col, 1.0);
}
