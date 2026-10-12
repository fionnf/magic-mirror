// Neon arc: one curved tube of neon in a dark room, its light falling in a soft coloured fan on
// the wall below it. The arc turns very slowly; the bass widens the glow; the key tints the fan.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.008;
  float rot = 0.4 * sin(t);
  mat2 R = mat2(cos(rot), -sin(rot), sin(rot), cos(rot));
  vec2 p = R * (uv - vec2(0.0, -0.05));
  float r = length(p), a = atan(p.y, p.x);
  float arc = smoothstep(0.3, 0.5, a) * smoothstep(2.9, 2.7, a);        // an arc over the top
  float d = abs(r - 0.33);
  float tube = exp(-pow(d / (0.006 + 0.003 * iBreath), 2.0)) * arc;
  float glow = exp(-d * (9.0 - 3.0 * iBreath)) * arc;
  // the fan: light thrown downward from the arc
  float below = smoothstep(0.33, 0.0, r) * smoothstep(0.0, 0.4, 0.33 - r);
  float fan = below * (0.5 + 0.5 * smoothstep(-0.3, 0.3, p.y)) * 0.5;
  vec3 fanCol = mix(iColB, iColC, 0.3 + 0.3 * cos(iKey * 6.2832));
  vec3 col = iColA * 0.55 + fanCol * fan * 0.6 + iColB * glow * 0.6;
  col += iColC * tube;
  col += (hash(fc) - 0.5) * 0.025;
  o = vec4(min(col, vec3(1.0)), 1.0);
}
