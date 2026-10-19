// Shoal of Small Lights - art of the day 2026-10-19
// A sphere that exists only as a shoal of fine teal points, crowding into a bright rim where the surface turns away from us; it wakes sparse and low, fills out and rises by noon, drifts across in the evening, and thins to a lone glowing ring at night, while each hour of the day's music is laid down as one brightened latitude band on its turning skin.
float h21(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
vec2 rot(vec2 p,float a){float c=cos(a),s=sin(a);return vec2(c*p.x-s*p.y,s*p.x+c*p.y);}
vec3 toObj(vec3 v,float tilt,float yaw){v.yz=rot(v.yz,-tilt);v.xz=rot(v.xz,-yaw);return v;}
vec3 toView(vec3 v,float tilt,float yaw){v.xz=rot(v.xz,yaw);v.yz=rot(v.yz,tilt);return v;}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
vec2 res=iResolution;float m=min(res.x,res.y);
vec2 uv=(fragCoord-0.5*res)/m;
float t=iTime;float c=iClock;
const float PI=3.14159265;
float day=smoothstep(5.0,12.0,c)*(1.0-smoothstep(17.0,24.0,c));
float eve=smoothstep(15.0,21.0,c);
float night=max(smoothstep(20.0,24.0,c),1.0-smoothstep(3.0,7.0,c));
vec2 center=vec2(mix(-0.12,0.10,smoothstep(6.0,22.0,c)),mix(-0.10,0.06,smoothstep(5.0,13.0,c))-0.08*smoothstep(19.0,24.0,c));
center+=0.03*vec2(sin(t*0.013),cos(t*0.009+1.0))+vec2(0.004*sin(iBeatPhase*6.2832),0.0);
float R=(0.20+0.12*day+0.03*eve*(1.0-night))*(1.0+0.04*iBreath)+0.01*sin(t*0.021);
vec2 q=(uv-center)/R;float r=length(q);
float yaw=t*0.02+c*0.3;
float tilt=0.35+0.15*sin(t*0.007)+0.1*sin(iKey);
float base=0.22+0.5*day;
float sz=mix(0.9,0.65,iBright);
float lean=0.15*sin(iKey);
vec3 col=iColA*(0.75+0.35*(1.0-clamp(length(uv),0.0,1.0)));
float w=mix(6.0,10.0,iTension);
col+=iColB*0.22*(1.0+0.4*iTension)*exp(-pow((r-1.0)*w,2.0));
col+=iColB*0.05*smoothstep(1.0,0.0,r);
col+=iColB*0.05*exp(-max(r-1.0,0.0)*3.0)*step(1.0,r);
if(r<1.04){
vec2 qs=r>0.999?q/r*0.999:q;float rs=length(qs);
const float NL=32.0;const float NLON=64.0;
for(int hs=0;hs<2;hs++){
float s=hs==0?1.0:-1.0;
float hw=hs==0?1.0:mix(0.3,0.55,eve);
vec3 p=vec3(qs,s*sqrt(max(1.0-rs*rs,0.0)));
vec3 o=toObj(p,tilt,yaw);
float lat=asin(clamp(o.y,-1.0,1.0));float lon=atan(o.z,o.x);
float row=floor((lat+PI*0.5)/PI*NL);
for(int dr=-1;dr<=1;dr++){
float rr=row+float(dr);
if(rr<0.0||rr>=NL)continue;
float latc=(rr+0.5)/NL*PI-PI*0.5;
float nl=max(1.0,floor(NLON*cos(latc)));
float ci=floor((lon+PI)/(2.0*PI)*nl);
int band=int(clamp((latc+PI*0.5)/PI*24.0,0.0,23.0));
float dayE=iDay[band];
for(int dc=-1;dc<=1;dc++){
float cc=mod(ci+float(dc),nl);
vec2 id=vec2(rr,cc)+iSong*17.3;
float h=h21(id);float h2=h21(id+3.1);float h3=h21(id+7.7);
float la=latc+(h2-0.5)*0.6/NL*PI;
float lo=(cc+0.5+(h3-0.5)*0.6)/nl*2.0*PI-PI;
vec3 po=vec3(cos(la)*cos(lo),sin(la),cos(la)*sin(lo));
vec3 v=toView(po,tilt,yaw);
if(v.z*s<0.0)continue;
float pr=length(v.xy);
float prob=(base+0.45*dayE)*mix(1.0,smoothstep(0.5,0.95,pr),night);
if(h>prob)continue;
vec2 pos=center+R*v.xy;
float d=length(uv-pos)*m;
float I=exp(-d*d/(sz*sz));
float limb=pow(pr,3.0);
float k=clamp(0.35+0.55*limb+lean+0.25*dayE,0.0,1.0);
vec3 dcol=mix(iColB,iColC,k);
col+=dcol*I*hw*(0.55+0.65*limb)*(0.8+0.4*dayE);
}}}
}
col=col/(1.0+col*0.25);
fragColor=vec4(clamp(col,0.0,1.0),1.0);
}