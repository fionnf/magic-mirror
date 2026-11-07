// Ink Swell, One Crest - art of the day 2026-11-07
// A single broad swell rolls through a sea of ink seen from above, its one long crest catching a faint steel light that grows from a thin dawn glint into a wide luminous body by night, with a darker trough behind it giving the water its weight.
float hsh(float n){return fract(sin(n*12.9898)*43758.5453);}
void mainImage(out vec4 fragColor, in vec2 fragCoord){
 float day=clamp((iClock-7.0)/16.0,0.0,1.0);
 vec2 R=iResolution; float s=min(R.x,R.y);
 vec2 p=(fragCoord-0.5*R)/s;
 float t=iTime;
 float seed=hsh(floor(iSong*97.0)+1.0);
 float ang=-0.35+0.25*iEvolve.x+0.15*sin(t*0.013);
 vec2 q=vec2(cos(ang)*p.x-sin(ang)*p.y, sin(ang)*p.x+cos(ang)*p.y);
 float ctr=mix(-0.22,0.18,day)*(R.y/s)+0.04*sin(t*0.011+seed*6.28)+0.03*iEvolve.y;
 float mea=0.05*sin(q.x*(2.2+0.6*iEvolve.z)+t*0.021+seed*6.0)+0.03*sin(q.x*4.1-t*0.017)+0.004*sin(iBeatPhase*6.283);
 float d=q.y-ctr-mea;
 float w=mix(0.035,0.11,day)*(1.0+0.25*iBreath)*(1.0+0.15*iEvolve.w);
 float core=w*mix(0.45,0.3,iTension);
 float glow=exp(-d*d/(2.0*w*w));
 float cr=exp(-d*d/(2.0*core*core));
 float along=0.75+0.25*sin(q.x*1.7+t*0.009+seed*3.0);
 float tr=smoothstep(0.0,w*1.2,-d)*exp(-pow((d+w*2.2)/(w*2.0),2.0));
 float marks=0.0;
 for(int i=0;i<24;i++){float fi=float(i);float e=iDay[i];float y=-w*1.3-fi*0.025;float m=exp(-pow((d-y)/0.01,2.0));marks+=m*e;}
 marks=clamp(marks,0.0,1.0)*smoothstep(-0.05,0.0,-d);
 vec3 ground=mix(iColA,iColB,0.12+0.1*(p.y+0.5));
 ground=max(ground,vec3(0.03,0.07,0.22));
 float k=0.5+0.5*sin(iKey);
 vec3 steel=mix(iColB,iColC,0.55+0.15*k);
 vec3 hi=mix(iColC,iColB,0.12+0.1*(1.0-k));
 float lv=mix(0.75,1.0,day)*along;
 vec3 col=ground;
 col=mix(col,ground*0.72,tr*0.6);
 col=max(col,vec3(0.025,0.06,0.2));
 col+= (steel-ground)*glow*0.75*lv;
 col=mix(col,hi*0.95,cr*0.75*lv);
 col+=iColB*marks*0.12;
 col+=iColC*0.03*iBright*glow;
 col=min(col,vec3(0.75));
 fragColor=vec4(col,1.0);
}