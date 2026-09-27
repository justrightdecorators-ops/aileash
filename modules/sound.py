"""
modules/sound.py  v2.0.0
Background music and button pops across sebbi.pro.

Arm after each deploy:  https://sebbi.pro/x/sound/status
(or everything at once:  https://sebbi.pro/x/arm/status)

What visitors get on every page:
  - Eight original tunes, two styles, rotating on their own:
      late-night guitar (clean plucked guitar with echo and chorus, bass
      guitar and sub, half-time beat) and chilled keys (Rhodes electric
      piano chords, plucked bass, laid-back swung drums, vinyl crackle).
    The guitar and bass are modelled plucked strings (Karplus-Strong), the
    piano is a Rhodes-style FM voice. Each tune has an intro that opens up,
    a drop, a breakdown and an outro, about two and a half minutes long.
    All generated live in the browser: no files to host, no licence to pay.
  - Real tracks: put audio files (mp3, m4a, ogg, wav) in modules/music/ in
    GitHub and the player plays those instead, shuffled. Leave the folder
    out and the built-in music plays.
  - A soft "pop" whenever a button or link is pressed.
  - A small music button under MY EARNINGS: play/pause, next, volume,
    pops on/off. Choices are remembered.
  - Starts on the visitor's first tap (browsers allow nothing before that),
    fades out while any video plays, pauses when the tab is hidden.

Nothing in server.py is edited.
"""

import io
import json
import os
import re
import sys
from urllib.parse import quote, unquote

VERSION = "2.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

HERE = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(HERE, "music")
AUDIO_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg",
               ".oga": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav", ".webm": "audio/webm",
               ".flac": "audio/flac"}

TAG = b'<script src="/sound.js?v=' + VERSION.encode() + b'" defer id="sebbi-sound-js"></script>'
MARK = b'id="sebbi-sound-js"'
SKIP_PREFIX = ("/api", "/x/", "/p/", "/sound", "/admin", "/webhook", "/stripe", "/.well-known", "/static")

