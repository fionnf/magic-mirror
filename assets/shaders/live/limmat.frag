// Limmat (live): the river as it runs past the city right now. Strands of water flow down the wall,
// bending round slow eddies; glints travel along them. iTime is the river's own clock (Python runs it
// at the measured flow), iEnergy 0..1 how full the river is: more strands, wider eddies, more glints.
float hash(float n){ return fract(sin(n * 127.1) * 43758.5453); }
float n2(vec2 p){ return sin(p.x * 1.7 + sin(p.y * 1.3)) * 0.5 + sin(p.y * 2.3 - p.x * 0.7) * 0.5; }

void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = fc / iResolution.y;                         // 0..0.75 wide, 0..1 tall
  float T = iTime, e = clamp(iEnergy, 0.0, 1.0);
  float y = uv.y + T * 0.12;                            // the water moves down the wall
  // stream function: strands are its level lines, bent by eddies drifting with the water
  float psi = uv.x
            + (0.035 + 0.03 * e) * sin(y * 6.0 + 1.3 * sin(uv.x * 4.0 + T * 0.05))
            + (0.02 + 0.02 * e) * n2(vec2(uv.x * 5.0, y * 3.0))
            + 0.012 * sin(y * 17.0 + uv.x * 9.0);
  float N = 14.0 + 10.0 * e;                            // strands across the river
  float s = psi * N;
  float idx = floor(s), f = fract(s);
  float w = 0.09 + 0.05 * e;                            // strand half-width (in strand spacing)
  float line = smoothstep(w, w * 0.25, abs(f - 0.5));
  float shade = 0.55 + 0.45 * hash(idx + 3.0);          // each strand its own tone
  // glints: short bright runs travelling along each strand, a little faster than the water
  float g = fract(y * (1.5 + hash(idx) * 1.5) - T * (0.05 + 0.1 * hash(idx + 9.0)) + hash(idx + 5.0));
  float glint = smoothstep(0.0, 0.06, g) * smoothstep(0.22 + 0.2 * e, 0.06, g);
  float depth = 0.5 + 0.5 * sin(uv.x * 3.0 + 0.7);      // deeper in the middle of the river
  vec3 col = iColA * (0.55 + 0.45 * depth);
  col = mix(col, iColB * shade, line * 0.9);
  col += iColC * line * glint * (0.55 + 0.4 * e);
  o = vec4(col, 1.0);
}
