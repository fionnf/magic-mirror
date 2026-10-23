// Violet Glass, Breathing Low - art of the day 2026-10-23
// A single soft lump of violet glass drifts through a dark indigo room, catching a cold white rim light that circles it like a slow sun, while the faint glow it casts beneath it gathers, hour by hour, into a quiet record of the day's music.
float hash(float n){return fract(sin(n)*43758.5453);}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
  vec2 uv=(fragCoord-0.5*iResolution)/iResolution.y;
  float t=iTime;
  float hc=iClock;
  float dayArc=sin(3.14159*clamp((hc-6.0)/16.0,0.0,1.0));
  float night=clamp(smoothstep(20.0,23.5,hc)+(1.0-smoothstep(4.0,7.5,hc)),0.0,1.0);
  float sd=hash(iSong*17.31+0.37);
  vec2 cen;
  cen.x=mix(-0.13,0.13,smoothstep(7.0,22.0,hc))+0.03*sin(t*0.013+1.1)+0.02*sin(t*0.0071+sd*6.283);
  cen.y=-0.17+0.22*dayArc-0.05*night+0.015*sin(t*0.009+2.3)+0.003*sin(6.2832*iBeatPhase);
  float r=0.15+0.06*dayArc+0.03*night+0.015*iBreath+0.008*sin(t*0.017);
  vec2 p=uv-cen;
  p.y*=1.0+0.22*night;
  float a=atan(p.y,p.x);
  float amp=0.6+0.8*night+0.9*iTension;
  float lump=amp*(0.03*sin(3.0*a+t*0.02+sd*6.283)+0.022*sin(5.0*a-t*0.031+1.7+sd*3.0)+0.02*sin(2.0*a+t*0.011+4.0));
  float R=r*(1.0+lump);
  float d=length(p)-R;
  vec2 q=p/R;
  float qq=min(dot(q,q),1.0);
  vec3 N=normalize(vec3(q,sqrt(max(1.0-qq,0.0))+0.001));
  float la=mix(2.5,0.6,clamp((hc-5.0)/19.0,0.0,1.0))+0.15*sin(t*0.004);
  vec3 L=normalize(vec3(cos(la),sin(la),0.55));
  float keyT=0.5+0.5*cos(iKey);
  vec3 midT=mix(iColB,mix(iColB,iColC,0.28),keyT*0.6);
  // ground
  float gy=uv.y;
  vec3 bg=mix(iColA*1.25+iColB*0.06,iColA*0.7,smoothstep(-0.5,0.5,gy));
  // halo
  float hw=10.0-4.0*iBright;
  float halo=exp(-max(d,0.0)*hw);
  vec3 col=bg+midT*halo*0.28;
  // glow pool below
  float fy=cen.y-r*(1.0-0.1*night)-0.05;
  float dy=uv.y-fy;
  float vert=exp(-dy*dy*(dy>0.0?260.0:70.0));
  float base=exp(-pow((uv.x-cen.x)/(R*1.1),2.0));
  float sed=0.0;
  for(int i=0;i<24;i++){
    float hx=cen.x+(float(i)/23.0-0.5)*0.8;
    float dx=uv.x-hx;
    sed+=exp(-dx*dx*900.0)*iDay[i];
  }
  float pool=vert*(0.55*base+0.6*sed);
  col+=mix(midT,iColC,0.25)*pool*0.55;
  // glass body
  float nz=N.z;
  float fres=pow(1.0-nz,2.5);
  float dif=max(dot(N,L),0.0);
  vec3 glass=mix(iColA*1.4,midT,0.35+0.5*fres);
  float caust=exp(-dot(q+L.xy*0.55,q+L.xy*0.55)*3.5);
  glass+=midT*caust*0.55;
  glass+=mix(midT,iColC,0.4)*caust*caust*0.25;
  glass*=0.75+0.35*dif;
  vec2 qn=normalize(q+0.0001);
  float rim=pow(max(dot(qn,normalize(L.xy)),0.0),3.0)*pow(smoothstep(0.55,1.0,sqrt(qq)),3.0);
  glass+=iColC*0.8*rim;
  glass+=iColB*0.35*fres;
  vec3 H=normalize(L+vec3(0.0,0.0,1.0));
  float spec=pow(max(dot(N,H),0.0),60.0);
  glass+=iColC*0.7*spec;
  float m=smoothstep(0.006,-0.006,d);
  col=mix(col,glass,m);
  // thin outer edge light
  float edge=exp(-abs(d)*160.0)*(0.3+0.7*max(dot(qn,normalize(L.xy)),0.0));
  col+=iColC*edge*0.35;
  col=1.0-exp(-col*1.25);
  col=min(col,vec3(0.92));
  fragColor=vec4(col,1.0);
}
