// The Champagne Gap - art of the day 2026-10-22
// A single hairline of pale gold light draws itself around the dark. It is a wide open arc at breakfast, almost seals into a full ring by evening and loosens again after midnight, and the day's music is written into its thickness, one hour to each sliver of the circle.
float hsh(float n){return fract(sin(n*127.1)*43758.5453);}
float dayAt(float h){int i=int(mod(h,24.0));return clamp(iDay[i],0.0,1.0);}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float PI=3.14159265;float TAU=6.2831853;
vec2 uv=(fragCoord-0.5*iResolution)/min(iResolution.x,iResolution.y);
float t=iTime;float day=iClock/24.0;
vec2 c=vec2(0.025*sin(t*0.0051)+0.012*sin(t*0.0013+1.7),0.03*cos(t*0.0037)+0.02*cos(TAU*day));
c.x+=0.0015*sin(iBeatPhase*TAU);
vec2 p=uv-c;float r=length(p);float a=atan(p.y,p.x);
float song=hsh(iSong*13.7+0.3);
float R=0.29+0.035*sin(t*0.0071)+0.02*sin(t*0.0023+2.0)+0.03*sin(TAU*(day-0.25))+0.025*iBreath;
R+=0.004*sin(3.0*a+song*TAU);
float g=0.5+0.5*cos(TAU*(iClock-19.5)/24.0);
float gap=mix(1.7,0.035,g*g*(3.0-2.0*g));
gap*=(1.0-0.45*iTension);gap+=0.08*sin(t*0.0043);gap=max(gap,0.02);
float ga=t*0.011+iClock*0.26+0.6*sin(t*0.0029)+0.25*sin(iKey);
float dd=abs(mod(a-ga+PI,TAU)-PI);
float mask=smoothstep(gap,gap+0.35,dd);
float hp=(a+PI)/TAU*24.0;float hf=fract(hp-0.5);float h0=floor(hp-0.5);
float e=mix(dayAt(h0),dayAt(h0+1.0),smoothstep(0.0,1.0,hf));
float w=0.0045+0.0075*e+0.0015*sin(a*2.0+t*0.006);
float dr=r-R;
float core=exp(-(dr*dr)/(w*w));
float hw=0.05+0.03*iBright;
float halo=exp(-abs(dr)/hw);
float wide=exp(-abs(dr)/0.18);
vec2 tip1=c+R*vec2(cos(ga+gap),sin(ga+gap));
vec2 tip2=c+R*vec2(cos(ga-gap),sin(ga-gap));
float tipv=smoothstep(0.03,0.2,gap);
float tips=(exp(-length(uv-tip1)/0.025)+exp(-length(uv-tip2)/0.025))*tipv;
float ys=fragCoord.y/iResolution.y;
vec3 ground=iColA*(0.85+0.25*ys);
ground+=iColB*0.05*exp(-r/0.4);
float night=smoothstep(0.0,1.0,abs(iClock-12.0)/12.0);
float lvl=0.95-0.2*night*night;
vec3 gold=mix(iColB,iColC,0.55+0.2*sin(iKey));
vec3 champ=mix(iColC,iColB,0.12+0.1*cos(iKey));
vec3 col=ground;
col+=gold*wide*0.10*mask*lvl;
col+=gold*halo*0.38*mask*lvl;
col+=mix(gold,champ,core)*core*0.88*mask*lvl;
col+=champ*tips*0.35*lvl;
col=mix(col,ground+gold*0.02,0.0);
col=min(col,vec3(0.95));
fragColor=vec4(col,1.0);
}