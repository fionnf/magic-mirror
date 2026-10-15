// Azure Ring, Ember Edge - art of the day 2026-10-15
// A single ring of cyan light hangs in deep night-blue, drifting from a soft dawn blur into sharp noon focus and back into a gentle evening bloom, always rimmed on its outer edge by a thin breath of peach, like the last warmth caught on cold glass.
float g(float x, float w){ float q = x / max(w, 1e-4); return exp(-q*q); }
void mainImage(out vec4 fragColor, in vec2 fragCoord){
  vec2 p = (fragCoord - 0.5*iResolution) / iResolution.x;
  float h = iClock;
  float t = iTime;
  float TAU = 6.2831853;
  float focus = 0.5 + 0.5*cos((h - 13.0)/24.0*TAU);
  float drift = 1.0 + 0.18*sin(t*0.013) + 0.1*sin(t*0.0041 + 1.7);
  float s = mix(0.062, 0.017, focus) * drift;
  s *= 1.0 - 0.22*iTension;
  s = clamp(s, 0.012, 0.066);
  vec2 c = vec2(0.02*sin(t*0.0071) + 0.012*sin(t*0.0023 + 2.0), -0.045*cos((h - 4.0)/24.0*TAU) + 0.015*sin(t*0.0057));
  c.x += 0.002*sin(iBeatPhase*TAU);
  float R = 0.245 + 0.04*smoothstep(13.0, 20.0, h) - 0.025*smoothstep(21.5, 24.0, h) + 0.012*sin(t*0.0031) + 0.008*iBreath;
  vec2 q = p - c;
  float r = length(q);
  float a = atan(q.y, q.x);
  float d = r - R;
  float a1 = 0.0; float b1 = 0.0; float a2 = 0.0; float b2 = 0.0; float tot = 0.0;
  for (int i = 0; i < 24; i++) {
    float e = iDay[i];
    float th = float(i)/24.0*TAU;
    a1 += e*cos(th); b1 += e*sin(th);
    a2 += e*cos(2.0*th); b2 += e*sin(2.0*th);
    tot += e;
  }
  float n = max(tot, 1e-3);
  float ang = a + iSong*TAU + t*0.004;
  float swell = (a1*cos(ang) + b1*sin(ang) + 0.5*(a2*cos(2.0*ang) + b2*sin(2.0*ang))) / n;
  swell = 1.0 + 0.22*clamp(swell, -1.0, 1.0)*smoothstep(0.0, 0.5, tot);
  float core = g(d, s);
  float halo = g(d, s*3.2 + 0.03);
  float disc = smoothstep(R + s, R - 0.12, r);
  float lean = 0.5 + 0.18*sin(iKey) + 0.1*sin(t*0.009);
  vec3 azure = mix(iColB, iColC, lean*0.6);
  vec3 ringCol = mix(azure, iColC, pow(core, 1.6)*0.85);
  vec3 col = iColA;
  col += iColB * halo * 0.22;
  col += iColB * disc * 0.07;
  col += ringCol * core * 0.92 * swell;
  float fOff = s*1.35 + 0.012;
  float fw = mix(s*0.5 + 0.007, s*0.32 + 0.005, iBright);
  float warmAmt = 0.32 + 0.18*smoothstep(15.0, 20.0, h) + 0.05*sin(t*0.011);
  float fr = g(d - fOff, fw) * warmAmt;
  vec3 warmCol = mix(vec3(1.0, 0.70, 0.48), iColC, 0.15) * 0.85;
  col = mix(col, warmCol, clamp(fr, 0.0, 1.0) * 0.75);
  col += warmCol * fr * 0.12;
  float vig = smoothstep(0.95, 0.25, length(p*vec2(1.0, iResolution.x/iResolution.y*0.7)));
  col = mix(iColA*0.85, col, 0.75 + 0.25*vig);
  col = col / (1.0 + 0.22*col);
  fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}