JS = r"""
(function(){
if(window.__sebbiSound)return;window.__sebbiSound=1;
var AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;
function lg(k,d){try{var v=localStorage.getItem('sbs_'+k);return v===null?d:JSON.parse(v)}catch(e){return d}}
function ls(k,v){try{localStorage.setItem('sbs_'+k,JSON.stringify(v))}catch(e){}}
function sg(k,d){try{var v=sessionStorage.getItem('sbs_'+k);return v===null?d:JSON.parse(v)}catch(e){return d}}
function ss(k,v){try{sessionStorage.setItem('sbs_'+k,JSON.stringify(v))}catch(e){}}
var st={music:lg('music',true),pops:lg('pops',true),vol:lg('vol',0.7)};
var MIN=[0,3,5,7,10],MAJ=[0,2,4,7,9];
function C(b,v){return {b:b,v:v}}
var TUNES=[
 {name:'Night Shift',kind:'gtr',k:45,bpm:98,sw:.04,cb:2,bars:56,pent:MIN,dens:.5,prog:[C(0,[12,15,19]),C(-4,[8,12,15]),C(3,[10,15,19]),C(-2,[10,14,17])]},
 {name:'Harbour Light',kind:'keys',k:48,bpm:78,sw:.2,cb:1,bars:48,pent:MAJ,dens:.42,prog:[C(2,[5,9,12,16]),C(-5,[5,9,11,16]),C(0,[4,7,11,14]),C(-3,[4,7,11,12])]},
 {name:'Slow Signal',kind:'gtr',k:47,bpm:94,sw:.04,cb:2,bars:54,pent:MIN,dens:.45,prog:[C(0,[12,15,19]),C(-7,[8,12,17]),C(0,[12,15,19]),C(-4,[8,12,15])]},
 {name:'After Hours',kind:'keys',k:48,bpm:74,sw:.22,cb:1,bars:44,pent:MIN,dens:.38,prog:[C(0,[3,7,10,14]),C(5,[8,12,15,19]),C(-4,[7,12,15,20]),C(-5,[5,8,11,14])]},
 {name:'Second Witness',kind:'gtr',k:44,bpm:100,sw:.03,cb:2,bars:58,pent:MIN,dens:.55,prog:[C(0,[12,15,19]),C(-2,[10,14,17]),C(-4,[8,12,15]),C(-2,[10,14,17])]},
 {name:'Quiet Ledger',kind:'keys',k:48,bpm:82,sw:.18,cb:1,bars:48,pent:MAJ,dens:.4,prog:[C(5,[4,7,9,12]),C(4,[2,4,7,11]),C(2,[0,4,5,9]),C(0,[11,14,16,19])]},
 {name:'North Sea',kind:'gtr',k:50,bpm:92,sw:.05,cb:2,bars:52,pent:MIN,dens:.42,prog:[C(0,[12,15,19]),C(-4,[8,12,15]),C(-7,[8,12,17]),C(-5,[7,10,14])]},
 {name:'Low Tide',kind:'keys',k:45,bpm:76,sw:.2,cb:2,bars:44,pent:MIN,dens:.36,prog:[C(0,[3,7,10,14]),C(-7,[9,12,15,19])]}
];

var ctx=null,master,musicBus,popBus,gtrBus,keysBus,padBus,drumBus,lp,lpVal=3600,wobG,dly,started=false,playing=false,timer=null,switching=false;
var cur=null,ti=0,step=0,nextT=0,motif=[],mv=[],duck=1,crackle=null,KS={},BUF={};
var FILES=null,fi=0,audio=null,fileBus=null,mode='gen',curName='';

function mk(len,fn){var sr=ctx.sampleRate,n=Math.floor(sr*len),b=ctx.createBuffer(1,n,sr);fn(b.getChannelData(0),sr,n);return b}
function impulse(sec,pre){var r=ctx.sampleRate,n=Math.floor(r*sec),p=Math.floor(r*pre),b=ctx.createBuffer(2,n,r);for(var c=0;c<2;c++){var d=b.getChannelData(c),l=0;for(var i=p;i<n;i++){l+=((Math.random()*2-1)-l)*.55;d[i]=l*Math.pow(1-(i-p)/(n-p),2.8)}}return b}
function drums(){
 BUF.kick=mk(.5,function(d,sr,n){var ph=0;for(var i=0;i<n;i++){var t=i/sr,f=46+110*Math.exp(-t*30);ph+=6.2832*f/sr;d[i]=Math.tanh(1.7*Math.sin(ph)*Math.exp(-t*7))*.85+(i<sr*.002?(Math.random()*2-1)*.2:0)}});
 BUF.snare=mk(.32,function(d,sr,n){var a=0,p=0,ph=0;for(var i=0;i<n;i++){var t=i/sr;a+=((Math.random()*2-1)-a)*.4;var h=a-p;p=a;ph+=6.2832*182/sr;d[i]=h*Math.exp(-t*15)*1.4+Math.sin(ph)*Math.exp(-t*30)*.4}});
 BUF.clap=mk(.35,function(d,sr,n){var a=0,p=0;for(var i=0;i<n;i++){var t=i/sr;a+=((Math.random()*2-1)-a)*.5;var h=a-p;p=a;var e=Math.exp(-t*14)+(t<.03?Math.exp(-((t*1000)%10)*.5)*.6:0);d[i]=h*e*1.3}});
 BUF.hat=mk(.09,function(d,sr,n){var p=0;for(var i=0;i<n;i++){var r=Math.random()*2-1;d[i]=(r-p)*Math.exp(-i/sr*55)*.45;p=r}});
 BUF.ohat=mk(.4,function(d,sr,n){var p=0;for(var i=0;i<n;i++){var r=Math.random()*2-1;d[i]=(r-p)*Math.exp(-i/sr*9)*.3;p=r}});
 BUF.crackle=mk(6,function(d,sr,n){var l=0;for(var i=0;i<n;i++){l+=((Math.random()*2-1)-l)*.08;d[i]=l*.05;if(Math.random()<.00035){var a=(Math.random()*.6+.2)*(Math.random()<.5?-1:1),m=Math.floor(Math.random()*20+4);for(var j=0;j<m&&i+j<n;j++)d[i+j]+=a*Math.exp(-j/3)}}});
}
function init(){
 if(ctx)return;
 try{ctx=new AC()}catch(e){ctx=null;return}
 var comp=ctx.createDynamicsCompressor();comp.threshold.value=-16;comp.ratio.value=3;comp.attack.value=.01;comp.release.value=.2;comp.connect(ctx.destination);
 master=ctx.createGain();master.gain.value=1;master.connect(comp);
 popBus=ctx.createGain();popBus.gain.value=.3;popBus.connect(master);
 musicBus=ctx.createGain();musicBus.gain.value=0;
 lp=ctx.createBiquadFilter();lp.type='lowpass';lp.frequency.value=lpVal;lp.Q.value=.5;musicBus.connect(lp);
 var sat=ctx.createWaveShaper(),cv=new Float32Array(1024);for(var i=0;i<1024;i++){var x=i/511.5-1;cv[i]=Math.tanh(1.3*x)/Math.tanh(1.3)}sat.curve=cv;lp.connect(sat);
 var dry=ctx.createGain();dry.gain.value=.82;sat.connect(dry);dry.connect(master);
 var verb=ctx.createConvolver();verb.buffer=impulse(3.4,.025);var wet=ctx.createGain();wet.gain.value=.3;sat.connect(verb);verb.connect(wet);wet.connect(master);
 var lfo=ctx.createOscillator();lfo.frequency.value=.33;wobG=ctx.createGain();wobG.gain.value=6;lfo.connect(wobG);lfo.start();
 gtrBus=ctx.createGain();gtrBus.connect(musicBus);
 var ch=ctx.createDelay(.05);ch.delayTime.value=.016;var chl=ctx.createOscillator();chl.frequency.value=.7;var chg=ctx.createGain();chg.gain.value=.0035;chl.connect(chg);chg.connect(ch.delayTime);chl.start();
 var chOut=ctx.createGain();chOut.gain.value=.5;gtrBus.connect(ch);ch.connect(chOut);
 if(ctx.createStereoPanner){var cp=ctx.createStereoPanner();cp.pan.value=.55;chOut.connect(cp);cp.connect(musicBus)}else chOut.connect(musicBus);
 dly=ctx.createDelay(2);var fb=ctx.createGain();fb.gain.value=.33;var dl=ctx.createBiquadFilter();dl.type='lowpass';dl.frequency.value=2000;var dh=ctx.createBiquadFilter();dh.type='highpass';dh.frequency.value=300;
 var dOut=ctx.createGain();dOut.gain.value=.34;gtrBus.connect(dh);dh.connect(dly);dly.connect(dl);dl.connect(fb);fb.connect(dly);dl.connect(dOut);dOut.connect(musicBus);
 keysBus=ctx.createGain();
 if(ctx.createStereoPanner){var kp=ctx.createStereoPanner(),kl=ctx.createOscillator(),kg=ctx.createGain();kl.frequency.value=3.2;kg.gain.value=.32;kl.connect(kg);kg.connect(kp.pan);kl.start();keysBus.connect(kp);kp.connect(musicBus)}else keysBus.connect(musicBus);
 var kd=ctx.createGain();kd.gain.value=.22;keysBus.connect(kd);kd.connect(dly);
 padBus=ctx.createGain();var pl=ctx.createBiquadFilter();pl.type='lowpass';pl.frequency.value=800;padBus.connect(pl);pl.connect(musicBus);
 drumBus=ctx.createGain();drumBus.gain.value=.9;drumBus.connect(musicBus);
 drums();
 document.addEventListener('visibilitychange',function(){if(!ctx)return;if(document.hidden){save();if(audio&&!audio.paused)audio.pause();if(ctx.state==='running')ctx.suspend()}else if(started){ctx.resume();if(mode==='file'&&playing&&audio)audio.play().catch(function(){})}});
}
function hz(m){return 440*Math.pow(2,(m-69)/12)}
function wob(p){try{wobG.connect(p)}catch(e){}}
function unwob(p){return function(){try{wobG.disconnect(p)}catch(e){}}}
function level(){return playing?(.85*st.vol*duck):0}
function setLevel(sec){if(!ctx)return;var t=ctx.currentTime,g=mode==='file'&&fileBus?fileBus.gain:musicBus.gain,o=mode==='file'?musicBus.gain:(fileBus?fileBus.gain:null),lv=mode==='file'?.5*st.vol*duck*(playing?1:0):level();
 g.cancelScheduledValues(t);g.setValueAtTime(g.value,t);g.linearRampToValueAtTime(lv,t+(sec||.6));if(o){o.cancelScheduledValues(t);o.setValueAtTime(o.value,t);o.linearRampToValueAtTime(0,t+.5)}}

function ksGet(m,br){
 var key=m+':'+br;if(KS[key])return KS[key];
 var sr=ctx.sampleRate,P=sr/hz(m),N=Math.max(2,Math.floor(P-.5)),rate=(N+.5)/P,len=Math.floor(sr*(m<48?2.4:3.4)),b=ctx.createBuffer(1,len,sr),d=b.getChannelData(0),w=new Float32Array(N),l=0,i;
 for(i=0;i<N;i++){l+=((Math.random()*2-1)-l)*br;w[i]=l}
 var pp=Math.max(1,Math.floor(N*.13)),w2=new Float32Array(N);for(i=0;i<N;i++)w2[i]=w[i]-(i>=pp?w[i-pp]:0);w=w2;
 var rho=m<48?.9955:.9975,idx=0,pk=0;
 for(i=0;i<len;i++){var j=idx+1;if(j===N)j=0;var v=w[idx];d[i]=v;w[idx]=rho*.5*(v+w[j]);idx=j;v=v<0?-v:v;if(v>pk)pk=v}
 var sc=pk>0?.7/pk:1,ft=Math.floor(sr*.25);for(i=0;i<len;i++)d[i]*=sc;for(i=0;i<ft;i++)d[len-1-i]*=i/ft;
 return KS[key]={b:b,r:rate};
}
function pluck(m,t,vel,br,dest,pan){
 var o=ksGet(m,br),s=ctx.createBufferSource(),g=ctx.createGain();s.buffer=o.b;s.playbackRate.value=o.r;g.gain.value=vel;
 if(s.detune){wob(s.detune);s.onended=unwob(s.detune)}
 s.connect(g);if(pan&&ctx.createStereoPanner){var p=ctx.createStereoPanner();p.pan.value=pan;g.connect(p);p.connect(dest)}else g.connect(dest);
 s.start(t);
}
function rhodes(m,t,amp,dur){
 var f=hz(m),c=ctx.createOscillator(),md=ctx.createOscillator(),mg=ctx.createGain(),tn=ctx.createOscillator(),tg=ctx.createGain(),g=ctx.createGain(),end=t+Math.max(1.5,dur);
 c.frequency.value=f;md.frequency.value=f;tn.frequency.value=f*14.02;
 mg.gain.setValueAtTime(f*1.5,t);mg.gain.exponentialRampToValueAtTime(f*.16,t+1);
 tg.gain.setValueAtTime(f*.8,t);tg.gain.exponentialRampToValueAtTime(.01,t+.07);
 md.connect(mg);mg.connect(c.frequency);tn.connect(tg);tg.connect(c.frequency);
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(amp,t+.006);g.gain.exponentialRampToValueAtTime(amp*.4,t+1.3);g.gain.exponentialRampToValueAtTime(amp*.22,end);g.gain.exponentialRampToValueAtTime(.0001,end+.45);
 c.connect(g);g.connect(keysBus);wob(c.detune);c.onended=unwob(c.detune);
 c.start(t);md.start(t);tn.start(t);c.stop(end+.5);md.stop(end+.5);tn.stop(t+.1);
}
function pad(ms,t,dur){for(var i=0;i<ms.length;i++){for(var j=0;j<2;j++){var o=ctx.createOscillator(),g=ctx.createGain();o.type=j?'sine':'triangle';o.frequency.value=hz(ms[i]);o.detune.value=j?6:-6;g.gain.setValueAtTime(.0001,t);g.gain.linearRampToValueAtTime(.018,t+1.5);g.gain.setValueAtTime(.018,t+Math.max(1.6,dur-1));g.gain.linearRampToValueAtTime(.0001,t+dur+.7);o.connect(g);g.connect(padBus);o.start(t);o.stop(t+dur+.9)}}}
function sub(m,t,dur){var o=ctx.createOscillator(),g=ctx.createGain();o.frequency.value=hz(m);g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.12,t+.03);g.gain.setTargetAtTime(.07,t+.1,.4);g.gain.setTargetAtTime(.0001,t+Math.max(.2,dur-.2),.1);o.connect(g);g.connect(musicBus);o.start(t);o.stop(t+dur+.5)}
function hit(n,t,v,rate){var s=ctx.createBufferSource(),g=ctx.createGain();s.buffer=BUF[n];if(rate)s.playbackRate.value=rate;g.gain.value=v;s.connect(g);g.connect(drumBus);s.start(t)}
function kick(t,v){hit('kick',t,.62*v);[padBus,keysBus].forEach(function(n){n.gain.cancelScheduledValues(t);n.gain.setValueAtTime(.5,t);n.gain.setTargetAtTime(1,t+.02,.12)})}
function sweep(t,from,to,dur){lp.frequency.cancelScheduledValues(t);lp.frequency.setValueAtTime(from||lpVal,t);lp.frequency.exponentialRampToValueAtTime(to,t+dur);lpVal=to}

function mkMotif(dens,rest){var m=[],last=4;for(var i=0;i<32;i++){var on=i%2===0?(i===0||Math.random()<dens):Math.random()<dens*.15;if(rest&&i>=26)on=false;if(on){var c=last+[-2,-1,-1,0,1,1,2][Math.floor(Math.random()*7)];if(c<2)c=3;if(c>9)c=8;last=c;m.push(c)}else m.push(null)}return m}
function vary(m){var v=m.slice();for(var i=1;i<v.length;i++){if(Math.random()<.1)v[i]=v[i]===null?(i%2?null:Math.max(2,Math.min(9,(v[i-2]||4)+1))):null}return v}
function noteOf(n){return cur.k+12+cur.pent[n%5]+12*Math.floor(n/5)}
function e16(){return 60/cur.bpm/4}

function schedule(s,t){
 var B=cur.bars,b=Math.floor(s/16),k=s%16,bd=e16()*16,cb=cur.cb,ci=Math.floor(b/cb)%cur.prog.length,ch=cur.prog[ci],nx=cur.prog[(ci+1)%cur.prog.length],first=(b%cb===0)&&k===0;
 var mid=Math.floor(B/2),brk=b>=mid-2&&b<mid+2,out=b>=B-4,gtr=cur.kind==='gtr';
 var dr=b>=(gtr?8:4)&&!brk&&!out,bs=b>=(gtr?4:2)&&b<B-2;
 if(k===0){if(b===0)sweep(t,600,3600,bd*4);if(b===mid-2)sweep(t,0,1200,bd);if(b===mid+2)sweep(t,0,3600,bd*.75);if(b===B-4)sweep(t,0,420,bd*4)}
 if(k===0&&b%8===0&&b>0)mv=vary(motif);
 var mm=(Math.floor(b/8)%2)?mv:motif,n=mm[(b%2)*16+k];
 if(gtr){
  if(n!==null)pluck(noteOf(n),t,(k%4===0?.3:.22)*(b<2?.8:1),.5,gtrBus,k%8<4?-.3:.3);
  if(b>=12&&!brk&&k===0&&b%2===1&&Math.random()<.5)pluck(cur.k+12+ch.v[1],t,.13,.7,gtrBus,.45);
  if(first)pad(ch.v.map(function(x){return cur.k+x}),t,bd*cb);
  if(bs){if(first){pluck(cur.k-12+ch.b,t,.42,.22,musicBus);sub(cur.k-12+ch.b,t,bd*cb*.9)}else if(k===10&&Math.random()<.3)pluck(cur.k+ch.b,t,.22,.25,musicBus)}
  if(dr){if(k===0)kick(t,1);if(k===10&&Math.random()<.35)kick(t,.55);if(k===8)hit('clap',t,.3);if(k%2===0)hit('hat',t,k%4===0?.16:.1);else if(Math.random()<.1)hit('hat',t,.06);if(k===14&&Math.random()<.18)hit('ohat',t,.1)}
 }else{
  if(first||(k===0&&cb>1&&Math.random()<.4)){for(var i=0;i<ch.v.length;i++)rhodes(cur.k+ch.v[i],t+i*.014,(first?.075:.05),bd*(first?cb:1))}
  else if(k===7&&Math.random()<.28){for(var i2=0;i2<ch.v.length;i2++)rhodes(cur.k+ch.v[i2],t+i2*.01,.04,.5)}
  var ph=(b>=8&&b<mid-2)||(b>=mid+2&&b<B-4);
  if(ph&&b%4<2&&n!==null)pluck(noteOf(n)+12,t,(k%4===0?.2:.15),.6,gtrBus,k%8<4?-.25:.25);
  if(bs){var r=cur.k-12+ch.b;if(first||(cb>1&&k===0))pluck(r,t,.5,.2,musicBus);else if(k===6&&Math.random()<.4)pluck(r+12,t,.26,.25,musicBus);else if(k===10&&Math.random()<.6)pluck(r+7,t,.34,.22,musicBus);else if(k===14&&Math.random()<.3&&(b%cb===cb-1))pluck(cur.k-12+nx.b-1,t,.28,.22,musicBus)}
  if(dr){if(k===0)kick(t,1);if(k===10)kick(t,.8);if(k===7&&Math.random()<.25)kick(t,.45);if(k===4||k===12)hit('snare',t,.34);if(k%2===0)hit('hat',t,k%4===0?.15:.09);else if(Math.random()<.15)hit('hat',t,.05);if(k===14&&Math.random()<.15)hit('ohat',t,.09)}
 }
}
function tick(){
 if(!ctx||!playing||switching||mode!=='gen')return;
 var e=e16();
 while(nextT<ctx.currentTime+.3){schedule(step,nextT);nextT+=e*(step%2?(1-cur.sw):(1+cur.sw));step++;if(step>=cur.bars*16){nextTune(1);return}}
}
function startCrackle(){stopCrackle();if(cur.kind!=='keys')return;crackle=ctx.createBufferSource();crackle.buffer=BUF.crackle;crackle.loop=true;var g=ctx.createGain();g.gain.value=.55;crackle.connect(g);g.connect(musicBus);crackle.start()}
function stopCrackle(){if(crackle){try{crackle.stop()}catch(e){}crackle=null}}
function loadTune(i){
 ti=((i%TUNES.length)+TUNES.length)%TUNES.length;cur=TUNES[ti];curName=cur.name;step=0;
 motif=mkMotif(cur.dens,cur.kind==='keys');mv=vary(motif);
 dly.delayTime.setValueAtTime(60/cur.bpm*.75,ctx.currentTime);
 nextT=ctx.currentTime+.1;startCrackle();ss('ti',ti);ui();
}
function nextTune(dir){
 if(switching)return;switching=true;var t=ctx.currentTime;
 musicBus.gain.cancelScheduledValues(t);musicBus.gain.setValueAtTime(musicBus.gain.value,t);musicBus.gain.linearRampToValueAtTime(0,t+1.8);
 setTimeout(function(){stopCrackle();switching=false;loadTune(ti+(dir||1));setLevel(1.5)},1900);
}
function playFile(i){
 fi=((i%FILES.length)+FILES.length)%FILES.length;
 if(!audio){audio=new Audio();audio.preload='auto';var src=ctx.createMediaElementSource(audio);fileBus=ctx.createGain();fileBus.gain.value=0;src.connect(fileBus);fileBus.connect(master);
  audio.addEventListener('ended',function(){playFile(fi+1)});audio.addEventListener('error',function(){setTimeout(function(){if(FILES.length>1)playFile(fi+1)},800)})}
 var resume=sg('fpos',null);audio.src=FILES[fi].url;
 if(resume&&resume.i===fi){audio.addEventListener('loadedmetadata',function h(){audio.removeEventListener('loadedmetadata',h);try{audio.currentTime=resume.t}catch(e){}})}
 ss('fpos',null);curName=FILES[fi].name;ss('fi',fi);var p=audio.play();if(p&&p.catch)p.catch(function(){});ui();
}
function play(){
 init();if(!ctx)return;ctx.resume();playing=true;
 if(mode==='file'){if(!audio||!audio.src)playFile(sg('fi',0));else{audio.play().catch(function(){})}setLevel(1.5);ui();return}
 if(!cur)loadTune(sg('ti',Math.floor(Math.random()*TUNES.length)));
 nextT=Math.max(nextT,ctx.currentTime+.1);if(!timer)timer=setInterval(tick,50);setLevel(2);ui();
}
function pause(){playing=false;setLevel(.7);if(mode==='file'&&audio){setTimeout(function(){if(!playing)audio.pause()},800)}ui()}
function next(){if(!playing){play();return}if(mode==='file'){var t=ctx.currentTime;fileBus.gain.setValueAtTime(fileBus.gain.value,t);fileBus.gain.linearRampToValueAtTime(0,t+.6);setTimeout(function(){playFile(fi+1);setLevel(1)},650)}else nextTune(1)}
function save(){if(mode==='file'&&audio&&!isNaN(audio.currentTime))ss('fpos',{i:fi,t:audio.currentTime});else if(cur)ss('ti',ti)}
window.addEventListener('pagehide',save);
try{fetch('/sound/tracks').then(function(r){return r.json()}).then(function(j){if(j&&j.tracks&&j.tracks.length){FILES=j.tracks;if(!playing)mode='file';ui()}}).catch(function(){})}catch(e){}

function pop(){
 if(!ctx||ctx.state!=='running')return;
 var t=ctx.currentTime,o=ctx.createOscillator(),g=ctx.createGain(),f=480+Math.random()*320;
 o.frequency.setValueAtTime(f*2,t);o.frequency.exponentialRampToValueAtTime(f*.55,t+.07);
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.55,t+.004);g.gain.exponentialRampToValueAtTime(.0001,t+.11);
 o.connect(g);g.connect(popBus);o.start(t);o.stop(t+.13);
}
function mediaPlaying(){var m=document.querySelectorAll('video,audio');for(var i=0;i<m.length;i++){if(!m[i].paused&&!m[i].ended&&!m[i].muted&&m[i].volume>0)return true}return false}
function recheck(){var d=mediaPlaying()?0:1;if(d!==duck){duck=d;setLevel(1.2)}}
['play','playing','pause','ended','volumechange'].forEach(function(ev){document.addEventListener(ev,function(){setTimeout(recheck,50)},true)});
function unlock(){
 init();if(!ctx)return;var p=ctx.resume();
 if(!started){started=true;hint();if(st.music)play()}
 if(p&&p.then)p.then(function(){if(ctx.state==='running')['pointerdown','touchend','click','keydown'].forEach(function(ev){document.removeEventListener(ev,unlock,true)})});
}
['pointerdown','touchend','click','keydown'].forEach(function(ev){document.addEventListener(ev,unlock,true)});
var SEL='a,button,[role=button],summary,label,input[type=submit],input[type=button],input[type=checkbox],input[type=radio],select,[onclick]';
document.addEventListener('pointerdown',function(e){if(!st.pops)return;var el=e.target&&e.target.closest?e.target.closest(SEL):null;if(!el)return;init();if(ctx&&ctx.state!=='running')ctx.resume();pop()},true);

var css='#sebbi-snd{position:fixed;right:12px;top:calc(104px + env(safe-area-inset-top,0px));z-index:2147483000;width:36px;height:36px;border-radius:50%;'+
'background:rgba(10,15,30,.9);border:1.5px solid #8fd0ff;box-shadow:0 0 16px rgba(143,208,255,.35);display:flex;align-items:flex-end;justify-content:center;gap:3px;padding:0 0 10px;box-sizing:border-box;cursor:pointer;-webkit-tap-highlight-color:transparent}'+
'#sebbi-snd i{display:block;width:3px;background:#8fd0ff;border-radius:2px;height:5px;transition:height .3s}'+
'#sebbi-snd.on i{animation:sbsnd 1.1s ease-in-out infinite}#sebbi-snd.on i:nth-child(2){animation-delay:-.4s}#sebbi-snd.on i:nth-child(3){animation-delay:-.75s}'+
'#sebbi-snd.off{border-color:rgba(255,255,255,.3);box-shadow:none}#sebbi-snd.off i{background:rgba(255,255,255,.45);height:3px}'+
'@keyframes sbsnd{0%,100%{height:4px}50%{height:15px}}'+
'#sebbi-sndhint{position:fixed;right:54px;top:calc(111px + env(safe-area-inset-top,0px));z-index:2147483000;font:600 10.5px/1 "IBM Plex Mono",monospace;color:#8fd0ff;background:rgba(10,15,30,.85);padding:6px 9px;border-radius:999px;transition:opacity .6s;pointer-events:none}'+
'#sebbi-sndp{position:fixed;right:12px;top:calc(148px + env(safe-area-inset-top,0px));z-index:2147483001;width:232px;background:rgba(10,15,30,.96);color:#fff;border:1px solid rgba(143,208,255,.45);border-radius:14px;padding:12px 14px;box-shadow:0 10px 30px rgba(0,0,0,.45);font:500 12px/1.4 "IBM Plex Mono",monospace;display:none;box-sizing:border-box}'+
'#sebbi-sndp .l{font-size:9.5px;letter-spacing:.14em;color:#8fd0ff;opacity:.8}#sebbi-sndp .n{font-size:14px;font-weight:700;margin:3px 0 10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'+
'#sebbi-sndp .r{display:flex;gap:8px;align-items:center;margin-bottom:10px}'+
'#sebbi-sndp button{flex:1;background:transparent;color:#fff;border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:7px 0;font:600 12px "IBM Plex Mono",monospace;cursor:pointer}'+
'#sebbi-sndp input[type=range]{flex:1;accent-color:#8fd0ff}#sebbi-sndp label{display:flex;gap:8px;align-items:center;cursor:pointer;font-size:11.5px}#sebbi-sndp input[type=checkbox]{accent-color:#8fd0ff}'+
'#sebbi-sndp .f{margin-top:9px;font-size:9.5px;opacity:.55}';
var btn,panel,hintEl,nameEl,ppBtn,foot;
function build(){
 var s=document.createElement('style');s.textContent=css;document.head.appendChild(s);
 btn=document.createElement('div');btn.id='sebbi-snd';btn.setAttribute('role','button');btn.setAttribute('aria-label','Music');btn.innerHTML='<i></i><i></i><i></i>';
 panel=document.createElement('div');panel.id='sebbi-sndp';
 panel.innerHTML='<div class="l">NOW PLAYING</div><div class="n" id="sebbi-sndn">&nbsp;</div>'+
 '<div class="r"><button type="button" id="sebbi-sndpp">Play</button><button type="button" id="sebbi-sndnx">Next &#9654;&#9654;</button></div>'+
 '<div class="r"><span>&#128264;</span><input type="range" min="0" max="100" id="sebbi-sndv"><span>&#128266;</span></div>'+
 '<label><input type="checkbox" id="sebbi-sndpo"> Button pops</label><div class="f" id="sebbi-sndf">Original music by sebbi.pro</div>';
 document.body.appendChild(btn);document.body.appendChild(panel);
 nameEl=panel.querySelector('#sebbi-sndn');ppBtn=panel.querySelector('#sebbi-sndpp');foot=panel.querySelector('#sebbi-sndf');
 var v=panel.querySelector('#sebbi-sndv'),po=panel.querySelector('#sebbi-sndpo');v.value=Math.round(st.vol*100);po.checked=!!st.pops;
 btn.addEventListener('click',function(e){e.stopPropagation();panel.style.display=panel.style.display==='block'?'none':'block'});
 ppBtn.addEventListener('click',function(){if(playing){pause();st.music=false}else{play();st.music=true}ls('music',st.music)});
 panel.querySelector('#sebbi-sndnx').addEventListener('click',function(){st.music=true;ls('music',true);next()});
 v.addEventListener('input',function(){st.vol=v.value/100;ls('vol',st.vol);setLevel(.2)});
 po.addEventListener('change',function(){st.pops=po.checked;ls('pops',st.pops)});
 document.addEventListener('click',function(e){if(panel.style.display==='block'&&!panel.contains(e.target)&&!btn.contains(e.target))panel.style.display='none'});
 if(st.music){hintEl=document.createElement('div');hintEl.id='sebbi-sndhint';hintEl.textContent='♪ tap anywhere for music';document.body.appendChild(hintEl);setTimeout(hint,5000)}
 ui();
}
function hint(){if(hintEl){hintEl.style.opacity='0';var h=hintEl;hintEl=null;setTimeout(function(){h.remove()},700)}}
function ui(){if(!btn)return;btn.className=playing?'on':'off';ppBtn.textContent=playing?'Pause':'Play';
 nameEl.textContent=curName||(mode==='file'&&FILES?FILES[sg('fi',0)%FILES.length].name:(TUNES[sg('ti',0)]||TUNES[0]).name);
 foot.textContent=mode==='file'?'sebbi.pro radio':'Original music by sebbi.pro'}
if(document.body)build();else document.addEventListener('DOMContentLoaded',build);
})();
""".strip().encode("utf-8")

