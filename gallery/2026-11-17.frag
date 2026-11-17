// Teal Orbit Field - art of the day 2026-11-17
// A quiet teal sphere of fine light points hovers in deep space, swelling and drifting through the day while its rim brightens and thickens like a held breath.
float hash12(vec2 p){
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float softDot(vec2 p, vec2 c, float r){
    float d = length(p - c);
    return exp(-d * d / (r * r));
}

vec3 paletteMix(float t){
    return mix(iColA, mix(iColB, iColC, 0.75), clamp(t, 0.0, 1.0));
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    vec2 uv = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;
    vec2 p = uv;

    float slowT = iTime * 0.018;
    float sway = 0.02 * sin(slowT * 1.7 + iEvolve.x * 1.8);
    p.x += sway;
    p.y += 0.01 * sin(slowT * 1.3 + iEvolve.y * 2.2);

    vec2 center = vec2(mix(-0.10, 0.11, day), mix(0.05, -0.03, day));
    center += 0.03 * vec2(iEvolve.z, -iEvolve.w);

    float baseR = mix(0.18, 0.34, day);
    baseR += 0.020 * iBass + 0.012 * iEnergy;
    baseR += 0.012 * sin(slowT + 6.2831 * iTreble);

    vec2 q = p - center;
    float d = length(q);
    float ang = atan(q.y, q.x);

    float body = smoothstep(baseR, baseR - 0.10, d);
    float edge = exp(-pow((d - baseR) / 0.035, 2.0));
    float halo = exp(-pow((d - baseR) / 0.10, 2.0));

    float tealShift = 0.35 + 0.20 * day + 0.08 * iBright;
    vec3 bg = paletteMix(0.08 + 0.10 * day);
    bg *= 0.75 + 0.10 * sin(ang * 2.0 + slowT * 0.4);

    vec3 col = bg * (0.22 + 0.12 * halo);

    float spark = 0.0;
    vec2 r = q / max(baseR, 0.001);
    float edgeBand = smoothstep(0.60, 1.08, length(r)) * (1.0 - smoothstep(0.90, 1.15, length(r)));

    for(int i = 0; i < 12; i++){
        float fi = float(i);
        float a = 6.2831853 * (fi / 12.0 + 0.03 * hash12(vec2(fi, 1.7)) + 0.01 * iSong);
        float rr = 0.86 + 0.08 * hash12(vec2(fi, 9.2)) + 0.04 * day;
        vec2 pc = vec2(cos(a), sin(a)) * rr;
        float rad = mix(0.055, 0.030, day) * (0.85 + 0.35 * iBright);
        rad *= 1.0 + 0.20 * hash12(vec2(fi, 4.4));
        float w = softDot(r, pc, rad);
        float pop = 0.55 + 0.45 * hash12(vec2(fi, 7.1));
        spark += w * pop;
    }

    float grain = 0.25 + 0.75 * hash12(floor((r + 2.0) * 24.0));
    spark *= edgeBand * grain;
    spark *= 0.75 + 0.55 * iMid + 0.35 * iBright;

    float rim = edge * (1.0 + 0.50 * iTreble);
    float core = exp(-pow(d / (baseR * (0.58 + 0.10 * day)), 2.0));
    core *= mix(0.90, 0.65, day);

    vec3 tealA = iColA;
    vec3 tealB = mix(iColA, iColB, 0.75);
    vec3 tealC = mix(iColB, iColC, 0.80);

    col += body * mix(tealA * 0.12, tealB * 0.36, day);
    col += core * mix(tealB * 0.55, tealC * 0.60, day);
    col += rim * mix(tealB * 0.60, tealC * 1.05, 0.65 + 0.35 * day);
    col += spark * mix(tealB, tealC, tealShift);

    float outside = smoothstep(baseR + 0.18, baseR + 0.02, d);
    col *= mix(0.10, 1.0, outside);

    col = max(col, vec3(0.0));
    col = pow(col, vec3(0.92));

    fragColor = vec4(col, 1.0);
}