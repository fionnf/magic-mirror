// Dot sea: a field of fine light points rolling in long slow swells, seen low across the water;
// near points large and bright, the far ones fading into dark blue, up to a glowing horizon high on
// the wall. The swell grows with the bass, and the sea rises and calms over the day.
// Over tens of minutes (iEvolve) the horizon rises and sinks, the swell builds from a calm into
// long rollers, the waves lengthen and shorten, and the points spread out or crowd together.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution;
  vec4 e = iEvolve;
  float t = iTime * 0.05;
  float calm = (0.6 + 0.4 * sin(iClock * 0.26)) * (1.0 + 0.55 * e.y);
  float horizon = 0.86 + 0.07 * e.x;                       // where the far rows end
  float wave = 1.0 + 0.35 * e.z;                           // longer .. shorter waves
  float spacing = 0.035 * (1.0 + 0.22 * e.w);
  vec3 col = vec3(0.0);
  for (int row = 0; row < 44; row++){
    float z = float(row) / 44.0;                           // 0 near .. 1 far
    float persp = mix(1.0, 0.16, z);
    float yb = mix(0.02, horizon, pow(z, 0.75));
    float xs = (uv.x - 0.5) / persp;
    float h = (sin(xs * 6.0 * wave + t + z * 7.0) * 0.6 + sin(xs * 13.0 * wave - t * 1.3 + z * 4.0) * 0.4) * 0.05 * persp * calm * (1.0 + 0.4 * iBreath);
    float y = yb + h;
    if (abs(uv.y - y) > 0.03) continue;                    // far from this row: skip the work
    float gx = fract(xs / spacing + z * 0.37) - 0.5;
    float d = length(vec2(gx * spacing * persp * iResolution.x, (uv.y - y) * iResolution.y));
    float r = mix(1.6, 0.55, z);
    float dot_ = smoothstep(r + 0.6, r - 0.4, d);
    vec3 c = mix(iColC, iColB, z) * mix(1.0, 0.45, z);
    col = max(col, c * dot_);
  }
  float sky = smoothstep(horizon - 0.02, horizon + 0.02, uv.y);
  col += iColB * 0.35 * exp(-abs(uv.y - horizon) * 28.0);  // the glow along the horizon
  col += mix(iColA * 0.25 * (1.0 - uv.y), iColA * 0.55 + iColB * 0.12 * (1.0 - uv.y), sky);
  o = vec4(col, 1.0);
}
