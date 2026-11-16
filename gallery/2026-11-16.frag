// Aubergine Hour - art of the day 2026-11-16
// A single mauve orb gathers out of a deep plum field, its lit edge drifting through the day while the shadow side dissolves back into the room’s darkness.
float sat(float x){ return clamp(x, 0.0, 1.0); }

vec3 mix3(vec3 a, vec3 b, vec3 c, vec3 w){ return a*w.x + b*w.y + c*w.z; }

float sdCircle(vec2 p, float r){ return length(p) - r; }

float softMask(float d, float w){ return smoothstep(w, -w, d); }

vec3 paletteTint(vec3 a, vec3 b, vec3 c, float t){
    vec3 ab = mix(a, b, smoothstep(0.0, 0.65, t));
    return mix(ab, c, smoothstep(0.55, 1.0, t));
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    vec2 p = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;

    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    float night = smoothstep(0.72, 1.0, day);
    float dawn = 1.0 - smoothstep(0.0, 0.28, day);

    float song = fract(iSong * 0.173 + 0.31);
    float evo = 0.18 * iEvolve.x + 0.11 * iEvolve.y - 0.09 * iEvolve.z + 0.07 * iEvolve.w;
    float tide = 0.03 * sin(iTime * 0.014 + song * 6.2831);

    vec2 c = vec2(0.0);
    c.x = mix(-0.14, 0.10, day) + 0.04 * evo + 0.03 * sin(iTime * 0.017 + song * 9.0);
    c.y = mix(0.03, -0.04, day) + 0.03 * iBreath + 0.02 * evo;

    float r = mix(0.30, 0.42, day);
    r += 0.03 * iBreath + 0.02 * evo + 0.02 * iMid;
    r += 0.015 * tide;

    vec2 q = p - c;
    float aspect = iResolution.x / iResolution.y;
    q.x *= 1.0 + 0.08 * (aspect - 1.0);

    float d = sdCircle(q, r);
    float wobble = 0.020 * sin(3.0 * q.x + 2.0 * q.y + 1.3 * song + iTime * 0.010)
                 + 0.014 * sin(5.0 * q.y - 0.8 * song + iTime * 0.013)
                 + 0.010 * iEvolve.z * (q.x - q.y);
    d += wobble * smoothstep(-0.50, 0.25, 1.0 - length(q) / r);

    float body = softMask(d, 0.055);
    float glow = exp(-abs(d) * 10.0);
    float rim = exp(-abs(d) * 26.0);

    vec3 groundA = vec3(iColA) * vec3(0.86, 0.78, 0.92);
    vec3 groundB = vec3(iColB) * vec3(0.78, 0.70, 0.88);
    vec3 ground = mix(groundA, groundB, 0.30 + 0.12 * day + 0.08 * iBass);
    ground += 0.012 * vec3(0.03, -0.01, 0.02) * (q.y + 0.5);

    vec3 formShadow = mix(vec3(iColA), vec3(iColB), 0.35) * vec3(1.0, 0.88, 1.06);
    vec3 formMid    = mix(vec3(iColB), vec3(iColC), 0.22 + 0.18 * day) * vec3(1.05, 0.95, 1.08);
    vec3 formLight  = mix(vec3(iColB), vec3(iColC), 0.55) * vec3(1.00, 0.96, 1.02);

    float lightSide = smoothstep(-0.10, 0.32, q.x + 0.10 * q.y + 0.12 * day);
    float shadeSide = 1.0 - lightSide;

    vec3 orb = mix(formShadow, formMid, lightSide);
    orb = mix(orb, formLight, smoothstep(0.42, 0.95, glow));

    float edgeLight = smoothstep(0.10, 0.85, rim) * (0.58 + 0.22 * iBright + 0.10 * day);
    vec3 rimCol = mix(vec3(iColC), mix(vec3(iColB), vec3(iColC), 0.35), 0.4);
    orb += rimCol * edgeLight * vec3(0.55, 0.45, 0.60);

    float melt = smoothstep(0.18, 0.72, -q.x + 0.18 * q.y + 0.08 * day);
    orb = mix(orb, ground, 0.30 * melt * shadeSide);

    float interior = smoothstep(-0.25, 0.35, -d);
    orb += interior * (0.035 + 0.030 * iBreath) * vec3(0.08, 0.03, 0.10);

    float noonShift = smoothstep(0.20, 0.70, day);
    vec3 dayTint = mix(vec3(0.02, 0.00, 0.03), vec3(0.05, 0.02, 0.07), noonShift);
    ground += dayTint * 0.6;

    vec3 col = ground;
    col = mix(col, orb, body);
    col += glow * vec3(0.03, 0.01, 0.05) * (0.35 + 0.35 * iLevel);

    col += 0.02 * iDay[0] * vec3(0.02, 0.01, 0.03);
    col += 0.02 * iDay[6] * vec3(0.03, 0.01, 0.04);
    col += 0.015 * iDay[14] * vec3(0.01, 0.00, 0.02);
    col += 0.018 * iDay[21] * vec3(0.03, 0.02, 0.04);

    col = max(col, vec3(45.0 / 255.0, 45.0 / 255.0, 45.0 / 255.0));
    col = clamp(col, 0.0, 0.92);

    fragColor = vec4(col, 1.0);
}
