// Ember web: a soft dotted blob, like a net of tiny lights stretched over an invisible body. The
// dots burn orange-red at its folded edges and cool to blue across its face. It wobbles very slowly,
// and over the day it turns, showing a different face each hour.
void mainImage(out vec4 o, in vec2 fc){
  vec2 uv = (fc - 0.5 * iResolution) / min(iResolution.x, iResolution.y);
  float t = iTime * 0.025 + iClock * 0.2;
  float a = atan(uv.y, uv.x), r = length(uv);
  float R = 0.38 + 0.04 * sin(a * 3.0 + t * 2.0) + 0.025 * sin(a * 5.0 - t * 1.4) + 0.01 * iBreath;
  float inside = smoothstep(R + 0.01, R - 0.02, r);
  float z = sqrt(max(0.0, 1.0 - pow(r / R, 2.0)));      // a pretend surface height
  vec2 p = uv / (0.55 + 0.45 * z);                        // dots crowd towards the edges
  p = mat2(cos(t), -sin(t), sin(t), cos(t)) * p;
  vec2 c = fract(p * 30.0) - 0.5;
  float dot_ = smoothstep(0.42, 0.2, length(c)) * inside;
  float rim = smoothstep(0.35, 1.0, 1.0 - z);
  vec3 col = mix(iColB * 0.7, mix(iColC, iColA, 0.35), rim);   // blue face, orange-red edge
  col *= 0.9 + 1.4 * rim + 0.4 * z;
  col = mix(col, col.bgr, 0.25 * (0.5 + 0.5 * sin(iClock * 0.26)));   // the blob's temperature changes through the day
  o = vec4(col * dot_ + iColA * 0.05 * inside, 1.0);
}
