// Light Far Down - art of the day 2026-10-30
// A single veil of muted aqua hangs in deep petrol water, swaying like the last daylight reaching the bottom of a lake, widening and rising through the day until by night it fills the depth with a soft drowned glow.
float h1(float n){return fract(sin(n*12.9898)*43758.5453);}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float day=clamp((iClock-7.0)/16.0,0.0,1.0);
vec2 uv=fragCoord/iResolution;
float asp=iResolution.x/iResolution.y;
vec2 p=vec2((uv.x-0.5)*asp,uv.y);
float t=iTime;
float seed=h1(iSong*7.1)*6.28;
float cx=0.12*sin(t*0.013+iEvolve.x*0.8)+0.06*sin(t*0.031+seed)+0.05*sin(iKey);
float sway=0.04*sin(p.y*3.0+t*0.05+seed)+0.01*sin(iBeatPhase*6.283);
float w=mix(0.07,0.24,day)*asp*(1.0+0.15*iBreath+0.1*iEvolve.y);
float x=p.x-cx-sway*(1.0-p.y*0.5);
float folds=3.0+iEvolve.z+iTension*1.5;
float inner=0.75+0.25*cos(x/w*folds*1.5+t*0.02+seed);
float soft=mix(1.6,1.0,iBright);
float veil=exp(-pow(abs(x)/w,2.0)/soft)*inner;
float top=mix(0.55,0.95,day)+0.04*iEvolve.w;
float vfade=smoothstep(top+0.1,top-0.25,p.y)*smoothstep(-0.05,0.35,p.y);
veil*=vfade;
float halo=exp(-abs(x)/(w*3.0))*vfade*0.25;
float tide=0.0;
for(int i=0;i<24;i++){float fi=float(i);float hx=(fi+0.5)/24.0;float e=iDay[i];tide+=e*exp(-pow((uv.x-hx)*24.0,2.0))*smoothstep(0.08*e+0.01,0.0,uv.y);}
vec3 ground=mix(iColA,iColB,0.25+0.2*uv.y);
ground=max(ground,vec3(0.02,0.18,0.2));
vec3 aqua=mix(iColB,iColC,mix(0.45,0.85,day));
vec3 col=ground+(iColB-ground)*halo;
col=mix(col,aqua,clamp(veil*mix(0.75,0.9,day),0.0,1.0));
col=mix(col,iColB,clamp(tide*0.5,0.0,0.5));
col=min(col,vec3(0.75));
fragColor=vec4(col,1.0);}