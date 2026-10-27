// Cross glow: four soft cushions of deep blue pressing together, light escaping along the seams
// between them as a glowing cross - violet near the centre, warming to gold at the far ends. The
// cushions breathe apart a little with the bass; the cross turns a few degrees over the day.
// Over tens of minutes (iEvolve) two more seams open and close (four cushions become six), the
// meeting point wanders off centre, the glow along the seams thickens and thins.
float seamDist(vec2 p, float n){                         // distance to the nearest of n seams
  float a = atan(p.y, p.x), s = 6.2832 / n;
  float da = abs(mod(a, s) - 0.5 * s);
  return length(p) * sin(0.5 * s - da);
}
void mainImage(out vec4 o, in vec2 fc){
  vec4 e = iEvolve;
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  uv -= vec2(0.08 * e.y, 0.1 * e.w);                       // the meeting point wanders
  float ang = 0.15 * sin(iClock * 0.26) + 0.04 * sin(iTime * 0.02) + 0.3 * e.z;
  uv = mat2(cos(ang), -sin(ang), sin(ang), cos(ang)) * uv;
  vec2 q = abs(uv);
  float far = max(q.x, q.y);
  float six = smoothstep(0.1, 0.8, e.x);                   // the extra seams fade in and out
  float seam4 = min(q.x, q.y);
  float seam6 = seamDist(uv, 6.0);
  float wid = 0.02 + 0.06 * min(far, 0.6);
  wid *= 1.0 + 0.45 * e.w;
  float glow = max(exp(-seam4 / wid) * (1.0 - six), exp(-seam6 / wid) * six);
  float seam = mix(seam4, seam6, six);
  float cushion = smoothstep(0.0, 0.25, seam) * smoothstep(0.75, 0.2, far);
  float along = clamp(mix(far, length(uv), six) / 0.7, 0.0, 1.0);
  vec3 seamCol = mix(iColB, iColC, along);
  vec3 col = iColA * (0.25 + 0.6 * cushion) + seamCol * glow * (1.0 - 0.3 * along);
  col += vec3(1.0) * 0.4 * exp(-length(uv) / (0.03 + 0.012 * e.z));   // a hot point where the seams meet
  o = vec4(col, 1.0);
}
