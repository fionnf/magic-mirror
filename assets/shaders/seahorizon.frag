// Sea horizon: a flat sea, a flat sky and a sun that rises in the morning, stands high at noon and
// sinks at dusk (iClock), the sky's colour family following it. The bass lifts the swell.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.02;
  float sun = -0.25 + 0.75 * max(0.0, sin((iClock - 6.0) / 24.0 * 6.2832 * 0.5 * 2.0));   // up 6 .. 18
  float dayness = clamp(sun * 2.0 + 0.3, 0.0, 1.0);
  float horizon = -0.06;
  vec3 skyTop = mix(iColA, iColB, 0.45 * dayness);
  vec3 skyLow = mix(iColB, iColC, 0.5 * dayness);
  vec3 col = mix(skyLow, skyTop, smoothstep(horizon, 0.55, uv.y));
  vec2 sp = vec2(0.1 * sin(t * 0.1), horizon + sun * 0.5);
  float d = length(uv - sp);
  col = mix(col, iColC, smoothstep(0.07, 0.062, d) * step(horizon, sp.y + 0.06));
  col += iColB * 0.35 * exp(-d * 4.0) * step(0.0, sp.y - horizon + 0.1);
  if (uv.y < horizon) {
    float depth = horizon - uv.y;
    float swell = 0.5 + 0.5 * sin(uv.x * 30.0 + t * 1.5 + depth * 40.0) * sin(depth * 25.0 - t);
    vec3 sea = mix(iColA * 0.8, iColB, 0.3 + 0.3 * dayness);
    sea = mix(sea, iColC, 0.25 * swell * exp(-depth * 4.0) * exp(-pow((uv.x - sp.x) / 0.12, 2.0)) * dayness);
    sea *= 1.0 - 0.5 * depth;
    col = mix(col, sea, smoothstep(0.0, 0.006 + 0.004 * iBreath, depth));
  }
  col += (hash(fc) - 0.5) * 0.015;
  o = vec4(col, 1.0);
}
