// Pill: a tall rounded outline of light, like a neon tube bent into a capsule, glowing mint at the
// bottom and fading to rose at the top in a dark green-grey room. Its light pools softly below it.
// The tube brightens slightly with the bass; over the day the colour slides round the loop.
float sdCapsule(vec2 p, float h, float r){ p.y -= clamp(p.y, -h, h); return length(p) - r; }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  float stretch = 0.65 + 0.35 * sin(iClock * 0.26);     // the capsule grows taller towards evening
  float d = abs(sdCapsule(uv, stretch * 0.2 * iResolution.y / min(iResolution.x, iResolution.y), 0.17));
  float tube = exp(-pow(d / 0.008, 2.0)) + 0.35 * exp(-d / 0.05);
  float k = clamp(0.5 - uv.y * 1.1 + 0.6 * sin(iClock * 0.26 + iTime * 0.01), 0.0, 1.0);
  vec3 light = mix(iColC, iColB, k);
  vec3 col = iColA * (0.4 + 0.2 * smoothstep(0.6, 0.0, length(uv - vec2(0.0, -0.35))));
  col += light * tube * (0.9 + 0.15 * iBreath);
  o = vec4(col, 1.0);
}
