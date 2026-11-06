// Ink Swell, One Crest - art of the day 2026-11-06
// A single long crest of deep water seen from above rises out of an ink-navy field, lit faintly as if by a moon you cannot see, and through the day it travels up the wall, broadens and gathers the hours' music as faint tide marks below it.
float hsh(float n){return fract(sin(n*91.7)*43758.5);}
float vn(vec2 p){vec2 i=floor(p);vec2 f=fract(p);f=f*f*(3.0-2.0*f);float a=hsh(i.x+i.y*57.0),b=hsh(i.x+1.0+i.y*57.0),c=hsh(i.x+(i.y+1.0)*57.0),d=hsh(i.x+1.0+(i.y+1.0)*57.0);return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float day=clamp((iClock-7.0)/16.0,0.0,1.0);
vec2 uv=fragCoord/iResolution;float asp=iResolution.x/iResolution.y;
vec2 p=vec2((uv.x-0.5)*asp,uv.y);
float t=iTime*0.02;
float sd=hsh(iSong+3.1);
float cy=mix(0.30,0.58,day)+0.03*iEvolve.y;
float bend=0.06*sin(p.x*(2.2+0.6*iEvolve.x)+t*1.3+sd*6.28)+0.03*sin(p.x*4.1-t*0.7+iClock*0.3)+0.004*sin(iBeatPhase*6.2832);
float y=p.y-cy-bend;
float w=mix(0.07,0.17,day)*(1.0+0.25*iBreath+0.15*iEvolve.z);
float body=exp(-pow(max(y,0.0)/(w*0.6),2.0))*exp(-pow(min(y,0.0)/(w*1.6),2.0));
float sharp=mix(0.03,0.015,iBright)*(1.0-0.3*iTension);
float crest=exp(-pow((y-w*0.15)/sharp,2.0))*0.6;
float len=smoothstep(0.75*asp,0.15*asp,abs(p.x-0.08*iEvolve.w));
float n=vn(p*3.0+vec2(t,-t*0.6))*0.5+vn(p*7.0-t)*0.25;
body*=len*(0.8+0.3*n);crest*=len*(0.7+0.4*n);
float marks=0.0;
for(int i=0;i<24;i++){float fi=float(i);if(fi>iClock)break;float e=iDay[i];float yy=cy-w*1.2-0.012*(iClock-fi)*1.0;float d=abs(p.y-yy-bend*0.6);marks+=e*exp(-pow(d/0.008,2.0))*0.35;}
marks=min(marks,0.4)*len;
vec3 ground=mix(iColA,iColB,0.18+0.12*uv.y*(1.0-day*0.3));
ground=max(ground,vec3(0.0,0.03,0.18));
float k=0.5+0.5*sin(iKey);
vec3 steel=mix(iColB,iColC,0.55+0.2*day);
steel=mix(steel,steel*vec3(0.92,1.0,1.08),k);
vec3 col=ground;
col=mix(col,mix(iColB,steel,0.4),clamp(body*mix(0.75,0.9,day),0.0,1.0));
col=mix(col,steel,clamp(crest*(0.8+0.2*day),0.0,1.0));
col=mix(col,iColB*1.2,marks);
col=min(col,vec3(0.75));
fragColor=vec4(col,1.0);}