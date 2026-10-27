// Contours: fine topographic lines in one hue family, drawn around two slow-moving peaks, so the
// map redraws itself over minutes. The bass raises the ground; treble thins the lines.
// Over tens of minutes the land changes: a third summit rises and sinks away, the peaks grow
// sharp or broad, the ground turns from smooth hills to rough country, and the lines crowd
// together or open out.
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.01;
  vec4 e = iEvolve;
  vec2 p1 = vec2(0.25 * sin(t), 0.15 * cos(t * 0.8)), p2 = vec2(-0.3 * cos(t * 0.6), -0.2 * sin(t * 0.5));
  vec2 p3 = vec2(0.15 * cos(t * 0.4 + 1.0), 0.32 * sin(t * 0.3 + 2.0));
  float sharp = 4.0 + 2.5 * e.x;
  float h = 0.8 * exp(-dot(uv - p1, uv - p1) * sharp) + 0.6 * exp(-dot(uv - p2, uv - p2) * (sharp + 2.0));
  h += 0.55 * smoothstep(-0.3, 0.8, e.w) * exp(-dot(uv - p3, uv - p3) * 9.0);   // the third summit
  float rough = 0.25 + 0.12 * e.z;
  h += rough * noise(uv * (3.0 + e.z) + t) + 0.1 * noise(uv * 7.0 - t * 0.5) + 0.012 * iBreath;
  float levels = 20.0 + 5.0 * e.y;
  float f = fract(h * levels);
  float w = 0.08 - 0.015 * iBright;
  float line = 1.0 - smoothstep(0.0, w * 1.5, min(f, 1.0 - f));
  float major = step(0.5, fract(floor(h * levels) / 5.0 + 0.01)) ;
  vec3 ground = mix(iColA, iColB, h * 0.55);
  vec3 ink = mix(iColB, iColC, 0.5 + 0.5 * h);
  vec3 col = mix(ground, ink, line * (0.55 + 0.45 * (1.0 - major)));
  col *= 1.0 - 0.3 * dot(uv, uv);
  col += (hash(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
