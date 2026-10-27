// Ember web: a soft dotted blob, like a net of tiny lights stretched over an invisible body. The
// dots burn orange-red at its folded edges and cool to blue across its face. It wobbles very slowly,
// and over the day it turns, showing a different face each hour.
// Over tens of minutes the body goes from nearly round to clearly lobed, the net draws finer or
// coarser, and a second, smaller body swells out of it, hangs beside it and is drawn back in.
float smin(float a, float b, float k){ float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0); return mix(b, a, h) - k * h * (1.0 - h); }
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  vec4 e = iEvolve;
  float t = iTime * 0.025 + iClock * 0.2;
  float a = atan(uv.y, uv.x), r = length(uv);
  float k = 4.0 + 1.5 * e.z, f = floor(k);              // 2.5 .. 5.5 lobes, blended
  float lob = mix(sin(a * f + t * 2.0), sin(a * (f + 1.0) - t * 1.4), smoothstep(0.0, 1.0, k - f));
  float R0 = 0.36;
  float R = R0 + (0.02 + 0.035 * (0.5 + 0.5 * e.y)) * lob + 0.01 * iBreath;
  float d = r - R;
  float bud = smoothstep(0.05, 0.8, e.w);
  if (bud > 0.0) {
    float ba = t * 0.6 + 2.0 * e.x;
    vec2 bc = mix(0.1, 0.36, bud) * vec2(cos(ba), sin(ba));
    d = smin(d, length(uv - bc) - 0.16 * bud, 0.08);
  }
  float inside = smoothstep(0.01, -0.02, d);
  float z = sqrt(clamp(-d / 0.3, 0.0, 1.0));            // a pretend surface height
  vec2 p = uv / (0.55 + 0.45 * z);                        // dots crowd towards the edges
  p = mat2(cos(t), -sin(t), sin(t), cos(t)) * p;
  vec2 c = fract(p * (30.0 + 6.0 * e.x)) - 0.5;          // finer .. coarser net
  float dot_ = smoothstep(0.42, 0.2, length(c)) * inside;
  float rim = smoothstep(0.35, 1.0, 1.0 - z);
  vec3 col = mix(iColB * 0.7, mix(iColC, iColA, 0.35), rim);   // blue face, orange-red edge
  col *= 0.9 + 1.4 * rim + 0.4 * z;
  col = mix(col, col.bgr, 0.25 * (0.5 + 0.5 * sin(iClock * 0.26)));   // the blob's temperature changes through the day
  o = vec4(col * dot_ + iColA * 0.05 * inside, 1.0);
}
