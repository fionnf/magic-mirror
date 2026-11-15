// Under Ash Ember - art of the day 2026-11-15
// A low copper ember lies under a dark umber field, breathing almost imperceptibly as the day widens, lifts, and then settles back into heat.
float sat(float x){ return clamp(x, 0.0, 1.0); }

float ease(float x){ return x * x * (3.0 - 2.0 * x); }

float sdEllipse(vec2 p, vec2 r){
    vec2 q = p / r;
    return length(q) - 1.0;
}

vec3 mix3(vec3 a, vec3 b, vec3 c, float t){
    if(t < 0.5) return mix(a, b, t * 2.0);
    return mix(b, c, (t - 0.5) * 2.0);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    vec2 uv = fragCoord / iResolution.xy;
    vec2 p = (fragCoord - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);

    float aspect = iResolution.x / iResolution.y;
    vec2 q = p;
    q.x *= aspect;

    float yShift = mix(-0.06, -0.22, day);
    yShift += 0.03 * iEvolve.x;
    yShift += 0.02 * iEvolve.y;

    float xShift = 0.03 * iEvolve.z + 0.02 * sin(6.2831 * (iClock / 24.0) + iSong * 6.0);

    float wide = mix(0.24, 0.38, day);
    wide += 0.05 * iBreath + 0.02 * iEvolve.w;
    float tall = mix(0.045, 0.070, 0.5 + 0.5 * iMid);
    tall += 0.010 * iTension;

    vec2 c = vec2(xShift, yShift);
    vec2 r = vec2(wide, tall);
    float d = sdEllipse(q - c, r);

    float core = exp(-max(d, 0.0) * 18.0);
    float glow = exp(-max(d, 0.0) * 5.5);
    float rim = exp(-abs(d) * 28.0);

    float floorGrad = smoothstep(0.40, -0.65, q.y);
    float emberLift = mix(0.18, 0.44, day);
    float emberFade = smoothstep(0.42, -0.05, q.y + emberLift * 0.2);

    float breathShape = 0.85 + 0.18 * iBreath - 0.10 * iTension;
    float density = 0.90 + 0.10 * iMid + 0.12 * iEnergy;
    float ash = smoothstep(0.10, 0.95, length(q - c) / vec2(1.0, 1.0).x);

    float sediment = 0.0;
    sediment += 0.05 * iDay[0];
    sediment += 0.04 * iDay[1];
    sediment += 0.03 * iDay[2];
    sediment += 0.02 * iDay[3];
    sediment += 0.015 * iDay[4];
    sediment = clamp(sediment, 0.0, 0.18);

    float lowerGlow = exp(-abs(q.y - (yShift - 0.02)) * 10.0) * exp(-abs(q.x - xShift) * 2.0);
    lowerGlow *= smoothstep(0.38, -0.12, q.y);

    vec3 colA = iColA;
    vec3 colB = iColB;
    vec3 colC = iColC;

    vec3 bg = mix(colA, colB, 0.18 + 0.12 * floorGrad);
    bg += 0.03 * vec3(0.08, 0.02, 0.00) * floorGrad;
    bg += sediment * vec3(0.06, 0.03, 0.01);

    float hueTilt = 0.08 + 0.10 * day + 0.05 * iBright;
    vec3 emberBase = mix(colB, colC, hueTilt);
    emberBase = mix(emberBase, colA, 0.14 * (1.0 - day));

    vec3 ember = bg;
    ember += emberBase * (0.45 * glow + 0.90 * core);
    ember += vec3(0.10, 0.04, 0.02) * rim * 0.8;
    ember += vec3(0.07, 0.03, 0.01) * lowerGlow * density;

    float underAsh = smoothstep(-0.35, 0.30, q.y);
    ember *= mix(1.0, 0.88, underAsh * 0.2);

    float vign = 1.0 - 0.10 * length(q * vec2(0.90, 1.15));
    ember *= vign;

    float contrast = mix(0.80, 1.10, day);
    ember = bg + (ember - bg) * contrast;

    float a = clamp(core * 0.95 + glow * 0.55, 0.0, 1.0);
    vec3 outCol = mix(bg, ember, a);

    outCol += 0.02 * iBreath * vec3(0.08, 0.03, 0.01) * (1.0 - smoothstep(0.10, 0.50, abs(q.y - yShift)));
    outCol += 0.02 * iBright * vec3(0.05, 0.02, 0.01) * rim;

    outCol = clamp(outCol, vec3(0.0), vec3(1.0));
    fragColor = vec4(outCol, 1.0);
}
