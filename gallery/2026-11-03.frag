// Moss In Shadow - art of the day 2026-11-03
// Three soft leaf-shapes drift through a deep forest field, opening slightly across the day and settling into a quiet dusk glow by night.
float sat(float x) { return clamp(x, 0.0, 1.0); }

float sdEllipse(vec2 p, vec2 r) {
    vec2 q = p / r;
    return length(q) - 1.0;
}

float leafShape(vec2 p, vec2 c, vec2 r, float t) {
    vec2 q = p - c;
    float a = 0.35 * sin(t * 0.17) + 0.18 * sin(t * 0.07 + 1.3);
    float ca = cos(a);
    float sa = sin(a);
    q = mat2(ca, -sa, sa, ca) * q;
    q.x *= mix(0.82, 1.08, 0.5 + 0.5 * sin(t * 0.11 + c.x * 3.0));
    float d = sdEllipse(q, r);
    float taper = 0.16 * q.x * q.x / max(r.x * r.x, 0.0001);
    return d + taper;
}

float softBlob(vec2 p, vec2 c, vec2 r, float t) {
    float d = leafShape(p, c, r, t);
    return exp(-3.5 * max(d, -0.35));
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = (fragCoord - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    float dusk = smoothstep(0.20, 0.88, day);
    float night = smoothstep(0.62, 1.0, day);

    float breath = 0.5 + 0.5 * iBreath;
    float tense = iTension;
    float bright = iBright;
    float evo1 = iEvolve.x;
    float evo2 = iEvolve.y;
    float evo3 = iEvolve.z;
    float evo4 = iEvolve.w;

    vec3 A = iColA;
    vec3 B = iColB;
    vec3 C = iColC;

    vec3 bg = A * 0.92 + B * 0.08;
    bg += 0.03 * dusk * B;
    bg += 0.015 * night * C;

    vec2 drift = vec2(0.06 * sin(iTime * 0.012 + 1.7 * evo1), 0.05 * cos(iTime * 0.011 + 1.9 * evo2));
    vec2 p = uv + drift;

    float hor = mix(-0.18, 0.08, day) + 0.03 * sin(iTime * 0.009 + evo3 * 2.2);
    float sway = 0.04 * sin(iTime * 0.014 + evo4 * 3.1);

    vec2 c1 = vec2(-0.28 + 0.08 * day + 0.03 * evo1, 0.10 + hor + 0.04 * breath);
    vec2 c2 = vec2(0.02 + 0.10 * day + 0.02 * evo2, -0.02 + hor - 0.02 * breath);
    vec2 c3 = vec2(0.24 + 0.06 * day - 0.03 * evo3, 0.16 + hor + 0.03 * sin(iTime * 0.010 + 2.0));

    float s1 = mix(0.22, 0.29, day) * mix(0.95, 1.08, 0.5 + 0.5 * evo1);
    float s2 = mix(0.26, 0.34, day) * mix(0.94, 1.06, 0.5 + 0.5 * evo2);
    float s3 = mix(0.18, 0.27, day) * mix(0.96, 1.10, 0.5 + 0.5 * evo3);

    float l1 = softBlob(vec2(p.x + sway, p.y), c1, vec2(s1, s1 * 0.86), iTime);
    float l2 = softBlob(vec2(p.x - 0.2 * sway, p.y), c2, vec2(s2, s2 * 0.82), iTime + 2.7);
    float l3 = softBlob(vec2(p.x + 0.15 * sway, p.y), c3, vec2(s3, s3 * 0.88), iTime + 5.1);

    float leaf = max(l1, max(l2, l3));
    float overlap = min(l1 + l2 + l3, 2.0);

    float core = exp(-7.5 * (sdEllipse(p - c2, vec2(s2 * 0.72, s2 * 0.64)) + 0.03));
    float rim = smoothstep(0.60, 0.15, abs(sdEllipse(p - c2, vec2(s2 * 1.02, s2 * 0.92))));

    float halo = 0.0;
    halo += 0.75 * exp(-10.0 * max(sdEllipse(p - c1, vec2(s1 * 1.08, s1 * 0.92)), 0.0));
    halo += 0.70 * exp(-10.0 * max(sdEllipse(p - c3, vec2(s3 * 1.05, s3 * 0.90)), 0.0));
    halo += 0.55 * exp(-8.0 * max(sdEllipse(p - c2, vec2(s2 * 1.12, s2 * 0.98)), 0.0));

    float dayLift = mix(0.0, 1.0, day);
    float nightSed = 0.12 * iDay[18] + 0.10 * iDay[19] + 0.08 * iDay[20];
    float mornSed = 0.05 * iDay[7] + 0.06 * iDay[8] + 0.07 * iDay[9];
    float sediment = clamp(nightSed + mornSed, 0.0, 1.0);

    vec3 leafCol = mix(A, B, 0.55 + 0.18 * dayLift);
    leafCol = mix(leafCol, C, 0.10 + 0.18 * dusk + 0.10 * bright);
    leafCol += 0.08 * sediment * C;

    vec3 edgeCol = mix(B, C, 0.25 + 0.25 * dayLift);
    edgeCol *= 0.78 + 0.18 * tense;

    vec3 col = bg;
    col += 0.25 * leaf * leafCol;
    col += 0.14 * overlap * edgeCol;
    col += 0.11 * core * (0.65 * B + 0.35 * C);
    col += 0.06 * rim * C;
    col += 0.04 * halo * C;

    float vign = smoothstep(1.18, 0.20, length(uv));
    col += 0.03 * vign * B;

    col = clamp(col, vec3(0.0), vec3(1.0));
    col = mix(col, col * 0.92 + vec3(0.02, 0.03, 0.02), 0.08);
    col = pow(col, vec3(0.96));

    fragColor = vec4(col, 1.0);
}