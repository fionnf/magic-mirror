// Halftone Halo - art of the day 2026-11-04
// A single ring of living halftone light hangs in a dark room, warming from magenta to orange as the day gathers and then settles into a glowing afterimage by night.
vec3 paletteMix(float t){
    return mix(mix(iColA, iColB, smoothstep(0.0, 0.55, t)), iColC, smoothstep(0.25, 1.0, t));
}

float hash12(vec2 p){
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float sdRing(vec2 p, float r){
    return abs(length(p) - r);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    vec2 res = iResolution.xy;
    vec2 p = (fragCoord - 0.5 * res) / min(res.x, res.y);

    float asp = res.x / res.y;
    p.x *= asp;

    float tslow = iTime * 0.028;
    float evo = dot(iEvolve, vec4(0.20, 0.17, 0.13, 0.11));
    float song = iSong;
    float breath = iBreath;
    float bright = iBright;
    float energy = max(iEnergy, max(iBass, max(iMid, iTreble)));

    vec3 bg = iColA * 0.75;
    bg += iColB * 0.03 * (0.25 + 0.75 * day);

    // Day arc: the ring grows, shifts upward a little, and becomes more open toward night.
    float radius = mix(0.18, 0.30, day);
    radius += 0.015 * sin(tslow * 1.7 + song * 6.1 + evo * 2.0);
    radius += 0.010 * (breath - 0.5);

    vec2 center = vec2(0.0, mix(-0.03, 0.06, day));
    center += 0.045 * vec2(sin(song * 5.7 + evo * 3.0), cos(song * 4.3 + evo * 2.4));
    center += 0.012 * vec2(sin(tslow * 1.3), cos(tslow * 1.1));

    vec2 q = p - center;
    float r = length(q);
    float a = atan(q.y, q.x);

    // Wide luminous annulus.
    float ringW = mix(0.085, 0.120, day) + 0.010 * evo;
    float ring = exp(-pow((r - radius) / ringW, 2.0));

    // Halftone dots: larger in the middle of the ring, quiet and spaced.
    float dots = 0.0;
    float nDots = mix(58.0, 84.0, day) + 4.0 * floor(0.5 + evo);
    float ang = a + 0.12 * sin(tslow * 0.7 + evo);
    float angCell = ang / (6.2831853 / nDots);
    float cell = floor(angCell);
    float f = fract(angCell) - 0.5;
    float seed = hash12(vec2(cell, floor((r - radius) * 34.0)) + song * 13.0);
    float ringBand = 1.0 - smoothstep(0.0, ringW * 1.15, abs(r - radius));
    float dotSize = mix(0.015, 0.040, ringBand);
    dotSize *= mix(0.70, 1.20, seed);
    dotSize *= mix(0.85, 1.15, bright);

    float dAng = abs(f) * 2.0 * radius;
    float dRad = abs(r - radius);
    float dot = 1.0 - smoothstep(dotSize, dotSize + 0.012, length(vec2(dAng, dRad * 1.6)));
    dot *= ringBand;

    // Breathing thickness variation, very slow.
    float asym = 0.10 * sin(a * 2.0 + tslow * 0.6 + song * 4.0);
    float wave = 0.04 * sin(a * 3.0 - tslow * 0.9 + evo * 2.5);
    ring *= 1.0 + asym + wave;

    // Hollow center stays dark.
    float hollow = smoothstep(radius - ringW * 0.95, radius - ringW * 0.10, r);
    hollow *= 1.0 - smoothstep(radius + ringW * 0.55, radius + ringW * 1.30, r);

    // Glow core inside the ring to keep it luminous on LEDs.
    float innerGlow = exp(-pow((r - radius) / (ringW * 0.55), 2.0));
    innerGlow *= 0.65;

    // Outer aura, stronger at dawn and in quieter music.
    float aura = exp(-pow((r - radius) / (ringW * 2.6), 2.0));
    aura *= mix(0.80, 0.45, day);

    // Composition sediment from the day: faint additional ring memory from iDay.
    float hour = clamp(iClock, 0.0, 23.999);
    float h0 = floor(hour);
    float h1 = min(23.0, h0 + 1.0);
    float hf = fract(hour);
    float dayMem = mix(iDay[int(h0)], iDay[int(h1)], hf);
    float sediment = smoothstep(0.18, 0.82, dayMem);
    float oldRing = exp(-pow((r - (radius * (0.86 + 0.05 * sediment))) / (ringW * 1.4), 2.0));
    oldRing *= 0.20 * sediment;

    // Color: magenta on shadow side, warm orange on highlight side.
    float warm = smoothstep(-0.15, 0.45, q.x * 0.55 + q.y * 0.18 + 0.20 * sin(a + evo));
    vec3 ringCol = mix(iColB, iColC, warm);
    ringCol = mix(ringCol, iColC, 0.30 + 0.35 * bright);

    vec3 col = bg;
    col += ringCol * (0.95 * ring + 1.35 * dot + 0.90 * innerGlow);
    col += mix(iColB, iColC, 0.65) * aura * 0.40;
    col += mix(iColA, iColB, 0.35) * oldRing * 0.55;

    // Keep the center empty but not dead black.
    float centerLift = smoothstep(0.0, radius - ringW * 0.95, r) * 0.08;
    col += iColA * centerLift;

    // Make the main form luminant enough for the real wall; protect the dark ground.
    float exposure = mix(1.08, 1.35, day) + 0.10 * bright + 0.06 * energy;
    col *= exposure;
    col = max(col, vec3(0.0));

    // Gentle highlight compression without crushing the glow.
    col = col / (1.0 + 0.28 * col);
    col += 0.02 * iColC * aura;

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}