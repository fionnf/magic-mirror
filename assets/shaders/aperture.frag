// Aperture: nested soft rectangles of light around a deep, dark centre, like looking into a
// glowing frame; the opening breathes with the bass and its tint drifts with the key.
float sdBox(vec2 p, vec2 b){ vec2 q = abs(p) - b; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0); }
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.012;
  float d = sdBox(uv, vec2(0.10 + 0.015 * iBreath, 0.16 + 0.015 * iBreath));
  float k = smoothstep(-0.05, 0.45, d);                 // 0 in the centre .. 1 at the edge
  float shift = 0.08 * sin(t + iKey * 6.283);
  vec3 col = mix(iColA, iColB, smoothstep(0.0, 0.55, k + shift * 0.3));
  col = mix(col, iColC, smoothstep(0.45, 1.0, k) * (0.85 + 0.1 * sin(t * 0.7 + uv.y * 2.0)));
  col *= 1.0 - 0.35 * smoothstep(0.42, 0.6, max(abs(uv.x) * 1.15, abs(uv.y)));   // the frame's dark edge
  col += (grain(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
