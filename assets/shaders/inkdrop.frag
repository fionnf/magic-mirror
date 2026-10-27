// Ink drop: one orb of ink on soft paper, its edge bleeding into the fibres. The paper's warmth
// and the ink's depth are the only two colours; the orb drifts and swells with the breath.
// The ink pools darker towards a dried rim and leaves faint tide lines as it spreads. Over tens of
// minutes its feathered fingers reach further into the paper or pull back, the tide lines multiply
// and fade, the drop squashes, and a second small drop lands beside it and bleeds into it.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
float smin(float a, float b, float k){ float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0); return mix(b, a, h) - k * h * (1.0 - h); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  vec4 e = iEvolve;
  float t = iTime * 0.01;
  vec2 c = vec2(0.05 * sin(t), 0.04 * cos(t * 0.7));
  vec2 p = (uv - c) * vec2(1.0 + 0.1 * e.y, 1.0 - 0.1 * e.y);
  float a = atan(p.y, p.x);
  float R = 0.26 + 0.02 * iBreath + 0.012 * sin(a * 3.0 + t * 2.0) + 0.02 * (noise(vec2(a * 1.5, t)) - 0.5);
  float d = length(p) - R;
  float drop2 = smoothstep(0.1, 0.85, e.w);              // a second drop, part of the cycle
  if (drop2 > 0.0) {
    vec2 c2 = vec2(0.22, -0.2) + 0.04 * vec2(sin(t * 1.3), cos(t));
    d = smin(d, length(p - c2) - 0.085 * drop2, 0.05);
  }
  float fibre = noise(fc * 0.35) * 0.6 + noise(fc * 0.9) * 0.4;
  float reach = 0.05 + 0.05 * (0.5 + 0.5 * e.x);         // how far the feathering reaches
  float fingers = noise(vec2(a * 9.0, length(p) * 14.0)) * noise(fc * 0.18);
  float bleed = smoothstep(reach * (0.5 + 1.4 * fingers) + 0.03 * fibre, -0.01, d);
  float ink = smoothstep(0.012, -0.012, d);
  vec3 paper = mix(iColC, iColB, 0.22 + 0.12 * fibre) * 0.72;
  paper *= 1.0 - 0.25 * length(uv);
  float depth = smoothstep(0.0, -0.22, d);               // 0 at the edge .. 1 deep inside
  vec3 wet = mix(iColB, iColA, 0.55 + 0.45 * depth);
  float lines = 3.0 + 2.0 * e.z;                         // tide lines left by the drying ink
  float tide = pow(0.5 + 0.5 * cos(d * lines * 40.0), 6.0) * smoothstep(-0.2, -0.02, d) * (0.5 + 0.5 * fibre);
  vec3 col = mix(paper, mix(paper, wet, 0.45), bleed * (0.6 + 0.4 * fibre));
  col = mix(col, wet, ink);
  col = mix(col, iColA * 0.8, ink * tide * 0.35);
  col = mix(col, iColA * 0.7 + iColB * 0.2, ink * smoothstep(-0.035, 0.0, d) * 0.55);   // the dried rim, darkest
  col += (iColB - iColA) * 0.12 * ink * smoothstep(-0.05, -0.25, d) * (fibre - 0.3);    // pooled ink, uneven
  col += (hash(fc) - 0.5) * 0.03;
  o = vec4(col, 1.0);
}
