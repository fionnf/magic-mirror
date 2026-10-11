// Tree Rings for a Sunday - art of the day 2026-10-11
// The day grows outward like the cross-section of a tree, one ring for every hour from a glowing heartwood at midnight, so by night the wall holds a log sawn through the whole Sunday.
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p);vec2 f=fract(p);f=f*f*(3.0-2.0*f);
return mix(mix(hash(i),hash(i+vec2(1.0,0.0)),f.x),mix(hash(i+vec2(0.0,1.0)),hash(i+vec2(1.0,1.0)),f.x),f.y);}
float fbm(vec2 p){float s=0.0;float a=0.5;for(int i=0;i<4;i++){s+=a*noise(p);p=p*2.03+vec2(1.7,9.2);a*=0.5;}return s;}
float dayAt(int k){float e=0.0;for(int i=0;i<24;i++){if(i==k){e=iDay[i];}}return e;}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float m=min(iResolution.x,iResolution.y);
vec2 p=(fragCoord-0.5*iResolution.xy)/m;
float px=1.0/m;
float t=iTime;
float seed=iSong*17.0;
// the heartwood wanders a little over hours
vec2 c=vec2(0.05*sin(t*0.0071+1.3)+0.03*sin(iClock*0.26),0.04*sin(t*0.0053)-0.03*cos(iClock*0.21));
vec2 q=p-c;
float r=length(q*vec2(0.93+0.04*sin(t*0.004),1.0));   // a log is never quite round
// grain of the wood: a slow warp, re-seeded by each song; rising tension draws it a little straighter
vec2 w=q*2.1+vec2(t*0.011,-t*0.008)+seed;
float warp=fbm(w)-0.5;
float sp=0.0300;
float rr=r+0.075*(1.0-0.12*iTension)*warp*(0.25+r);
// the mid tone leans with the music's key
vec3 mid=mix(iColB,mix(iColB,iColC,0.35),0.5+0.5*cos(iKey*6.2831));
// ground: deep shadow with the faintest warmth toward the core
vec3 col=iColA*(0.55+0.35*exp(-r*r*6.0));
// rings: one for every hour, the heartwood is midnight. Like a tree's, a ring is as wide as its
// hour was rich: loud hours lay down wide rings, quiet hours tight ones; hours still to come wait as ghosts
float now=iClock;
float inner=0.045;
float line=0.0;
float glowIn=0.0;
float ghost=0.0;
float a=fract(atan(q.x,q.y)/6.2831+1.0);
for(int i=0;i<24;i++){
  float fi=float(i);
  float e=iDay[i];
  float past=step(fi+1.0,now);
  float cur=step(fi,now)*(1.0-past);
  float wdt=mix(0.016,0.008+0.028*e,max(past,cur));
  float outer=inner+wdt;
  float d=abs(rr-outer);
  float l=1.0-smoothstep(0.35*px,1.4*px+0.6*px*e,d);
  float vis=past+cur*smoothstep(a-0.004,a+0.004,fract(now));
  float s=vis*(0.18+0.6*smoothstep(0.0,0.8,e));
  line=max(line,l*s);
  ghost=max(ghost,l*0.05*(1.0-past));
  // earlywood: a faint warm fill inside the rich rings
  glowIn+=vis*step(inner,rr)*step(rr,outer)*smoothstep(0.35,1.0,e)*smoothstep(outer,inner,rr);
  inner=outer;
}
vec3 ink=mix(mid,iColC*0.8,smoothstep(0.55,1.0,line));
col+=mid*0.09*glowIn;
col=mix(col,ink,max(line,ghost)*(1.0-0.35*smoothstep(0.35,0.75,r)));
// heartwood glow: warmer in the evening, breathing slowly with the bass
float day=0.5+0.5*sin((iClock-9.0)/24.0*6.2831);
float core=exp(-r*r/(0.0025+0.0012*iBreath));
col=mix(col,mix(mid,iColC,0.6)*(0.55+0.25*day),core*0.85);
// a little static grain; airier music makes it finer and brighter
float g=hash(floor(fragCoord)+floor(t*0.03)*13.0);
col+=iColC*0.025*step(0.992-0.01*iBright,g);
vec2 v=fragCoord/iResolution.xy-0.5;
col*=1.0-0.6*dot(v,v);
fragColor=vec4(clamp(col,0.0,0.85),1.0);
}
