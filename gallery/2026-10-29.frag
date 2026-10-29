// Veils Under the Lake - art of the day 2026-10-29
// A few soft curtains of aqua light hang in deep petrol water, swaying almost imperceptibly, gathering and drifting across the wall as the day sinks from morning clarity into a dense, luminous night.
float h1(float x){return fract(sin(x*127.1)*43758.5);}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float day=clamp((iClock-7.0)/16.0,0.0,1.0);
vec2 uv=fragCoord/iResolution;
float asp=iResolution.x/iResolution.y;
vec2 p=vec2((uv.x-0.5)*asp,uv.y);
float t=iTime*0.02;
vec3 ground=mix(iColA,iColB,0.25*uv.y);
ground=max(ground,vec3(0.0));
float sed=0.0;
for(int i=0;i<24;i++){float fi=float(i);float e=iDay[i];float y=0.03+fi*0.004;sed+=e*0.5*exp(-pow((uv.y-y*(1.0+day))/0.01,2.0));}
float n=2.0+floor(day*2.99);
float cx=mix(-0.18,0.12,day)*asp+0.05*iEvolve.x;
float spread=mix(0.22,0.10,day)*(1.0-0.3*iTension);
float v=0.0;
for(int i=0;i<5;i++){float fi=float(i);if(fi>=n)break;
float s=h1(fi+floor(iSong*17.0)*3.1);
float x=cx+(fi-(n-1.0)*0.5)*spread+0.04*sin(t*(0.7+s)+fi*2.0+p.y*2.5+iEvolve.y)+0.004*sin(iBeatPhase*6.283);
float w=mix(0.035,0.06,day)*(1.0+0.3*iBreath)*(0.8+0.4*s)*(1.0-0.3*iBright+0.15);
float d=(p.x-x)/w;
float top=mix(0.95,0.75,s)-0.1*iEvolve.z;
float bot=mix(0.35,0.12,day)+0.1*s;
float vert=smoothstep(bot-0.15,bot+0.2,p.y)*smoothstep(top+0.05,top-0.25,p.y);
v+=exp(-d*d)*vert*(0.7+0.3*s);}
v=clamp(v,0.0,1.3);
float k=0.5+0.5*sin(iKey);
vec3 form=mix(iColB,iColC,0.55+0.25*day+0.1*k);
vec3 col=mix(ground,form,smoothstep(0.0,1.1,v));
col+=iColC*0.18*pow(clamp(v-0.6,0.0,1.0),1.5);
col=mix(col,iColB,sed*0.6);
col=max(col,vec3(0.0));
col=min(col,vec3(0.75));
fragColor=vec4(col,1.0);}