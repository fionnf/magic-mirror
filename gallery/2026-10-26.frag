// Prism Line - art of the day 2026-10-26
// A single vertical seam of light opens into a quiet spectral fan that deepens and widens through the day, holding a dark room together without ever breaking its calm.
float sat(float x){ return clamp(x,0.0,1.0); }
float smoother(float a,float b,float x){ x = sat((x-a)/(b-a)); return x*x*(3.0-2.0*x); }
float hash1(float n){ return fract(sin(n)*43758.5453123); }

vec3 paletteMix(float t){
    vec3 a = iColA;
    vec3 b = iColB;
    vec3 c = iColC;
    if(t < 0.5){
        float u = t * 2.0;
        return mix(a, b, u);
    }
    float u = (t - 0.5) * 2.0;
    return mix(b, c, u);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    vec2 p = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;

    float aspect = iResolution.x / iResolution.y;
    float seam = floor((fragCoord.x / iResolution.x) * iPanels.x) / max(iPanels.x - 1.0, 1.0);
    float drift = 0.015 * sin(iTime * 0.013 + iDay[int(mod(floor(iClock), 24.0))] * 6.2831);
    float x0 = mix(-0.02, 0.05, day) + drift + 0.02 * (seam - 0.5);
    float y0 = mix(0.22, -0.03, day) + 0.02 * sin(0.7 + iTime * 0.011 + iLevel * 1.3);

    vec2 q = p;
    q.x = (q.x - x0) * aspect;
    q.y = q.y - y0;

    float lineW = mix(0.010, 0.020, day) + 0.004 * iMid;
    float line = exp(-abs(q.x) / lineW) * exp(-abs(q.y + 0.16) * 1.7);
    float core = exp(-dot(vec2(q.x / (lineW * 1.8), q.y * 3.5), vec2(q.x / (lineW * 1.8), q.y * 3.5)));

    float fanStart = mix(0.02, -0.05, day);
    float fanOpen = mix(0.12, 0.42, day) + 0.06 * iTreble;
    float fanY = max(q.y - fanStart, 0.0);
    float width = fanOpen * fanY * 1.6 + 0.03;
    float fan = exp(-abs(q.x) / width) * smoother(0.0, 0.85, fanY);
    fan *= exp(-fanY * mix(0.9, 0.55, day));

    float prism = 0.0;
    float yy = max(q.y + 0.02, 0.0);
    float bands = 3.0 + 2.0 * day;
    float ang = atan(q.x, max(0.01, yy));
    float hue = 0.5 + 0.5 * sin(ang * bands + 3.0 * q.y + iTime * 0.01);
    prism += fan * (0.35 + 0.65 * hue);
    prism += 0.5 * core;
    prism += 0.7 * line;

    // soft spectral fan, not striped: only broad chromatic zones
    float r = exp(-pow((q.x + 0.10 * (1.0 - day)) / (0.20 + 0.16 * fanY), 2.0));
    float g = exp(-pow((q.x - 0.02 * day) / (0.16 + 0.14 * fanY), 2.0));
    float b = exp(-pow((q.x - 0.14 - 0.05 * day) / (0.18 + 0.18 * fanY), 2.0));
    vec3 spectral = iColA * (0.55 + 0.35 * r) + iColB * (0.22 + 0.55 * g) + iColC * (0.10 + 0.60 * b);

    // dark ground with luminous clarity
    float vign = 0.85 + 0.18 * dot(p, p);
    vec3 bg = iColA * (0.42 + 0.08 * sin(0.8 + iClock * 0.25)) * vign;

    // day arc: larger changes in height, position, and glow weight
    float dayGlow = mix(0.80, 1.22, day);
    float dayLift = mix(0.08, 0.26, day);
    vec3 col = bg;

    col += spectral * (0.10 + 0.65 * fan) * dayGlow;
    col += iColC * (0.10 * line + 0.12 * core) * mix(0.70, 1.15, day);
    col += iColB * (0.06 * fan) * (0.8 + 0.5 * iBright);

    // subtle sediment from the day's memory, concentrated low and gentle
    float mem = 0.0;
    mem += iDay[0] + iDay[4] + iDay[8] + iDay[12] + iDay[16] + iDay[20];
    mem /= 6.0;
    float sediment = exp(-pow((q.y + 0.33) / 0.22, 2.0)) * exp(-abs(q.x) * 2.2);
    col += (0.04 + 0.06 * mem) * sediment * mix(iColB, iColC, day * 0.7);

    // quiet edge glow along the fan opening
    float edge = exp(-abs(abs(q.x) - width * 0.85) / (0.02 + 0.02 * day)) * fan;
    col += edge * (0.06 * iColC + 0.03 * iColB);

    // keep it luminous but restrained
    col = max(col, vec3(0.0));
    col = col / (1.0 + col * 1.45);
    col = pow(col, vec3(0.92));

    fragColor = vec4(col, 1.0);
}