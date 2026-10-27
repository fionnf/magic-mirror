// Ultraviolet Threshold - art of the day 2026-10-27
// A single open arc of ultraviolet neon hangs in the dark and slowly lengthens through the day, its soft lilac fan spilling evenly onto the night around it while the gap stays open.
void mainImage(out vec4 fragColor, in vec2 fragCoord){
 float day=clamp((iClock-7.0)/16.0,0.0,1.0);
 vec2 res=iResolution;
 float s=min(res.x,res.y);
 vec2 uv=(fragCoord-0.5*res)/s;
 float t=iTime;
 vec2 c=vec2(0.03*sin(t*0.013),mix(-0.12,0.08,day)+0.02*sin(t*0.007+1.3));
 float R=mix(0.16,0.34,day)+0.01*sin(t*0.021);
 float half_=mix(0.9,2.3,day)+0.12*iTension;
 float rot=1.5708+0.25*sin(t*0.009)+0.1*sin(iClock*0.4);
 vec2 p=uv-c;
 float a=atan(p.y,p.x)-rot;
 a=mod(a+3.14159,6.28318)-3.14159;
 float r=length(p);
 float ca=clamp(a,-half_,half_);
 vec2 q=c+R*vec2(cos(ca+rot),sin(ca+rot));
 float d=length(uv-q);
 float w=0.007+0.002*(1.0-iBright);
 float core=exp(-pow(d/w,2.0));
 float hist=0.0;
 for(int i=0;i<24;i++){hist+=iDay[i];}
 hist/=24.0;
 float spread=0.07+0.03*iBreath+0.03*hist+0.03*day;
 float fan=exp(-d/spread);
 float inner=smoothstep(R+0.02,R*0.3,r);
 fan*=mix(1.0,1.25,inner);
 float halo=exp(-d/(spread*2.6))*0.35;
 float k=0.5+0.5*sin(iKey);
 vec3 vio=mix(iColB,mix(iColB,iColC,0.3),0.4*k);
 vec3 col=iColA;
 col=mix(col,vio*0.8,clamp(halo,0.0,1.0)*0.7);
 col=mix(col,vio,clamp(fan*0.55,0.0,1.0));
 vec3 hot=mix(iColC,vio,0.25+0.2*(1.0-day));
 col=mix(col,hot,clamp(core*1.1,0.0,1.0));
 col+=iColC*0.25*exp(-pow(d/(w*0.5),2.0));
 fragColor=vec4(clamp(col,0.0,1.0),1.0);
}