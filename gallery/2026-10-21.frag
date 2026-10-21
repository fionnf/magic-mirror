// Cobalt Vessel, Filling - art of the day 2026-10-21
// A single tall capsule of cobalt neon stands in the dark and slowly fills with pale mint light from morning to midnight, while its own glow pools and mirrors on an unseen floor below.
float hourE(float a){float x=fract(a)*24.0;float i0=floor(x);float f=x-i0;int a0=int(mod(i0,24.0));int a1=int(mod(i0+1.0,24.0));float e=mix(iDay[a0],iDay[a1],smoothstep(0.0,1.0,f));float played=smoothstep(i0-0.5,i0+0.5,iClock);return mix(0.32,0.5+0.7*e,played);}
float capD(vec2 p,float h,float r){return length(p-vec2(0.0,clamp(p.y,-h,h)))-r;}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
vec2 uv=(fragCoord-0.5*iResolution.xy)/iResolution.y;
float t=iTime;float asp=iResolution.x/iResolution.y;
float grow=smoothstep(5.0,13.0,iClock);float late=smoothstep(18.0,23.5,iClock);
float fillAmt=0.08+0.8*smoothstep(6.0,23.5,iClock);
float h=0.09+0.11*grow+0.015*sin(t*0.013)+0.01*sin(t*0.0031+2.0);
float r=0.095*(0.85+0.15*grow)*min(1.0,asp*1.1);
vec2 c=vec2(0.03*sin(t*0.007+iSong*6.283)+0.004*sin(iBeatPhase*6.283),0.07+0.02*sin(t*0.009)-0.04*late);
float ang=0.035*sin(t*0.005+1.0);float cs=cos(ang),sn=sin(ang);
vec2 q=uv-c;vec2 p=vec2(cs*q.x-sn*q.y,sn*q.x+cs*q.y);
float d=capD(p,h,r);
float w=0.0035+0.0025*(1.0-iTension);
float line=smoothstep(w*1.6,0.0,abs(d));
float halo=exp(-abs(d)*30.0);
float wide=exp(-max(d,0.0)*6.0)*0.22;
float a=atan(p.x,-p.y)/6.2832+0.5;
float li=hourE(a);
float bottom=-h-r;float level=bottom+(2.0*h+2.0*r)*fillAmt+0.004*sin(t*0.04+p.x*14.0)+0.006*iBreath;
float inside=smoothstep(0.004,-0.004,d);
float below=smoothstep(0.006,-0.006,p.y-level);
float men=exp(-abs(p.y-level)*110.0)*inside;
float keyT=0.5+0.5*sin(iKey);
vec3 neon=mix(iColB,iColC,0.5+0.15*keyT+0.25*late);
vec3 fillC=mix(iColB,iColC,0.2+0.2*keyT+0.2*late);
float fy=c.y-h-r-0.05-0.03*late;
float dx=uv.x-c.x;
float pw=0.16+0.14*fillAmt+0.03*iBreath;
float pool=exp(-pow(dx/pw,2.0)-pow((uv.y-fy)/(0.03+0.015*fillAmt),2.0))*(0.3+0.45*fillAmt);
float refl=0.0;
if(uv.y<fy){vec2 m=vec2(uv.x,2.0*fy-uv.y)-c;vec2 pm=vec2(cs*m.x-sn*m.y,sn*m.x+cs*m.y);float dm=capD(pm,h,r);refl=(exp(-abs(dm)*22.0)*0.5+smoothstep(0.004,-0.004,dm)*smoothstep(0.01,-0.01,pm.y-level)*0.25)*exp((uv.y-fy)*10.0);}
vec3 bg=iColA*(0.75+0.35*(uv.y+0.5));
bg+=iColB*0.05*exp(-length(uv-c)*2.5);
vec3 col=bg;
col+=iColB*halo*0.55*li;
col+=iColB*wide*(0.45+0.25*iBright);
col+=neon*line*li*1.1;
col+=fillC*0.32*inside*below;
col+=fillC*inside*below*exp(-(level-p.y)*8.0)*0.12;
col+=mix(iColB,iColC,0.7)*men*0.45;
col+=mix(iColB,iColC,0.3)*pool;
col+=mix(iColB,neon,0.4)*refl*0.6;
col+=iColB*0.04*iBright*exp(-length(uv-c)*3.0);
col=col/(1.0+col*0.35);
fragColor=vec4(clamp(col,0.0,1.0),1.0);}