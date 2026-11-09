// Ink Tide, Long Crest - art of the day 2026-11-09
// A single broad swell of deep water seen from above, its one long crest catching a faint steel light that slowly rises through the night-blue field as the day fills with music.
float hash(float n){return fract(sin(n*127.1)*43758.5453);}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float day=clamp((iClock-7.0)/16.0,0.0,1.0);
vec2 uv=fragCoord/iResolution.xy;
float asp=iResolution.x/iResolution.y;
vec2 p=vec2((uv.x-0.5)*asp,uv.y);
float t=iTime;
float ph=hash(iSong*7.3)*6.283;
float amp=0.06+0.04*iEvolve.x;
float cy=mix(0.30,0.62,day)+0.02*iEvolve.y;
float wave=amp*sin(p.x*(2.2+0.4*iEvolve.z)+t*0.03+ph)+0.03*sin(p.x*4.1-t*0.017+iEvolve.w);
float d=p.y-(cy+wave);
float w=mix(0.05,0.13,day)*(1.0+0.15*iBreath)*(1.0-0.25*iTension);
float crest=exp(-d*d/(w*w));
float core=exp(-d*d/(w*w*0.12));
float below=smoothstep(0.0,-0.5,d);
vec3 ground=mix(iColA,iColB,0.18*below);
ground=max(ground,vec3(0.02,0.07,0.19));
float marks=0.0;
for(int i=0;i<24;i++){float fi=float(i);float e=iDay[i];float y=0.04+fi*0.012*(cy/0.3);float dm=p.y-(y+wave*0.4);marks+=e*exp(-dm*dm/0.00008);}
marks=clamp(marks,0.0,1.0)*step(p.y,cy+wave-0.03);
float k=0.5+0.5*sin(iKey);
vec3 formCol=mix(iColB,iColC,mix(0.25,0.6,day)+0.1*k);
vec3 col=ground;
col=mix(col,formCol*0.75,crest*0.8);
col=mix(col,formCol,core*mix(0.55,0.85,day));
col+=iColC*0.04*iBright*crest*(0.5+0.5*sin(p.x*9.0+t*0.05));
col=mix(col,iColB,marks*0.35);
col=min(col,vec3(0.72));
fragColor=vec4(col,1.0);
}