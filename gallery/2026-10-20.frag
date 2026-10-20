// Jade Lantern, Tide Kept - art of the day 2026-10-20
// A single emerald glass orb rises from the floor of a dark room at dawn, hangs high and full at noon, drifts east and widens its halo through the evening, then sinks to rest above a pool of its own light at night, while soft, barely-banded shells of jade quietly record each hour of music the house played.
float sat(float x){return clamp(x,0.0,1.0);}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float m=min(iResolution.x,iResolution.y);
vec2 uv=(fragCoord-0.5*iResolution)/m;
float yl=0.5*iResolution.y/m;
float h=iClock;
float t=iTime;
float sun=sin(3.14159*(h-6.0)/15.0);
float up=sat(sun);
float eve=smoothstep(15.0,22.0,h);
float night=sat(smoothstep(20.0,24.0,h)+1.0-smoothstep(3.0,7.0,h));
vec2 c;
c.x=mix(-0.14,0.14,smoothstep(5.0,23.0,h))+0.035*sin(t*0.011+iSong*6.2832)+0.02*sin(t*0.0043+2.0)+0.003*sin(6.2832*iBeatPhase);
c.y=yl*mix(-0.40,0.22,up)+0.02*sin(t*0.0067+1.0)-0.05*night*yl;
float R=mix(0.065,0.14,up)*(1.0+0.05*iBreath)*(1.0-0.2*night)+0.008*iTension;
vec2 p=uv-c;
float d=length(p);
vec3 A=iColA;
vec3 B=iColB;
vec3 C=iColC;
float lean=0.5+0.5*cos(iKey);
vec3 hi=mix(C,mix(B,C,0.65),0.3*lean);
float vy=sat(0.5+0.5*uv.y/yl);
vec3 col=A*mix(0.75,1.05,vy);
float hw=R*mix(0.9,2.4,eve)*(1.0+0.3*iBright);
float dd=max(d-R,0.0);
float halo=exp(-dd/hw);
float halo2=exp(-dd/(hw*3.5));
col+=B*(0.55*halo+0.22*halo2)*mix(0.8,1.1,up);
float gy=-yl*0.72;
float close=exp(-max(c.y-R-gy,0.0)/0.25);
vec2 q=vec2((uv.x-c.x)/(R*4.5),(uv.y-gy)/(R*0.7));
float pool=exp(-dot(q,q));
col+=mix(A,B,0.7)*pool*close*mix(0.35,0.8,night);
float mem=0.0;
for(int i=0;i<24;i++){
float fi=float(i);
float rr=R*1.15+0.01+0.012*fi*(1.0+eve*0.5);
float w=step(fi,h);
float k=(d-rr)/0.011;
mem+=iDay[i]*w*exp(-k*k);
}
col+=mix(B,hi,0.35)*mem*0.35*halo2;
float inside=1.0-smoothstep(R-1.5/m,R+1.5/m,d);
vec2 n2=p/max(R,0.001);
float z=sqrt(sat(1.0-dot(n2,n2)));
vec3 nrm=vec3(n2,z);
float la=2.3+iSong*0.9+0.2*sin(t*0.009);
vec3 L=normalize(vec3(cos(la),sin(la),0.9));
float dif=sat(dot(nrm,L));
float glow=pow(z,1.5);
vec3 body=mix(B*0.9,hi,0.3+0.5*glow*mix(0.6,1.0,up))*(0.7+0.4*dif);
float rim=pow(1.0-z,4.0)*sat(dot(n2,-L.xy)*0.5+0.6);
body+=hi*rim*0.5;
float spec=pow(sat(dot(reflect(-L,nrm),vec3(0.0,0.0,1.0))),24.0);
body+=hi*spec*0.3;
body*=mix(1.0,0.78,night);
col=mix(col,body,inside);
col=col/(1.0+0.15*col);
fragColor=vec4(clamp(col,0.0,1.0),1.0);
}