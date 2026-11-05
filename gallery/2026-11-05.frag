// One Veil Down Deep - art of the day 2026-11-05
// A single curtain of muted aqua light hangs off-centre in deep petrol water, widening, swaying and brightening slowly through the day while the dark around it stays still.
float h1(float x){return fract(sin(x*127.1)*43758.5453);}
float n1(float x){float i=floor(x);float f=fract(x);f=f*f*(3.0-2.0*f);return mix(h1(i),h1(i+1.0),f);}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float day=clamp((iClock-7.0)/16.0,0.0,1.0);
vec2 uv=fragCoord/iResolution;
float asp=iResolution.x/iResolution.y;
float t=iTime;
float sway=0.04*sin(t*0.03+uv.y*2.2)+0.025*sin(t*0.017+uv.y*4.1+iEvolve.x)+0.006*sin(iBeatPhase*6.2832)*uv.y;
sway*=mix(0.6,1.6,day);
float cx=mix(0.36,0.62,day)+0.04*iEvolve.y+0.03*(h1(iSong*7.3+1.0)-0.5);
float w=mix(0.05,0.11,day)*(1.0+0.12*iBreath+0.1*iEvolve.z);
float rip=(0.25+0.6*iBright)*smoothstep(0.6,0.85,day)*0.025*n1(uv.y*9.0+t*0.05);
float dx=abs(uv.x-cx-sway)*asp;
dx=max(dx-rip,0.0);
float core=exp(-dx*dx/(w*w*(1.0-0.25*iTension)));
float halo=exp(-dx*dx/(w*w*6.0))*0.3;
float vert=smoothstep(1.02,0.55,uv.y)*0.35+0.65;
vert*=smoothstep(-0.05,0.35,uv.y)*0.5+0.5;
float hr=floor((1.0-uv.y)*24.0);
float mem=0.0;
for(int i=0;i<24;i++){if(float(i)==hr)mem=iDay[i];}
float v=(core+halo)*vert*(0.9+0.15*mem);
float k=0.5+0.5*sin(iKey);
vec3 ground=iColA*1.0;
ground=max(ground,vec3(0.0,0.18,0.2));
ground*=0.95+0.08*(1.0-uv.y);
vec3 form=mix(iColB,iColC,mix(0.35,0.8,day)*(0.85+0.15*k));
form=mix(form,iColB*1.3,0.1*(1.0-k));
float amp=mix(0.62,0.92,day);
vec3 col=mix(ground,form,clamp(v*amp,0.0,1.0));
col=min(col,vec3(0.72));
fragColor=vec4(col,1.0);
}