// Lime Glass Drift - art of the day 2026-11-14
// A single frosted glow gathers through the day, shifting from a compact green ember into a larger chartreuse presence that seems to breathe against a dark petrol field.
float sat(float x){ return clamp(x,0.0,1.0); }

vec3 palMix(vec3 a, vec3 b, vec3 c, float t, float k1, float k2){
    vec3 x = mix(a, b, t);
    return mix(x, c, sat(k1)) * (1.0 - 0.15 * k2);
}

float hash21(vec2 p){
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 34.345);
    return fract(p.x * p.y);
}

float smoothBlob(vec2 p, float day, float breath, vec4 evo, float songish){
    float a = 0.75 + 0.10 * sin(iTime * 0.013 + evo.x * 1.7);
    float b = 0.56 + 0.09 * cos(iTime * 0.011 + evo.y * 1.3);
    vec2 q = p;
    q.x /= a;
    q.y /= b;
    float wob = 0.075 * sin(q.y * 2.4 + iTime * 0.018 + evo.z * 2.0)
              + 0.050 * sin(q.x * 3.1 - iTime * 0.015 + evo.w * 2.4);
    float d = length(q + wob * vec2(0.25, -0.18)) - (0.26 + 0.16 * day + 0.03 * breath);
    d += 0.018 * sin((q.x + q.y) * 4.0 + songish * 6.2831);
    return d;
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    vec2 uv = (fragCoord - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);

    float breath = iBreath;
    float tense = iTension;
    float bright = iBright;
    float energy = iEnergy;
    float songish = fract(iDay[0] * 0.73 + iDay[6] * 0.31 + iDay[13] * 0.19 + iDay[20] * 0.11);

    vec3 colA = iColA;
    vec3 colB = iColB;
    vec3 colC = iColC;

    float yshift = mix(-0.08, 0.12, day);
    float xshift = 0.02 * sin(iTime * 0.006 + iEvolve.x * 1.5) + 0.02 * (songish - 0.5);
    vec2 p = uv - vec2(xshift, yshift);

    float d = smoothBlob(p, day, breath, iEvolve, songish);
    float core = smoothstep(0.22, -0.02, d);
    float body = smoothstep(0.42, -0.18, d);
    float rim = smoothstep(0.08, -0.12, abs(d));

    float halo = exp(-8.0 * abs(d + 0.06));
    halo += 0.5 * exp(-18.0 * abs(d + 0.16));

    float edgeLift = 0.12 + 0.25 * bright + 0.18 * tense;
    float glow = 0.0;
    glow += 0.85 * core;
    glow += 0.55 * body;
    glow += 0.65 * halo;
    glow *= edgeLift;

    vec3 bg = mix(colA * 0.70, colB * 0.55, 0.18 + 0.12 * sin(iTime * 0.004));
    bg = mix(bg, vec3(colA.r * 0.20, colA.g * 0.36, colA.b * 0.34), 0.35 + 0.15 * day);

    float seed = hash21(floor(fragCoord.xy / vec2(96.0, 96.0)) + vec2(songish * 7.0, day * 5.0));
    float subtle = 0.02 * (seed - 0.5) * (1.0 - smoothstep(0.0, 0.65, length(p)));

    vec3 glowCol = mix(colB, colC, 0.55 + 0.25 * day);
    glowCol = mix(glowCol, vec3(colC.r, colC.g, colB.b), 0.20 + 0.18 * bright);

    float innerTint = 0.30 + 0.35 * day + 0.15 * bright;
    vec3 orb = bg;
    orb += glow * glowCol * (0.85 + 0.25 * energy);
    orb += core * mix(colC, vec3(0.95, 0.98, 0.78), innerTint) * 0.75;
    orb += rim * mix(colA * 0.5 + colB * 0.5, colC, 0.60 + 0.25 * tense) * 0.55;
    orb += subtle * vec3(0.05, 0.08, 0.04);

    float vign = smoothstep(1.25, 0.25, length(uv));
    orb *= 0.92 + 0.08 * vign;

    // Keep the core luminous but prevent harsh white on the wall.
    orb = max(orb, vec3(0.0));
    orb = pow(clamp(orb, 0.0, 1.0), vec3(0.95));

    fragColor = vec4(clamp(orb, 0.0, 1.0), 1.0);
}