// October Sediment, Low Sun - art of the day 2026-10-09
// A low autumn sun hangs over the Zürich lake fog while the day's music settles beneath it as twenty-four thin strata of earth, one for every hour, so by midnight the ground has become a core sample of everything the house listened to.
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p);vec2 f=fract(p);f=f*f*(3.0-2.0*f);float a=hash(i);float b=hash(i+vec2(1.0,0.0));float c=hash(i+vec2(0.0,1.0));float d=hash(i+vec2(1.0,1.0));return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
vec2 uv=fragCoord/iResolution.xy;
float t=iTime;
vec3 colB=mix(iColB,mix(iColB,iColC,0.4),0.5+0.5*cos(iKey));
colB=mix(colB,iColA,0.15*(0.5+0.5*sin(iKey)));
vec3 col=mix(iColA*1.05,iColA*0.45,smoothstep(0.36,1.0,uv.y));
vec2 c=vec2(0.66+0.003*sin(iBeatPhase*6.2831),0.6+0.04*sin(t*0.012));
float r=0.075+0.012*iBreath;
float d=length(uv-c);
float disc=smoothstep(r,r-0.006,d);
float glow=exp(-d*d*28.0);
col=mix(col,mix(col,colB,0.5),glow*0.55);
col=mix(col,mix(colB,iColC,0.55)*0.85,disc);
float seed=iSong*37.0;
float base=0.04;
float top=0.36;
float w=0.007*sin(uv.x*5.0+seed)+0.006*(noise(vec2(uv.x*9.0+seed,seed))-0.5)+0.003*sin(uv.x*13.0+t*0.02);
float yy=uv.y+w*smoothstep(base,top,uv.y+0.02);
if(yy<top){
float f=(yy-base)/(top-base)*24.0;
float fi=floor(f);
float e=0.0;
for(int k=0;k<24;k++){if(k==int(fi)){e=iDay[k];}}
float fr=fract(f);
float grain=noise(vec2(uv.x*60.0,f*3.0+seed))*0.12;
vec3 lay=mix(iColA*0.7,colB*0.9,clamp(0.12+0.75*e+grain,0.0,1.0));
lay=mix(lay,mix(lay,iColC*0.7,0.35),smoothstep(0.6,1.0,e));
float line=smoothstep(0.0,0.08,fr)*smoothstep(1.0,0.9,fr);
lay*=0.7+0.3*line;
if(yy<base){lay=iColA*0.5;}
lay*=0.75+0.25*smoothstep(base,top,yy);
col=lay;
}
float fw=0.05-0.025*iTension;
float fy=(uv.y-top-0.01)/fw;
float fog=exp(-fy*fy);
float fn=noise(vec2(uv.x*4.0-t*0.02,uv.y*12.0+t*0.01));
float sparkle=step(0.985-0.02*iBright,hash(floor(fragCoord*0.5)+floor(t*0.05)))*0.25;
fog*=0.55+0.45*fn;
fog*=1.0-0.35*iBright+sparkle*iBright;
col=mix(col,mix(colB,iColC,0.25)*0.75,fog*0.45);
vec2 v=uv-0.5;
col*=1.0-0.45*dot(v,v);
col=clamp(col,0.0,0.9);
fragColor=vec4(col,1.0);
}