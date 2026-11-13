// Edge Current - art of the day 2026-11-13
// A comb of luminous lines slips in from the edge and is bent by a slow two-wave field, so the wall reads like a quiet current that thickens, travels, and gathers memory over the day.
float satf(float x){ return clamp(x,0.0,1.0); }
float hash11(float n){ return fract(sin(n*91.17+13.7)*43758.5453123); }
float hash21(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453123); }

float lineSeg(vec2 p, vec2 a, vec2 b){
    vec2 pa = p - a;
    vec2 ba = b - a;
    float h = clamp(dot(pa,ba)/dot(ba,ba),0.0,1.0);
    return length(pa - ba*h);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    vec2 uv = fragCoord / iResolution.xy;
    vec2 p = uv * 2.0 - 1.0;
    p.x *= iResolution.x / iResolution.y;

    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    float t = iTime * 0.03;
    float evo = iEvolve.x * 0.12 + iEvolve.y * 0.09 + iEvolve.z * 0.07 + iEvolve.w * 0.05;
    float keyShift = 0.12 * sin(iKey + 6.2831 * 0.25);

    vec3 colA = iColA;
    vec3 colB = mix(iColA, iColB, 0.65 + 0.20 * day);
    vec3 colC = mix(iColB, iColC, 0.70 + 0.10 * day);

    vec3 bg = colA * (0.90 + 0.08 * day);
    float glow = 0.0;

    float lineCount = mix(6.0, 11.0, day);
    lineCount += floor(2.0 * satf(iLevel) + 1.5 * satf(iEnergy));
    lineCount += floor(1.0 + 1.5 * satf(iSong));

    float waveA = sin(p.y * 2.5 + t * 0.8 + evo * 3.0 + keyShift);
    float waveB = sin(p.y * 5.1 - t * 0.55 - evo * 2.4 + 1.7 * keyShift);
    float field = 0.11 * waveA + 0.07 * waveB;
    field += 0.05 * sin(p.x * 2.2 + p.y * 1.3 + 0.6 * sin(t));

    float edge = mix(-1.08, -0.82, day);
    float lift = mix(-0.18, 0.20, day);
    float bend = mix(0.10, 0.28, day);
    float spread = mix(0.24, 0.40, day);

    for(int i=0; i<14; i++){
        float fi = float(i);
        float m = step(fi, lineCount - 0.5);
        float f = fi / 13.0;
        float s = hash11(fi + 9.0 * iSong);
        float x0 = edge + 0.10 * f + 0.03 * sin(fi * 1.7 + iSong * 6.0);
        float y0 = mix(-0.72, 0.58, f) + lift + 0.08 * sin(fi * 0.9 + iSong * 5.0);
        y0 += 0.10 * (iBass - 0.5);
        float travel = 0.58 + 0.38 * day + 0.06 * iEvolve.x;
        vec2 a = vec2(x0, y0);
        vec2 b = vec2(x0 + travel, y0 + 0.18 * sin(2.2 * f + t + evo));

        vec2 pp = p;
        pp.y += field * (0.85 + 0.25 * f);
        pp.x += bend * (pp.y * pp.y - 0.14) + 0.06 * sin(pp.y * 1.7 + 1.5 * f + evo);

        float d = lineSeg(pp, a, b);
        float head = clamp(1.0 - abs(lineSeg(pp, b - normalize(b-a)*0.04, b)) / 0.04, 0.0, 1.0);
        float core = exp(-d * d * mix(180.0, 115.0, day));
        float body = exp(-d * d * mix(55.0, 28.0, day));
        float wing = exp(-d * d * 9.0);
        float taper = mix(0.55, 0.95, f) * mix(0.55, 1.0, 1.0 - f);
        float accent = 0.55 + 0.45 * sin(6.2831 * (f + 0.13 * s + 0.08 * iBright));

        vec3 lineCol = mix(colB, colC, 0.35 + 0.45 * accent + 0.10 * day);
        lineCol = mix(lineCol, colC, 0.25 + 0.35 * iTreble);
        vec3 headCol = mix(lineCol, colC, 0.70);

        glow += m * (0.90 * body * taper + 1.55 * core * (0.55 + 0.45 * iBright));
        bg += m * (0.16 * wing * lineCol + 0.48 * core * headCol * (0.70 + 0.25 * head));
    }

    // soft sediment, brighter by night but still sparse
    float sediment = 0.0;
    for(int j=0; j<24; j++){
        float fj = float(j);
        float sj = hash11(fj * 1.7 + iSong * 2.0);
        float yy = mix(-0.90, 0.86, fj / 23.0);
        float xx = mix(-1.05, -0.15, sj) + 0.06 * sin(fj + evo * 2.0);
        float dd = length((p - vec2(xx, yy)) * vec2(1.15, 1.0));
        sediment += exp(-dd * dd * 40.0) * (0.02 + 0.08 * day) * (0.4 + 0.6 * sj);
    }

    vec3 col = bg;
    col += glow * mix(colB, colC, 0.55 + 0.25 * day);
    col += sediment * mix(colA, colB, 0.6);

    float vign = smoothstep(1.35, 0.15, length(p));
    col *= 0.93 + 0.07 * vign;
    col = max(col, vec3(0.0));

    // gentle contrast for LED readability, no white blowout
    col = pow(col, vec3(0.92));
    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}