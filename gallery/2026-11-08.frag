// Ink Tide, One Crest - art of the day 2026-11-08
// A single long swell moves through deep ink-blue water seen from above, its crest catching a faint steel light that rises, broadens and travels up the wall as the day goes on.
float hsh(float n){return fract(sin(n*91.345)*43758.5453);}
void mainImage(out vec4 fragColor, in vec2 fragCoord){
float day=clamp((iClock-7.0)/16.0,0.0,1.0);
vec2 uv=fragCoord/iResolution.xy;
float asp=iResolution.x/iResolution.y;
vec2 p=vec2((uv.x-0.5)*asp,uv.y);
float t=iTime;
float cy=mix(0.30,0.62,day)+0.03*iEvolve.x+0.02*sin(t*0.013);
float amp=0.06+0.03*iEvolve.y+0.02*sin(iSong*6.28);
float ph=t*0.02+iSong*3.0+0.01*sin(iBeatPhase*6.2832);
float w=cy+amp*sin(p.x*2.2+ph)+0.025*sin(p.x*4.1-t*0.011+iEvolve.z*2.0);
float d=p.y-w;
float width=mix(0.05,0.12,day)*(1.0+0.3*iBreath)*(1.0-0.25*iTension)*(1.0+0.2*iEvolve.w);
float crest=exp(-d*d/(width*width));
float core=exp(-d*d/(width*width*0.12));
float back=smoothstep(0.0,-0.5,d)*0.25;
float tide=0.0;
for(int i=0;i<24;i++){float fi=float(i);if(fi>iClock)break;float e=iDay[i];float ty=w-0.06-fi*0.012*(1.0+day);float dd=p.y-ty;tide+=e*exp(-dd*dd/0.00012)*0.35;}
float glint=0.0;
if(iBright>0.01){float g=hsh(floor(p.x*40.0)+floor(t*0.05)*17.0);glint=step(0.93-0.05*iBright,g)*core*0.25*iBright;}
float kt=0.5+0.5*sin(iKey);
vec3 ground=mix(iColA,iColB,0.18+0.1*uv.y);
ground=max(ground,vec3(0.03,0.07,0.19));
vec3 mid=mix(iColB,iColB*vec3(0.9,1.0,1.1),kt);
vec3 col=ground;
col=mix(col,mid,back+tide);
col=mix(col,mid,crest*0.85);
col=mix(col,mix(mid,iColC,0.5+0.3*day),core*mix(0.55,0.85,day)+glint);
col=min(col,vec3(0.72));
fragColor=vec4(col,1.0);
}