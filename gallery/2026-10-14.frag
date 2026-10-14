// Interference in Cobalt - art of the day 2026-10-14
// A field of Riley-like cobalt and cream stripes that wakes straight and quiet, then through the day lets a slow set of concentric rings drift in across it, until by night the two systems lean, widen and cross into a full, breathing moire.
float tri(float p){return abs(fract(p)-0.5)*2.0;}
void mainImage(out vec4 fragColor, in vec2 fragCoord){
 vec2 R=iResolution;
 vec2 uv=(fragCoord-0.5*R)/R.y;
 float t=iTime;
 float c=iClock;
 float k=smoothstep(7.0,17.0,c);
 float night=clamp(smoothstep(21.0,24.0,c)+1.0-smoothstep(0.0,5.0,c),0.0,1.0);
 float ang=0.42*smoothstep(6.0,23.0,c)+0.06*sin(t*0.0013);
 float ca=cos(ang); float sa=sin(ang);
 vec2 q=vec2(ca*uv.x-sa*uv.y, sa*uv.x+ca*uv.y);
 float f1=mix(15.0,10.0,night);
 float warp=(0.045+0.012*iBreath)*sin(q.y*3.1+t*0.011)+0.022*sin(q.y*6.3-t*0.007+1.3)+0.03*sin(q.y*1.7+t*0.0041+c*0.2);
 float p1=(q.x+warp)*f1;
 vec2 c2=vec2(0.36*sin(t*0.0021+c*0.26),0.30*cos(t*0.0016+c*0.19));
 c2.y+=0.08*(R.y/R.x-1.0)*sin(c*0.3);
 vec2 d=uv-c2;
 d.x*=1.0+0.012*(fract(iSong*7.31)-0.5);
 float f2=f1*1.045-0.25*iTension;
 float p2=length(d)*f2-t*0.004;
 float hy=clamp(fragCoord.y/R.y,0.0,0.9999)*23.0;
 int i0=int(floor(hy));
 int i1=min(i0+1,23);
 float e=mix(iDay[i0],iDay[i1],smoothstep(0.0,1.0,fract(hy)));
 float duty=0.44+0.24*clamp(e,0.0,1.0);
 float aa=0.10-0.03*iBright+0.6*f1/R.y;
 float s1=smoothstep(duty-aa,duty+aa,tri(p1));
 float s2=smoothstep(0.5-aa,0.5+aa,tri(p2));
 float x=s1*s2+(1.0-s1)*(1.0-s2);
 float s=mix(s1,x,k);
 vec3 cream=mix(iColC,iColB,0.08+0.06*sin(iKey));
 vec3 ground=mix(iColB,iColA,0.12+0.1*night);
 vec3 col=mix(ground,cream*0.9,s);
 float vig=smoothstep(0.35,1.0,length(uv*vec2(R.y/R.x,1.0))*1.3);
 col=mix(col,iColA,0.3*vig);
 fragColor=vec4(col,1.0);
}