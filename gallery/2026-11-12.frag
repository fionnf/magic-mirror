// Prism Line Descending - art of the day 2026-11-12
// A single thread of pale light falls through the dark and, where it touches ground, opens into a soft narrow spectrum that widens and climbs as the day goes on, until by night the fan is a broad luminous veil.
vec3 spec(float t){vec3 a=mix(iColA*1.6,iColB,smoothstep(0.0,0.5,t));return mix(a,iColC,smoothstep(0.5,1.0,t));}
void mainImage(out vec4 fragColor,in vec2 fragCoord){
float day=clamp((iClock-7.0)/16.0,0.0,1.0);
vec2 uv=fragCoord/iResolution.xy;float asp=iResolution.x/iResolution.y;
vec2 p=vec2((uv.x-0.5)*asp,uv.y);
float cx=0.08*sin(iSong*6.28)+0.05*iEvolve.x+0.03*sin(iTime*0.013)+0.004*sin(iBeatPhase*6.28);
cx*=mix(1.0,0.4,day);
float split=mix(0.62,0.30,day)+0.04*iEvolve.y;
float x=p.x-cx;
float below=clamp((split-p.y)/split,0.0,1.0);
float spread=mix(0.06,0.45,day)*(1.0+0.15*iBreath+0.1*iEvolve.z)*(1.0-0.2*iTension);
float w=0.012+spread*pow(below,1.2);
float xn=x/w;
float body=exp(-xn*xn*1.6);
float line=exp(-pow(x/0.011,2.0))*step(split,p.y)*smoothstep(1.02,0.85,p.y);
float core=exp(-pow(x/(0.011+0.02*below),2.0));
float t=clamp(0.5+xn*0.45+0.08*sin(iKey),0.0,1.0);
vec3 sc=spec(t);
vec3 col=iColA*0.6*(1.0-uv.y*0.3);
col+=mix(iColB,iColC,0.5)*0.25*exp(-length(vec2(x,p.y-split)*vec2(1.0,1.6))*3.0)*(1.0+day);
float fanAmt=step(p.y,split)*body*mix(0.75,1.0,day);
col+=sc*fanAmt*mix(1.0,1.3,day)*(0.85+0.15*iBright);
col+=mix(iColC,vec3(1.0),0.3)*core*step(p.y,split)*(1.0-below)*0.7;
col+=mix(iColC,vec3(0.95),0.25)*line*0.95;
float sed=0.0;for(int i=0;i<24;i++){float fx=(float(i)/23.0-0.5)*asp*0.9;sed+=iDay[i]*exp(-pow((p.x-fx)/0.03,2.0));}
col+=iColB*0.5*sed*exp(-p.y/0.04);
col+=iColC*0.04*iBright*body;
fragColor=vec4(clamp(col,0.0,1.0),1.0);}