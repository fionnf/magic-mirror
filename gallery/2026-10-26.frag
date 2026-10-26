// Luminous Current - art of the day 2026-10-26
// A comb of glowing strands is released from one edge and carried through a slow two-wave field, gathering into a richer, broader flow as the day deepens.
vec3 palMix(vec3 a, vec3 b, vec3 c, float t){
    t = clamp(t, 0.0, 1.0);
    if(t < 0.5){
        return mix(a, b, t * 2.0);
    }
    return mix(b, c, (t - 0.5) * 2.0);
}

float hash11(float p){
    return fract(sin(p * 127.1 + 311.7) * 43758.5453123);
}

float lineHead(vec2 p, vec2 a, vec2 b, float w){
    vec2 pa = p - a;
    vec2 ba = b - a;
    float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
    vec2 q = pa - ba * h;
    float d = length(q);
    float head = smoothstep(0.25, 1.0, h);
    float tail = smoothstep(1.0, 0.72, h);
    float core = smoothstep(w, 0.0, d);
    float halo = smoothstep(w * 2.8, w * 0.8, d);
    return core * (0.35 + 0.65 * head) + halo * 0.22 * tail;
}

float curveY(float x, float t, float seed, float day, float energy){
    float drift = 0.02 * sin(t * 0.03 + seed * 6.3 + day * 2.2);
    float wave1 = sin(x * (2.0 + 1.2 * day) + t * (0.06 + 0.02 * energy) + seed * 4.7);
    float wave2 = sin(x * (5.0 - 1.3 * day) - t * 0.041 + seed * 2.1);
    float arch = (0.18 + 0.22 * day) * (x - 0.15) * (x - 0.85);
    return drift + arch + 0.050 * wave1 + 0.024 * wave2;
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);

    vec2 uv = fragCoord / iResolution.xy;
    vec2 p = uv * 2.0 - 1.0;
    p.x *= iResolution.x / iResolution.y;

    float t = iTime;
    float slow = iTime * 0.03;
    float breath = iBass;
    float bright = iTreble;
    float energy = iEnergy;
    float mood = 0.35 + 0.65 * day;

    vec3 colA = iColA;
    vec3 colB = iColB;
    vec3 colC = iColC;

    vec3 bg = colA * 0.70 + colB * 0.03;
    bg += 0.012 * colB * (0.5 + 0.5 * sin((uv.y + 0.15 * day) * 6.0 + slow));

    float field = 0.0;
    float glow = 0.0;
    float heads = 0.0;

    float count = mix(6.0, 13.0, day);
    float x0 = mix(-0.82, -0.58, day);
    float ySpread = mix(0.18, 0.42, day);
    float bend = mix(0.10, 0.30, day);

    for(int i = 0; i < 14; i++){
        float fi = float(i);
        if(fi >= count) break;

        float seed = hash11(fi + floor(iSong * 17.0));
        float yOff = (seed - 0.5) * 2.0 * ySpread;
        float xStart = x0 + 0.035 * sin(seed * 31.0 + slow * 2.0);
        float xEnd = mix(0.78, 1.12, day) + 0.06 * sin(seed * 9.0 + slow * 1.3);

        float y0 = yOff + 0.03 * sin(seed * 19.0 + t * 0.02);
        float y1 = yOff + bend * (0.35 + 0.65 * seed) + 0.16 * sin(seed * 7.0 + 1.4);

        float px = smoothstep(0.0, 1.0, (uv.x - 0.06) / 0.94);
        float x = mix(xStart, xEnd, px);
        float yc = mix(y0, y1, px);
        yc += curveY(px, t, seed, day, energy) * (0.90 + 0.25 * breath);

        vec2 a = vec2(xStart, y0);
        vec2 b = vec2(xEnd, yc);
        float w = mix(0.010, 0.018, day) * (1.0 + 0.20 * bright);
        float d = lineHead(vec2(uv.x * 2.0 - 1.0, uv.y * 2.0 - 1.0), a, b, w);

        float headPos = mix(0.62, 0.88, day) + 0.03 * sin(t * 0.02 + seed * 9.0);
        float headGlow = exp(-pow((px - headPos) / mix(0.07, 0.05, day), 2.0));
        float strand = d * (0.70 + 0.30 * headGlow);
        field += strand;
        glow += strand * (0.6 + 0.8 * headGlow);
        heads += headGlow * (0.35 + 0.65 * seed);
    }

    float ribbon = smoothstep(0.0, 0.22, field);
    float core = smoothstep(0.15, 0.85, field);
    float halo = smoothstep(0.0, 0.55, glow);

    float xBand = smoothstep(0.05, 0.78, uv.x);
    float yFade = 1.0 - smoothstep(0.70, 1.12, abs(uv.y - 0.53 - 0.10 * day));
    float mist = 0.02 * halo * xBand * yFade;

    float keyT = fract(iKey / 6.2831853);
    vec3 tint = palMix(colA, colB, colC, clamp(0.18 + 0.55 * keyT + 0.18 * day, 0.0, 1.0));
    vec3 lineCol = mix(colB, colC, 0.55 + 0.35 * day);
    lineCol = mix(lineCol, tint, 0.35);

    vec3 color = bg;
    color += lineCol * (0.45 * field + 0.55 * halo);
    color += colC * (0.35 * heads + 0.18 * core);
    color += colB * mist;

    float edgeGlow = smoothstep(0.0, 0.22, uv.x) * smoothstep(0.0, 0.18, 1.0 - abs(uv.y - 0.45));
    color += (0.04 + 0.06 * day) * colB * edgeGlow * (0.5 + 0.5 * bright);

    float vign = 1.0 - 0.18 * dot(p, p);
    color *= vign;

    color = max(color, vec3(0.0));
    color = mix(color, color + 0.08 * colC, 0.12 * iMid);
    fragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
}