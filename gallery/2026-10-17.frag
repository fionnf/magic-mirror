// Ultraviolet Hour Ring - art of the day 2026-10-17
// A single thin ultraviolet line slowly draws itself around an empty centre over the day, rising at dawn as a low sliver, opening into a breathing arc by evening, and closing at midnight into a quiet lilac ring wrapped in a faint halo of soft light.
float hash(float n){return fract(sin(n*12.9898)*43758.5453);}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
  float PI=3.14159265;
  vec2 uv=(fragCoord-0.5*iResolution)/min(iResolution.x,iResolution.y);
  float t=iTime;
  float h=iClock;
  float p=smoothstep(5.0,23.0,h);
  float span=mix(0.7,5.9,p);
  if(h<5.0){span=mix(5.9,0.7,smoothstep(2.0,5.0,h));}
  float late=clamp(smoothstep(21.0,23.5,h)+(1.0-smoothstep(1.5,5.0,h)),0.0,1.0);
  float eve=smoothstep(17.0,19.5,h)*(1.0-smoothstep(21.0,22.8,h));
  span+=0.25*iTension+0.15*sin(t*0.009);
  span=min(span,6.1);
  float R=0.29+0.035*sin(t*0.013)+0.03*p+0.01*sin(t*0.0031);
  vec2 c=vec2(0.03*sin(t*0.007),0.025*cos(t*0.011))+0.015*vec2(cos(iKey),sin(iKey));
  float a0=-1.5708+h*0.22+0.3*sin(t*0.004)+0.06*(hash(iSong)-0.5)+0.012*sin(iBeatPhase*6.2832);
  vec2 q=uv-c;
  float r=length(q);
  float ang=atan(q.y,q.x)-a0;
  ang=mod(ang+PI,2.0*PI)-PI;
  float hs=span*0.5;
  float ca=clamp(ang,-hs,hs);
  vec2 P=R*vec2(cos(ca+a0),sin(ca+a0));
  float d=length(q-P);
  float w=mix(0.0055,0.0035,iBright)*mix(1.0,0.75,late);
  float core=exp(-d*d/(w*w));
  float near=0.010/(d+0.010);
  near*=near;
  float inside=mix(0.3,1.0,smoothstep(R+0.06,R-0.08,r));
  float fall=0.09+0.05*iBreath+0.02*eve;
  float fan=exp(-d/fall)*inside;
  float wide=exp(-d*d/0.09)*0.25;
  float fanAmt=0.65*(1.0+eve*(0.35+0.45*iBreath));
  fanAmt*=mix(1.0,0.3,late);
  float halo=exp(-pow((r-R)/0.1,2.0))*late*0.22;
  float k=0.08*sin(iKey);
  vec3 lineCol=mix(iColB,iColC,0.65+k);
  vec3 fanCol=mix(iColB,iColC,0.12+0.45*late+k);
  vec3 haloCol=mix(iColB,iColC,0.7);
  vec3 ground=iColA*0.7+iColB*0.04*(1.0-smoothstep(0.0,0.9,length(uv)));
  vec3 col=ground;
  col+=fanCol*(fan+wide)*fanAmt;
  col+=haloCol*halo;
  col+=lineCol*near*0.9;
  col+=mix(iColC,vec3(1.0),0.15)*core*0.9;
  float beads=0.0;
  for(int i=0;i<24;i++){
    float fi=float(i);
    float ba=1.5708-fi/24.0*2.0*PI;
    vec2 bp=(R+0.06)*vec2(cos(ba),sin(ba));
    float bd=length(q-bp);
    beads+=iDay[i]*exp(-bd*bd/0.00004);
  }
  col+=mix(iColB,iColC,0.5)*beads*0.45;
  col=1.0-exp(-col*1.15);
  fragColor=vec4(col,1.0);
}
