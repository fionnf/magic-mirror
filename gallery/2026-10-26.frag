// Lantern in Frosted Lime - art of the day 2026-10-26
// A single lime light lives behind frosted glass in a dark petrol room: a tight low seed at morning, a broad pale lantern by afternoon, a lobed shape the evening music pulls into new outlines, and at night a wide, flattened ember with one small bright heart.
float hash(float n){return fract(sin(n)*43758.5453);}

void mainImage(out vec4 fragColor, in vec2 fragCoord){
  vec2 uv=fragCoord/iResolution;
  float m=min(iResolution.x,iResolution.y);
  vec2 p=(fragCoord-0.5*iResolution)/m;
  float h=mod(iClock,24.0);
  float t=iTime;
  vec4 A=vec4(0.075,0.075,-0.24,0.05); vec2 Ae=vec2(0.35,0.45);
  vec4 B=vec4(0.25,0.26,0.0,0.08);   vec2 Be=vec2(1.0,0.85);
  vec4 C=vec4(0.19,0.30,0.02,0.28);  vec2 Ce=vec2(0.6,0.55);
  vec4 D=vec4(0.32,0.11,-0.08,0.06); vec2 De=vec2(0.12,0.22);
  vec4 k; vec2 e;
  if(h<9.0){float w=smoothstep(2.0,8.5,h); k=mix(D,A,w); e=mix(De,Ae,w);}
  else{
    float w=smoothstep(9.0,15.0,h); k=mix(A,B,w); e=mix(Ae,Be,w);
    w=smoothstep(15.0,20.0,h); k=mix(k,C,w); e=mix(e,Ce,w);
    w=smoothstep(20.0,23.0,h); k=mix(k,D,w); e=mix(e,De,w);
  }
  float ev=smoothstep(16.0,19.5,h)*(1.0-smoothstep(21.0,23.0,h));
  float mus=clamp(iBreath*0.6+iTension*0.7,0.0,1.0);
  float lobe=k.w*(0.7+0.6*mus)+ev*0.28*mus+0.03*iBreath;
  float rx=k.x*(1.0+0.06*iBreath+0.05*sin(t*0.017));
  float ry=k.y*(1.0+0.04*iBreath+ev*0.4*iTension+0.05*sin(t*0.012+2.0));
  float dayE=0.0; float cnt=0.0;
  for(int i=0;i<24;i++){ if(float(i)<h){dayE+=iDay[i]; cnt+=1.0;} }
  dayE=cnt>0.0?dayE/cnt:0.0;
  vec2 c=vec2(0.03*sin(t*0.013)+0.02*sin(t*0.0071+1.0), k.z+0.015*sin(t*0.011+0.5));
  c.x+=0.004*sin(6.2831*iBeatPhase);
  vec2 q=p-c;
  float ro=0.15*sin(t*0.009)+0.05*sin(iKey);
  q=mat2(cos(ro),-sin(ro),sin(ro),cos(ro))*q;
  float ang=atan(q.y,q.x);
  float s=iSong*6.2831;
  float r=1.0+lobe*(0.55*sin(2.0*ang+t*0.021+s)+0.3*sin(3.0*ang-t*0.015+iKey+s*1.7)+0.15*sin(5.0*ang+t*0.033+s*2.3));
  float d=length(q/vec2(rx,ry))/max(r,0.3);
  float soft=1.7-0.5*iBright;
  float body=exp(-d*d*soft);
  float hs=1.0+1.4*dayE;
  float halo=exp(-d/(1.1*hs))*0.9;
  float vig=length((uv-0.5)*vec2(1.0,1.0))*1.45;
  vec3 ground=mix(iColA*1.35,iColA*0.55,smoothstep(0.0,1.0,vig));
  ground+=iColB*0.05*dayE*smoothstep(0.35,0.0,uv.y);
  vec3 col=ground;
  col=mix(col,iColB*0.75,clamp(halo*0.35,0.0,1.0));
  col=mix(col,iColB,clamp(body*1.1,0.0,1.0));
  vec3 lime=mix(iColB,iColC,0.3+0.12*sin(iKey));
  col=mix(col,lime,smoothstep(0.3,1.0,body)*0.45);
  col=mix(col,mix(iColB,iColC,0.65),smoothstep(0.15,0.75,body)*e.x*0.55);
  float core=smoothstep(1.0-0.7*e.y,1.0,body);
  col=mix(col,iColC,core*(0.55+0.35*e.x));
  col=min(col,vec3(0.95));
  fragColor=vec4(col,1.0);
}