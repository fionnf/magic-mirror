// Neon arc: one curved tube of neon in a dark room, its light washing the wall in a soft coloured
// fan below it. The arc turns very slowly; the bass widens the glow; the key tints the fan.
// Over tens of minutes the tube is re-bent: a short arc, a half circle or almost a full ring,
// fine or thick, and a second smaller arc lights up inside it and goes out again.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
vec2 tube(vec2 p, float R, float c, float span, float th){      // (tube, glow); arc centred on angle c from the top
  float a = atan(p.x, p.y) - c;
  a = mod(a + 3.14159, 6.28318) - 3.14159;
  float ac = clamp(a, -span, span) + c;                  // the nearest point of the bent tube
  float d = length(p - R * vec2(sin(ac), cos(ac)));
  return vec2(exp(-pow(d / th, 2.0)), exp(-d * (9.0 - 3.0 * iBreath)));
}
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.008;
  vec4 e = iEvolve;
  float rot = 0.4 * sin(t);
  mat2 Rm = mat2(cos(rot), -sin(rot), sin(rot), cos(rot));
  vec2 p = Rm * (uv - vec2(0.0, -0.05));
  float span = 1.3 + 0.9 * e.x;                            // half-width of the arc in radians round the top
  float R = 0.33 + 0.04 * e.y;
  float th = 0.006 + 0.003 * e.z + 0.003 * iBreath;
  vec2 a = tube(p, R, 0.0, span, th);
  float two = smoothstep(0.0, 0.8, e.w);                   // a second, smaller arc inside
  vec2 b = tube(p, R * 0.62, 0.4 * e.z, span * 0.7, th * 0.9) * two;
  // the wash: light falling from the tube onto the wall below and around it
  float wash = exp(-length(vec2(p.x * 0.9, (p.y - R * 0.3) * 0.7)) * 2.6) * (0.55 + 0.25 * min(span / 2.2, 1.0));
  vec3 fanCol = mix(iColB, iColC, 0.3 + 0.3 * cos(iKey * 6.2832));
  vec3 col = iColA * 0.6 + fanCol * wash * 0.42 + iColB * (a.y + b.y * 0.8) * 0.6;
  col += iColC * (a.x + b.x);
  col += (hash(fc) - 0.5) * 0.02;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