_patched = False
_wrapper = [None]
_rewraps = [0]


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _tracks():
    try:
        names = sorted(os.listdir(MUSIC_DIR))
    except Exception:
        return []
    out = []
    for f in names:
        ext = os.path.splitext(f)[1].lower()
        if f.startswith(".") or ext not in AUDIO_TYPES:
            continue
        title = re.sub(r"[_\-]+", " ", os.path.splitext(f)[0]).strip()
        title = re.sub(r"^\d+\s+", "", title) or f
        out.append({"name": title[:60], "url": "/sound/track/" + quote(f)})
    return out


def _is_page(path):
    if path.startswith(SKIP_PREFIX):
        return False
    last = path.rsplit("/", 1)[-1]
    return "." not in last or last.endswith((".html", ".htm"))


def _inject(raw):
    """Return modified response bytes, or None to send the original."""
    head, sep, body = raw.partition(b"\r\n\r\n")
    if not sep:
        return None
    lines = head.split(b"\r\n")
    if not lines or b" 200" not in lines[0]:
        return None
    lower = head.lower()
    if b"text/html" not in lower or b"content-encoding" in lower or b"chunked" in lower:
        return None
    if MARK in body:
        return None
    at = body.rfind(b"</body>")
    if at < 0:
        at = body.rfind(b"</BODY>")
    if at < 0:
        return None
    new_body = body[:at] + TAG + body[at:]
    out = []
    for ln in lines:
        if ln.lower().startswith(b"content-length:"):
            ln = b"Content-Length: " + str(len(new_body)).encode()
        out.append(ln)
    return b"\r\n".join(out) + b"\r\n\r\n" + new_body


