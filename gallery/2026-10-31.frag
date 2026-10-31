// Drift of Dots - art of the day 2026-10-31
// A handful of luminous dotted paths cross a dark field like remembered routes, widening, migrating, and multiplying through the day until the wall holds a quiet map of motion.
float sat(float x) { return clamp(x, 0.0, 1.0); }

vec3 palMix(vec3 a, vec3 b, vec3 c, float t) {
    vec3 m1 = mix(a, b, smoothstep(0.0, 0.55, t));
    return mix(m1, c, smoothstep(0.45, 1.0, t));
}

float hash11(float p) {
    return fract(sin(p * 127.1) * 43758.5453123);
}

vec2 hash21(float p) {
    float n = sin(p * 91.7) * 43758.5453123;
    return fract(vec2(n, n * 1.2154 + 0.37));
}

vec2 rot2(vec2 p, float a) {
    float s = sin(a), c = cos(a);
    return vec2(c * p.x - s * p.y, s * p.x + c * p.y);
}

vec2 bezier(vec2 a, vec2 b, vec2 c, vec2 d, float t) {
    float s = 1.0 - t;
    return s * s * s * a + 3.0 * s * s * t * b + 3.0 * s * t * t * c + t * t * t * d;
}

float dotGlow(vec2 p, vec2 c, float r, float core, float glow) {
    float d = length(p - c);
    float corev = smoothstep(r, r - core, d);
    float glv = smoothstep(r + glow, r, d);
    return corev + 0.55 * glv;
}

float trail(vec2 p, vec2 a, vec2 b, vec2 c, vec2 d, float nDots, float headBoost, float width, float glow) {
    float acc = 0.0;
    for (int i = 0; i < 32; i++) {
        float fi = float(i);
        float t = fi / max(nDots - 1.0, 1.0);
        if (fi >= nDots) break;
        vec2 q = bezier(a, b, c, d, t);
        float lead = pow(t, headBoost);
        float r = width * mix(1.05, 0.72, lead);
        float core = mix(0.018, 0.010, lead);
        float g = mix(glow, glow * 1.35, lead);
        acc += dotGlow(p, q, r, core, g) * mix(0.70, 1.25, lead);
    }
    return acc;
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    vec2 uv = (fragCoord - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);
    vec2 p = uv;

    float tSlow = iTime * 0.03;
    float breath = iBreath * 0.8 + iMid * 0.25 + 0.1;
    float tension = iTension;
    float bright = iBright;
    float seed = iSong;

    vec3 A = iColA;
    vec3 B = iColB;
    vec3 C = iColC;
    vec3 bg = A * 0.18 + B * 0.02;

    float arc = smoothstep(0.0, 1.0, day);
    float size = mix(0.10, 0.32, arc);
    float drift = mix(-0.22, 0.20, arc);
    float lift = mix(-0.18, 0.24, arc);
    float sway = 0.08 * sin(tSlow + seed * 6.2831);

    vec2 c0 = vec2(-0.52 + 0.12 * breath, -0.20 + 0.20 * arc + 0.04 * sway);
    vec2 c1 = vec2(-0.05 + 0.18 * arc, 0.04 + 0.10 * sin(0.7 + seed * 4.0));
    vec2 c2 = vec2(0.18 + 0.18 * arc, 0.22 + 0.10 * lift);
    vec2 c3 = vec2(0.48 + 0.08 * arc, 0.34 + 0.10 * lift);

    c0 += vec2(0.0, -0.12 * (1.0 - arc));
    c1 += vec2(0.05 * sin(0.9 + seed * 3.1), 0.10 * (arc - 0.5));
    c2 += vec2(0.06 * sin(1.3 + iEvolve.x * 2.5), 0.04 * cos(0.7 + iEvolve.y * 1.7));
    c3 += vec2(0.10 * drift, 0.08 * arc);

    float hueShift = 0.5 + 0.5 * sin(iKey + 1.4);
    vec3 dotA = mix(A, B, 0.45 + 0.25 * hueShift);
    vec3 dotB = mix(B, C, 0.35 + 0.40 * hueShift);
    vec3 dotC = mix(A, C, 0.25 + 0.55 * hueShift);

    float mainDots = mix(12.0, 28.0, arc);
    float mainWidth = size;
    float mainGlow = mix(0.10, 0.16, bright);

    float a = trail(p, c0, c1, c2, c3, mainDots, 1.8, mainWidth, mainGlow);
    vec3 col = bg + a * mix(dotA, dotC, 0.55);

    float secondOn = smoothstep(0.38, 0.82, day);
    vec2 d0 = vec2(-0.40 + 0.06 * iEvolve.z, 0.30 - 0.10 * arc);
    vec2 d1 = vec2(-0.15 + 0.18 * arc, 0.15 + 0.07 * sin(1.6 + tSlow));
    vec2 d2 = vec2(0.18 + 0.16 * arc, -0.02 + 0.10 * arc);
    vec2 d3 = vec2(0.52 + 0.10 * arc, -0.16 + 0.14 * arc);
    float b = trail(p, d0, d1, d2, d3, mix(6.0, 18.0, arc), 2.2, mainWidth * 0.82, mainGlow * 0.9);
    col += secondOn * b * mix(dotB, dotC, 0.75);

    float thirdOn = smoothstep(0.68, 1.0, day);
    vec2 e0 = vec2(-0.56 + 0.05 * sin(seed * 8.0), -0.02 + 0.06 * iEvolve.w);
    vec2 e1 = vec2(-0.18 + 0.20 * arc, -0.20 + 0.06 * arc);
    vec2 e2 = vec2(0.14 + 0.20 * arc, -0.26 + 0.10 * arc);
    vec2 e3 = vec2(0.52 + 0.08 * arc, -0.10 + 0.08 * arc);
    float c = trail(p, e0, e1, e2, e3, mix(5.0, 14.0, arc), 2.0, mainWidth * 0.72, mainGlow * 0.85);
    col += thirdOn * c * mix(dotA, dotB, 0.65);

    float grain = 0.0;
    for (int i = 0; i < 18; i++) {
        float fi = float(i);
        vec2 j = hash21(fi + seed * 17.0);
        float h = hash11(fi * 13.7 + seed * 3.0);
        vec2 qp = vec2(j.x - 0.5, j.y - 0.5);
        qp.x *= 1.35;
        qp = rot2(qp, 6.2831 * h);
        vec2 pp = p - vec2(-0.20 + 0.40 * arc + 0.10 * j.x, -0.16 + 0.34 * arc + 0.10 * j.y);
        float d = length(pp - qp * (0.08 + 0.10 * arc));
        grain += smoothstep(0.020, 0.0, d) * (0.2 + 0.8 * smoothstep(0.45, 1.0, arc));
    }
    col += grain * 0.04 * dotC;

    float vign = smoothstep(1.25, 0.35, length(uv));
    col *= 0.80 + 0.20 * vign;
    col = max(col, vec3(0.0));

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
