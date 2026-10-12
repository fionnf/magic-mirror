// Orb: one sphere of soft light hanging in the dark, lit from one side, its shadow side the room's
// own colour, a faint reflection of a window on it. The light source circles it over an hour.
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / iResolution.y;
  float t = iTime * 0.01;
  float R = 0.3;
  vec2 c = vec2(0.03 * sin(t * 0.7), 0.02 * cos(t));
  vec2 p = uv - c;
  float r = length(p);
  float z = sqrt(max(R * R - r * r, 0.0));
  vec3 n = vec3(p, z) / R;
  float la = fract(iClock) * 6.2832 + t;                           // the light goes round once an hour
  vec3 L = normalize(vec3(cos(la) * 0.8, 0.5, sin(la) * 0.5 + 0.6));
  float lit = max(dot(n, L), 0.0);
  float wrap = 0.5 + 0.5 * dot(n, L);
  float inside = smoothstep(0.004, -0.004, r - R);
  vec3 sphere = mix(iColA * 0.8, iColB, wrap * 0.9);
  sphere = mix(sphere, iColC, pow(lit, 2.5) * (0.7 + 0.2 * iBreath));
  float win = smoothstep(0.08, 0.0, length((n.xy - vec2(-0.35, 0.45)) * vec2(1.0, 1.8))) * smoothstep(0.0, 0.3, n.z);
  sphere = mix(sphere, iColC, win * 0.5);
  vec3 col = iColA * 0.6 + iColB * 0.3 * exp(-max(r - R, 0.0) * 4.0);
  col = mix(col, sphere, inside);
  col += (hash(fc) - 0.5) * 0.02;
  o = vec4(col, 1.0);
}
