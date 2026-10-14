// Living cells (music): soft smooth-Voronoi cells with glowing membranes and nuclei - the GPU port
// of organic.Cells (same 14 seeds, same drift) as music mode shows it (grey through the scene
// palette). The bass swells them: nuclei grow and the membranes thicken, as in the original.
const float CX[14] = float[14](0.8050,0.5153,0.0539,0.4085,0.0488,0.6524,0.4349,0.8977,0.3924,0.6767,0.5556,0.8797,0.6792,0.2273);
const float CY[14] = float[14](0.8079,0.2858,0.3834,0.0453,0.9992,0.2345,0.9742,0.8442,0.4930,0.0608,0.2715,0.0642,0.8701,0.8954);
const float Q0[14] = float[14](5.4774,4.4431,3.1611,1.2764,5.0630,0.9360,2.8169,1.4790,5.0232,3.1801,0.0913,0.5390,2.3103,2.5084);
const float Q1[14] = float[14](0.1163,0.0075,2.7423,2.0406,1.9873,4.3867,5.0173,2.0082,3.1844,1.4833,5.8606,5.3061,5.9724,5.8809);
vec3 pal(float s){                       // scene palette: iColA/B/C are LUT entries 25/140/245 of the
  vec3 s0 = 0.5 * iColA;                 // scene's 4-stop ramp; rebuild the 4 stops (within ~5%)
  vec3 s1 = s0 + (iColA - s0) / 0.2941;
  vec3 s2 = s1 + (iColB - s1) / 0.6471;
  vec3 s3 = s2 + (iColC - s2) / 0.8824;
  float x = clamp(s, 0.0, 1.0) * 3.0;
  vec3 c = x < 1.0 ? mix(s0, s1, x) : x < 2.0 ? mix(s1, s2, x - 1.0) : mix(s2, s3, x - 2.0);
  return clamp(c, 0.0, 1.0);
}
void mainImage(out vec4 o, in vec2 fc){
  float W = iResolution.x, hy = iResolution.y / W;
  vec2 p = vec2(fc.x - 0.5, iResolution.y - fc.y - 0.5) / W;   // width units, top-down
  float t = iTime, b = iBass;
  float d1 = 1e9, d2 = 1e9;
  for (int i = 0; i < 14; i++){
    vec2 c = vec2(CX[i] + 0.07 * sin(t * 0.07 + Q0[i]), (CY[i] + 0.07 * cos(t * 0.06 + Q1[i])) * hy);
    float d = length(p - c);
    if (d < d1){ d2 = d1; d1 = d; } else if (d < d2){ d2 = d; }
  }
  float wl = (d2 - d1) / (0.013 + 0.012 * b + 0.003 * iEnergy);
  float wall = exp(-wl * wl);                                   // bright membranes
  float body = exp(-d1 / (0.11 + 0.06 * b));                     // glowing nuclei
  o = vec4(pal(clamp(0.15 + 0.55 * body + 0.6 * wall, 0.0, 1.0)), 1.0);
}