def _send(h, status, ctype, body, cache="no-store"):
    h.send_response(status)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", cache)
    h.end_headers()
    h.wfile.write(body)


def _send_track(h, name):
    name = unquote(name)
    ext = os.path.splitext(name)[1].lower()
    path = os.path.join(MUSIC_DIR, name)
    if ("/" in name or "\\" in name or name.startswith(".") or ext not in AUDIO_TYPES
            or not os.path.isfile(path)):
        return _send(h, 404, "application/json", b'{"error":"not found"}')
    size = os.path.getsize(path)
    start, end, status = 0, size - 1, 200
    m = re.match(r"bytes=(\d*)-(\d*)$", (h.headers.get("Range") or "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        else:
            start = max(0, size - int(m.group(2)))
        end = min(end, size - 1)
        if start > end:
            h.send_response(416)
            h.send_header("Content-Range", "bytes */%d" % size)
            h.send_header("Content-Length", "0")
            h.end_headers()
            return
        status = 206
    h.send_response(status)
    h.send_header("Content-Type", AUDIO_TYPES[ext])
    h.send_header("Content-Length", str(end - start + 1))
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Cache-Control", "public, max-age=86400")
    if status == 206:
        h.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    h.end_headers()
    try:
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                h.wfile.write(chunk)
                left -= len(chunk)
    except (BrokenPipeError, ConnectionResetError):
        pass


def _wrap(cls):
    original_do_GET = cls.do_GET

    def do_GET(self):
        # Stay the outermost page hook even if another module is armed after
        # this one, so every page gets the music whatever order things are armed in.
        c = type(self)
        if c.do_GET is not _wrapper[0] and _rewraps[0] < 20:
            _rewraps[0] += 1
            _wrap(c)
        path = self.path.split("?")[0]
        if path == "/sound.js":
            return _send(self, 200, "application/javascript; charset=utf-8", JS, "public, max-age=86400")
        if path == "/sound/tracks":
            return _send(self, 200, "application/json", json.dumps({"tracks": _tracks()}).encode("utf-8"))
        if path.startswith("/sound/track/"):
            return _send_track(self, path[len("/sound/track/"):])
        if not _is_page(path):
            return original_do_GET(self)
        real = self.wfile
        buf = io.BytesIO()
        self.wfile = buf
        try:
            original_do_GET(self)
            if getattr(self, "_headers_buffer", None):
                self.flush_headers()
        finally:
            self.wfile = real
        raw = buf.getvalue()
        try:
            changed = _inject(raw)
        except Exception:
            changed = None
        real.write(changed if changed is not None else raw)

    cls.do_GET = do_GET
    _wrapper[0] = do_GET


def _install(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_sound_patched", False):
        _patched = True
        return True
    _wrap(cls)
    cls._sound_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    tracks = _tracks()
    return ({"module": "sound", "version": VERSION, "armed": armed,
             "playing": ("your %d tracks from modules/music/" % len(tracks)) if tracks
                        else "built-in music: 8 original tunes (late-night guitar and chilled keys)",
             "tracks": [t["name"] for t in tracks],
             "adds": "Music on every page, a pop on every button press, and a small music button under MY EARNINGS "
                     "with play/pause, next, volume and pops on/off",
             "starts": "on the visitor's first tap (browsers do not allow sound before that)",
             "fades_for_video": True}, 200)
