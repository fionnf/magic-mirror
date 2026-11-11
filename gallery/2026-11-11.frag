// Where the Line Opens - art of the day 2026-11-11
// A single thread of pale light descends through a deep indigo night and, at a point that sinks lower as the day goes on, loosens into a narrow soft fan of cool spectral tints, so that by midnight the line has become mostly fan.
vec3 tint(float t, float k){vec3 a=mix(iColA*1.6,iColB,smoothstep(0.0,0.5,t));vec3 b=mix(iColB,iColC,smoothstep(0.4,1.0,t));vec3 c=mix(a,b,step(0.5,t)*0.0+t);c.r*=0.85+0.25*sin(t*3.0+k);c.g*=0.9+0.15*sin(t*2.5+k+1.5);return c;}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float day=clamp((iClock-7.0)/16.0,0.0,1.0);
vec2 uv=fragCoord/iResolution.xy;float asp=iResolution.x/iResolution.y;
float x=(uv.x-0.5)*asp;float y=uv.y;
float T=iTime;
x+=0.015*iEvolve.x+0.004*sin(iBeatPhase*6.2832);
float split=mix(0.68,0.32,day)+0.04*iEvolve.y-0.05*iTension;
float below=clamp((split-y)/max(split,0.05),0.0,1.0);
float spread=mix(0.10,0.30,day)*(1.0+0.15*iBreath+0.1*iEvolve.z);
float tilt=(fract(sin(iSong*91.7)*437.1)-0.5)*0.06+0.02*sin(T*0.013);
float cx=tilt*below;
float w=0.006+spread*pow(below,1.15);
float d=(x-cx)/w;
float lineW=mix(0.012,0.008,iBright);
float line=exp(-pow((x-0.0)/lineW,2.0))*smoothstep(split-0.03,split+0.05,y)*smoothstep(1.0,0.75,y)*0.9;
float fan=smoothstep(1.1,0.75,abs(d))*smoothstep(0.0,0.06,below);
float t=clamp(d*0.5+0.5,0.0,1.0);
float k=iKey+0.4*iEvolve.w;
vec3 spec=tint(t,k);
vec3 white=mix(iColC,vec3(1.0),0.2);
float cool=smoothstep(0.0,0.35,below);
vec3 fc=mix(white,spec*1.25,cool);
float fanI=fan*mix(1.0,0.75,below)*(0.85+0.15*day);
vec3 col=iColA*0.6;
col+=iColB*0.08*exp(-abs(x)*4.0);
col=mix(col,fc,clamp(fanI,0.0,1.0));
col+=white*line;
float node=exp(-(x*x+pow(y-split,2.0))/0.0012);
col+=white*node*0.6;
float glow=exp(-pow(x/0.08,2.0))*smoothstep(split-0.1,1.0,y)*0.18;
col+=iColB*glow;
float sed=0.0;
for(int i=0;i<24;i++){float fi=float(i);float e=iDay[i];float yy=0.02+fi*0.006;sed+=e*exp(-pow((y-yy)/0.004,2.0));}
sed*=smoothstep(1.3,0.6,abs(d))*smoothstep(0.25,0.0,y);
col+=mix(iColB,iColC,0.4)*sed*0.4;
fragColor=vec4(clamp(col,0.0,1.0),1.0);}