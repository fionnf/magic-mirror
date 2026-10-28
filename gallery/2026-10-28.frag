// Lantern Under Still Water - art of the day 2026-10-28
// A single veil of aqua light hangs in deep petrol water like sun that has sunk a long way down, widening and rising through the day while a faint shadow-twin drifts beside it.
float hsh(float n){return fract(sin(n*127.1)*43758.5453);}
void mainImage(out vec4 fragColor, in vec2 fragCoord){
 float day=clamp((iClock-7.0)/16.0,0.0,1.0);
 vec2 uv=fragCoord/iResolution;
 float asp=iResolution.x/iResolution.y;
 float x=(uv.x-0.5)*asp; float y=uv.y;
 float t=iTime;
 float cx=0.12*sin(t*0.013+1.0)+0.05*iEvolve.x+mix(-0.12,0.10,day)*asp*0.5+0.03*sin(iBeatPhase*6.2831)*0.3;
 float sway=0.035*sin(y*3.0+t*0.031+iEvolve.y)+0.02*sin(y*7.0-t*0.047)+0.015*(iSong-0.5);
 float w=mix(0.045,0.11,day)*(1.0+0.15*iBreath)*(1.0+0.1*iEvolve.z)*asp;
 float dx=x-cx-sway;
 float core=exp(-dx*dx/(w*w));
 float fold=1.0+0.18*(1.0+iTension)*sin(dx/w*3.0+t*0.02)*core;
 float cy=mix(0.42,0.62,day)+0.04*iBreath;
 float hgt=mix(0.22,0.34,day);
 float vy=exp(-pow((y-cy)/hgt,2.0)*1.6);
 float veil=core*fold*vy;
 float sx=cx+mix(0.22,0.16,day)*asp*0.5*(iSong>0.5?1.0:-1.0)+0.04*iEvolve.w;
 float d2=x-sx-sway*0.7;
 float shadow=0.28*exp(-d2*d2/(w*w*0.5))*exp(-pow((y-cy+0.06)/(hgt*0.8),2.0)*1.6);
 float haze=0.06*iBright*exp(-dx*dx/(w*w*6.0));
 float sed=0.0;
 for(int i=0;i<24;i++){float fi=float(i);float hx=(fi+0.5)/24.0;float e=iDay[i];sed+=e*exp(-pow((uv.x-hx)*24.0,2.0)*0.5);}
 sed*=smoothstep(0.12,0.0,y)*0.18;
 float k=0.5+0.5*sin(iKey);
 vec3 ground=mix(iColA,iColB,0.18+0.12*(1.0-y))+vec3(0.0,0.02,0.025);
 ground=max(ground,vec3(0.02,0.16,0.18)*0.0+ground);
 vec3 aqua=mix(iColB,iColC,mix(0.55,0.8,day)+0.08*(k-0.5));
 float a=clamp(veil*0.85+shadow+haze,0.0,0.92);
 vec3 col=mix(ground,aqua,a);
 col+=sed*(iColB-iColA);
 float mx=max(col.r,max(col.g,col.b));
 if(mx<0.19) col*=0.19/max(mx,0.001);
 fragColor=vec4(col,1.0);
}