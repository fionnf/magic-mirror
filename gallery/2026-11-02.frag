// Amber Aperture - art of the day 2026-11-02
// A soft rectangular window of amber light hovers in darkness, breathing from a narrow morning slit into a fuller evening glow as the day leaves faint sediment in its frame.
float saturate(float x){ return clamp(x,0.0,1.0); }

float hash12(vec2 p){
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float sdRoundRect(vec2 p, vec2 b, float r){
    vec2 q = abs(p) - b;
    return length(max(q, 0.0)) - r + min(max(q.x, q.y), 0.0);
}

float softBand(float x, float w){
    return exp(-(x*x) / max(w, 1e-4));
}

vec3 toneMix(vec3 a, vec3 b, vec3 c, float t){
    vec3 m1 = mix(a, b, smoothstep(0.0, 0.55, t));
    return mix(m1, c, smoothstep(0.45, 1.0, t));
}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
    float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
    vec2 res = iResolution.xy;
    vec2 uv = (fragCoord - 0.5 * res) / min(res.x, res.y);

    float nDay = 0.0;
    for(int h = 0; h < 24; h++){
        float hh = float(h);
        float w = exp(-abs(iClock - hh) * 0.12);
        nDay += iDay[h] * w;
    }
    nDay = nDay / 8.0;

    float bass = saturate(iBass + 0.55 * iEnergy);
    float bright = saturate(iTreble + 0.35 * iMid);
    float tension = saturate(iTension);
    float evoA = iEvolve.x * 0.18 + iEvolve.y * 0.10;
    float evoB = iEvolve.z * 0.08 + iEvolve.w * 0.06;
    float t = iTime * 0.02;

    // Dark luminous ground
    vec3 bg = iColA * 0.30 + vec3(0.012, 0.014, 0.022);
    bg += 0.015 * nDay * vec3(0.55, 0.26, 0.08);
    bg += 0.010 * softBand(uv.y + 0.18, 0.65) * vec3(0.16, 0.08, 0.03);

    // One soft-edged rectangular aperture, varying strongly through the day.
    vec2 center = vec2(0.03 * sin(t + 6.2831 * iSong), -0.08 + 0.32 * day + 0.03 * bass + 0.02 * evoA);
    vec2 p = uv - center;

    vec2 halfSize = vec2(mix(0.14, 0.29, day) + 0.03 * bass + 0.02 * evoB,
                         mix(0.42, 0.24, day) + 0.015 * bright);
    float radius = mix(0.08, 0.16, day) + 0.01 * tension;
    float d = sdRoundRect(p, halfSize, radius);

    float fill = exp(-pow(max(d, 0.0) / (0.16 + 0.05 * day), 2.0));
    float core = exp(-pow(d / (0.12 + 0.03 * day), 2.0));
    float rim = exp(-pow(abs(d) / (0.030 + 0.010 * (1.0 - day)), 2.0));

    // Light bleeding past the frame: a wider glow, but not too bright overall.
    float bleed = exp(-pow(max(d + 0.02, 0.0) / (0.28 + 0.08 * day), 2.0));
    float spread = exp(-pow(length(p * vec2(1.0, 1.10)) / (0.70 + 0.12 * day), 2.0));

    // Slight asymmetry and slow life in the aperture body.
    float innerTilt = 0.5 + 0.5 * tanh(2.5 * (p.y + 0.12 * sin(t + 1.7 * iSong)));
    float glaze = mix(0.72, 1.0, innerTilt);
    glaze *= 0.92 + 0.08 * sin(3.1415 * (p.x * 1.3 + 0.15 * evoA));

    // Palette: deep amber shadow, warm gold mid, luminous soft highlight.
    vec3 sh = iColA;
    vec3 md = mix(iColB, vec3(0.78, 0.48, 0.16), 0.55);
    vec3 hi = mix(iColC, vec3(1.00, 0.82, 0.50), 0.60);

    // Day arc: dawn as a narrower slit; noon opens; evening deepens and warms.
    float openAmt = mix(0.30, 1.00, day);
    float warmth = mix(0.52, 1.00, day);
    float hueShift = 0.08 * sin(0.5 * iClock + 6.0 * iSong) + 0.05 * nDay;

    vec3 aperture = sh * (0.20 * fill + 0.10 * bleed);
    aperture += md * (0.55 * core * openAmt * glaze);
    aperture += hi * (0.92 * rim * (0.55 + 0.45 * bright));
    aperture += vec3(1.0, 0.82, 0.45) * (0.28 * spread * (0.35 + 0.65 * day) * warmth);
    aperture *= vec3(1.0 + hueShift, 1.0 + 0.30 * hueShift, 1.0 - 0.10 * hueShift);

    // Frame shadow just outside the aperture, keeping the rectangle legible on a dark wall.
    float frame = smoothstep(0.035, 0.0, abs(d) - 0.015) - smoothstep(0.10, 0.22, abs(d));
    vec3 frameCol = mix(iColA, vec3(0.22, 0.13, 0.06), 0.65) * frame * 0.18;

    // A faint accumulated tide mark from the day, strongest by evening.
    float tide = smoothstep(0.15, 0.95, nDay) * exp(-pow((p.y + 0.36 - 0.10 * day) / 0.09, 2.0));
    vec3 sediment = vec3(0.32, 0.18, 0.07) * tide * 0.12;

    vec3 col = bg + frameCol + sediment + aperture;

    // Keep the piece luminous but avoid a too-bright wash.
    col = clamp(col, 0.0, 1.0);
    col = mix(col, col * 0.92, 0.12 * smoothstep(0.75, 1.0, day));

    fragColor = vec4(col, 1.0);
}