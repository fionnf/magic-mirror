// Aperture: nested soft rectangles of light around a deep, dark centre, like looking into a
// glowing frame; the opening breathes with the bass and its tint drifts with the key.
// Over tens of minutes the opening changes: tall and narrow to wide, square-cornered to almost
// round, small and deep to wide open, and the light gathers into two to five nested frames or melts
// back into one smooth glow.
float sdBox(vec2 p, vec2 b, float rr){ vec2 q = abs(p) - b + rr; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - rr; }
float grain(vec2 p){ return fract(sin(dot(floor(p), vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.012;
  vec4 e = iEvolve;
  float sz = 1.0 + 0.25 * e.w;                          // small and deep .. wide open
  vec2 half_ = vec2(0.10 * (1.0 + 0.3 * e.y), 0.16 * (1.0 - 0.25 * e.y)) * sz + 0.015 * iBreath;
  float rr = min(half_.x, half_.y) * (0.15 + 0.75 * (0.5 + 0.5 * e.z));   // corner rounding
  float d = sdBox(uv, half_, rr);
  float k = smoothstep(-0.05, 0.45, d);                 // 0 in the centre .. 1 at the edge
  float n = 3.5 + 1.5 * e.x;                            // 2 .. 5 nested frames
  float steps = 0.5 + 0.5 * cos(k * n * 6.2832);
  float framed = smoothstep(0.1, 0.8, 0.5 + 0.5 * e.x) * 0.55;   // how strongly the frames show
  float shift = 0.08 * sin(t + iKey * 6.283);
  vec3 col = mix(iColA, iColB, smoothstep(0.0, 0.55, k + shift * 0.3));
  col = mix(col, iColC, smoothstep(0.45, 1.0, k) * (0.85 + 0.1 * sin(t * 0.7 + uv.y * 2.0)));
  col *= 1.0 - framed * (1.0 - steps) * smoothstep(0.02, 0.15, k);
  col *= 1.0 - 0.35 * smoothstep(0.42, 0.6, max(abs(uv.x) * 1.15, abs(uv.y)));   // the frame's dark edge
  col += (grain(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
