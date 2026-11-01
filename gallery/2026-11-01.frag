// Cold Corona, Sunday - art of the day 2026-11-01
// A dark rounded body sits in a deep blue night while a cold halo of glacier light spills round its whole edge, widening and paling slowly through the day until by midnight the dark form floats inside a broad field of ice glow.
float hash(float n){return fract(sin(n)*43758.5453);}
void mainImage(out vec4 fragColor, in vec2 fragCoord){
 float day = clamp((iClock - 7.0) / 16.0, 0.0, 1.0);
 vec2 uv=(fragCoord-0.5*iResolution)/min(iResolution.x,iResolution.y);
 float t=iTime;
 float mem=0.0;
 for(int i=0;i<24;i++){mem+=iDay[i];}
 mem=clamp(mem/12.0,0.0,1.0);
 vec2 c=vec2(0.03*iEvolve.x+0.02*sin(t*0.013+iSong*6.0), mix(0.10,-0.06,day)+0.02*iEvolve.y);
 c.x+=0.004*sin(iBeatPhase*6.2832);
 vec2 p=uv-c;
 p.y*=1.0+0.06*iEvolve.z;
 float ang=atan(p.y,p.x);
 float r=length(p);
 float R=mix(0.17,0.22,day)*(1.0+0.02*sin(t*0.021)+0.03*iEvolve.w);
 R*=1.0+0.03*sin(ang*2.0+t*0.017+iSong*3.0)*0.5;
 float d=r-R;
 float w=mix(0.035,0.16,day)*(1.0+0.15*iBreath+0.1*mem)*(1.0-0.15*iTension);
 float halo=exp(-max(d,0.0)/w);
 float rim=exp(-abs(d)/(0.012+0.004*iBright));
 float var=1.0+0.12*sin(ang*3.0+t*0.011+iSong)+0.08*sin(ang*5.0-t*0.019);
 halo*=var;
 float body=smoothstep(0.004,-0.006,d);
 vec3 ground=mix(iColA*0.9,iColA*1.6+iColB*0.08,smoothstep(0.9,0.0,length(uv-vec2(0.0,-0.2))));
 float k=0.5+0.5*sin(iKey);
 vec3 haloCol=mix(iColB,mix(iColB,iColC,0.5+0.2*k),mix(0.25,0.75,day));
 vec3 rimCol=mix(iColC,iColB,0.15+0.1*(1.0-k));
 vec3 col=ground;
 col=mix(col,haloCol,clamp(halo*(0.85+0.1*iBreath),0.0,1.0)*(1.0-body));
 col+=rimCol*rim*0.85*(1.0-0.5*body);
 float haze=iBright*0.08*exp(-max(d,0.0)/(w*2.5));
 col+=iColC*haze*(1.0-body);
 vec3 inner=mix(iColA*0.7,iColB*0.18,smoothstep(-R,0.0,d));
 col=mix(col,inner+rimCol*rim*0.5,body*0.92);
 col=min(col,vec3(0.94));
 fragColor=vec4(col,1.0);
}