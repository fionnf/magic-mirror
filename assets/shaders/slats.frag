// Slats: a loop of thin vertical blades, like a ribbon of iridescent film seen edge-on, each blade
// catching a different hue. The loop turns very slowly so blades slide from front to back; the
// spectrum shifts round it through the day. A faint glow sits behind it.
// Over tens of minutes the loop is re-shaped: a plain ring, a figure of eight or a wide ellipse,
// short even blades or tall uneven ones, and the band twists from flat to a deep wave.
vec3 spec(float h){ return 0.5 + 0.5 * cos(6.2832 * (h + vec3(0.0, 0.33, 0.67))); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  float t = iTime * 0.02 + iClock * 0.15;
  vec4 e = iEvolve;
  float eight = smoothstep(0.0, 0.9, e.x);                 // ring .. figure of eight
  float wide = 0.3 + 0.05 * e.y;
  float hAmp = 0.08 + 0.06 * e.z;                          // even .. uneven blade heights
  float twist = 0.06 + 0.05 * e.w;
  vec3 col = vec3(0.0);
  for (int i = 0; i < 32; i++){
    float fi = float(i) / 32.0;
    float ang = fi * 6.2832 + t;
    float ring = cos(ang) * (1.0 + 0.15 * sin(ang * 2.0 + t));
    float x = wide * mix(ring, 1.15 * sin(ang * 2.0), eight * 0.7), z = sin(ang);   // the blade's place on the loop
    float hgt = 0.26 + hAmp * sin(ang * 2.0 + t);
    float w = 0.008 + 0.012 * (z * 0.5 + 0.5);
    float y0 = twist * sin(ang * 3.0 - t * 2.0);
    float b = smoothstep(w, 0.0, abs(uv.x - x)) * smoothstep(hgt, hgt - 0.05, abs(uv.y - y0));
    vec3 c = mix(spec(fi + t * 0.3), mix(iColB, iColC, fi), 0.35);
    col = max(col, c * b * (0.25 + 0.85 * (z * 0.5 + 0.5)) * (1.0 + 0.2 * iBreath));
  }
  col += iColA * 0.25 * exp(-dot(uv, uv) * 6.0);
  o = vec4(col, 1.0);
}
