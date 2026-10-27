// Pill: a tall rounded outline of light, like a neon tube bent into a capsule, glowing mint at the
// bottom and fading to rose at the top in a dark green-grey room. Its light pools softly below it
// and haunts the glass inside. The tube brightens slightly with the bass; over the day the colour
// slides round the loop and the capsule grows taller towards evening.
// Over tens of minutes the tube bends from a capsule into a soft-cornered rectangle and back, it
// thickens and thins, tips a little off upright, and a second, smaller tube lights up inside it
// and fades again.
float sdRBox(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  vec4 e = iEvolve;
  float stretch = 0.65 + 0.35 * sin(iClock * 0.26);     // the capsule grows taller towards evening
  float tilt = 0.12 * e.z;
  vec2 p = mat2(cos(tilt), -sin(tilt), sin(tilt), cos(tilt)) * (uv - vec2(0.0, 0.03));
  float w = 0.22, h = w + stretch * 0.24 * iResolution.y / min(iResolution.x, iResolution.y);
  float rr = w * mix(1.0, 0.35, smoothstep(-0.2, 0.9, e.x));   // capsule .. soft rectangle
  float sd = sdRBox(p, vec2(w, h), rr);
  float d = abs(sd);
  float thick = 0.009 * (1.0 + 0.4 * e.y);
  float tube = exp(-pow(d / thick, 2.0)) + 0.35 * exp(-d / 0.05);
  float inner = smoothstep(0.1, 0.85, e.w);              // a second tube inside, part of the cycle
  float d2 = abs(sdRBox(p, vec2(w, h) * 0.72, rr * 0.72));
  float tube2 = inner * (exp(-pow(d2 / (thick * 0.8), 2.0)) + 0.25 * exp(-d2 / 0.04));
  float k = clamp(0.5 - p.y * 1.1 + 0.6 * sin(iClock * 0.26 + iTime * 0.01), 0.0, 1.0);
  vec3 light = mix(iColC, iColB, k);
  vec3 light2 = mix(iColB, iColC, k);
  vec3 col = iColA * (0.4 + 0.25 * smoothstep(0.7, 0.0, length((uv - vec2(0.0, -h - 0.02)) * vec2(0.6, 1.6))));
  col += light * 0.06 * smoothstep(0.0, -0.1, sd);       // the glass holds a little of the light
  col += light * tube * (0.9 + 0.15 * iBreath) + light2 * tube2 * 0.8;
  o = vec4(col, 1.0);
}
