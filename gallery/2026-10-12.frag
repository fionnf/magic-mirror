// A Rod Keeping Hours - art of the day 2026-10-12
// A single thin rod of warm neon hangs in an autumn dusk, casting a soft fan of light onto the wall below, and along its upper edge it quietly notches every hour of music the house has heard today.
float hash(float n){return fract(sin(n*127.1)*43758.5453);}
float hash2(vec2 p){return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453);}
void mainImage(out vec4 fragColor, in vec2 fragCoord){
  vec2 uv=(fragCoord-0.5*iResolution)/iResolution.y;
  float t=iTime;
  float aspect=iResolution.x/iResolution.y;
  float clk=iClock/24.0;
  float ang=0.22*sin(t*0.013)+0.12*sin(t*0.0071+1.3)+(clk-0.5)*0.5+0.004*sin(6.2832*iBeatPhase);
  vec2 c=vec2(0.07*sin(t*0.009+0.4)+0.03*sin(t*0.0023), 0.16+0.05*sin(t*0.011)+0.04*(clk-0.5));
  float L=min(aspect,1.0)*0.34+0.02*iBreath;
  vec2 dir=vec2(cos(ang),sin(ang));
  vec2 nrm=vec2(-dir.y,dir.x);
  vec2 p=uv-c;
  float along=dot(p,dir);
  float perp=dot(p,nrm);
  float ca=clamp(along,-L,L);
  float d=length(p-dir*ca);
  float core=exp(-d*d/0.000035);
  float halo=exp(-d*(16.0+8.0*iBright))*0.55;
  float below=max(-perp,0.0);
  float skew=(hash(iSong*13.7+1.0)-0.5)*0.35;
  float spread=(0.35+0.25*sin(t*0.005+2.0))*(1.0-0.3*iTension);
  float a2=along+skew*below;
  float edge=L*0.85+spread*below;
  float fan=smoothstep(edge+0.12,edge-0.08,abs(a2));
  float reach=mix(1.6,3.2,0.5+0.5*sin(clk*6.2832-1.5));
  fan*=exp(-below*reach)*smoothstep(0.0,0.03,below);
  fan*=0.85+0.15*sin(a2*3.0+t*0.004);
  float f=(along+L)/(2.0*L)*24.0;
  int idx=int(clamp(floor(f),0.0,23.0));
  float seg=2.0*L/24.0;
  float dx=(fract(f)-0.5)*seg;
  float h=iDay[idx]*step(float(idx),iClock);
  float len=0.006+h*0.07;
  float tick=smoothstep(0.0032,0.0012,abs(dx))*smoothstep(0.003,0.008,perp)*smoothstep(len,len-0.006,perp);
  tick*=step(0.0,f)*step(f,24.0)*step(0.001,h);
  float now=step(float(idx),iClock)*step(iClock,float(idx)+1.0);
  vec3 tint=mix(iColB,iColC,0.45+0.25*cos(iKey));
  float vy=uv.y+0.5;
  vec3 col=iColA*(0.55+0.35*vy);
  col=mix(col,mix(iColA,iColB,0.35),smoothstep(0.9,0.0,length(uv*vec2(0.8,1.0)))*0.3);
  col+=mix(iColB,tint,0.3)*fan*0.6;
  col+=tint*halo*0.55;
  col+=mix(tint,iColC,0.6)*core*0.85;
  col+=tint*tick*(0.35+0.15*now);
  float vig=smoothstep(1.2,0.3,length(uv*vec2(0.9/max(aspect,0.7),1.0)));
  col*=0.6+0.4*vig;
  vec2 cell=fragCoord/iResolution*iPanels;
  vec2 sd=abs(fract(cell)-0.5);
  float seam=smoothstep(0.497,0.5,max(sd.x,sd.y));
  col*=1.0-0.06*seam;
  float g=hash2(fragCoord+floor(t*2.0)*vec2(17.0,31.0))-0.5;
  col+=g*(0.018+0.02*iBright)*(0.5+col);
  col=min(col,vec3(0.95));
  fragColor=vec4(max(col,0.0),1.0);
}