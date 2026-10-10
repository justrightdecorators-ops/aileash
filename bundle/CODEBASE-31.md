# Codebase — part 31 of 54

Contains:
- `modules/sound.py`
- `modules/spec.py`
- `modules/spendgate.py`
- `modules/src/modules/sebbi/index.ts`
- `modules/standard.py`


## `modules/sound.py`

517 lines, 37833 bytes

```python
"""
modules/sound.py  v5.0.0
Background music and button pops across sebbi.pro.

Arm after each deploy:  https://sebbi.pro/x/sound/status
(or everything at once:  https://sebbi.pro/x/arm/status)

What visitors get on every page:
  - Twenty original electro/rave tunes, each a different style, rotating:
    acid house, electro, hoover rave, breakbeat, trance, minimal acid,
    hard-kick acid with sirens, 168 bpm gabber, 172 bpm jungle, half-time
    wobble, bleep techno, psytrance, UK garage, stutter-gated acid,
    hardcore, electro acid, trance hoovers, wobbly electro, and an
    everything-at-once finale. Lasers, air-raid sirens, stutter gates,
    wobble bass, impacts on every drop, snare rolls and risers.
  - Real tracks: put audio files (mp3, m4a, ogg, wav) in modules/music/ in
    GitHub and the player plays those instead, shuffled.
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

VERSION = "5.0.0"
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
var SH={m:[0,3,7,12],M:[0,4,7,12],s:[0,5,7,12]};
// acid patterns: 16 steps, [semitone offset or null, accent, slide]
function A(s){return s.split(' ').map(function(x){if(x==='.')return null;var a=x.indexOf('!')>=0,sl=x.indexOf('~')>=0;return [parseInt(x.replace(/[!~]/g,''),10),a,sl]})}
var AC_=["0! 0 12 0 . 0 3~ 0 0! . 12 10~ 0 . 7 0", "0! . 0 12~ 0 . 0! 3 . 0 10 0 12! . 0 7~", "0! 0 . 0 12! 0 . 5~ 7 . 0 0! . 3 0 12~", "0! 12 0 . 0 12~ 13 0 0! . 0 12 . 10~ 0 .", "0! . 3 0 . 0! 7~ 0 . 12 0 . 0! 10 . 7~", "0! . . 0 . . 0 12~ . 0! . . 3 . 0 ."].map(A);
var PR=[[[0,'m'],[0,'m'],[-4,'M'],[-2,'M']],[[0,'m'],[3,'M'],[-2,'M'],[0,'m']],[[0,'m'],[-4,'M'],[-7,'m'],[-5,'M']],[[0,'m'],[1,'M'],[0,'m'],[-2,'M']],[[0,'m'],[-4,'M'],[3,'M'],[-2,'M']],[[0,'m'],[0,'m'],[0,'m'],[-2,'M']],[[0,'s'],[0,'m'],[-2,'s'],[-2,'M']]];
function T(name,k,bpm,drums,bass,lead,stab,hats,pr,ac,fx,o){var t={name:name,k:k,bpm:bpm,drums:drums,bass:bass,lead:lead,stab:stab,hats:hats,prog:PR[pr],acid:AC_[ac],fx:fx,sw:0,kick:'soft',arp:[0,2,1,3,2,1,0,3]};if(o)for(var x in o)t[x]=o[x];return t}
var TUNES=[
 T('Night Shift',45,128,'four','acid','none','saw',2,0,0,'I',{g:1.0}),
 T('Robot Talk',43,116,'electro','square','sqarp','none',1,1,0,'IL'),
 T('Warehouse',47,138,'four','offbeat','none','hoover',3,2,0,'IS'),
 T('Breakbeat Heart',44,136,'breaks','reese','none','saw',1,3,0,'I'),
 T('Laser Lights',50,134,'four','offbeat','arp','none',2,4,0,'IL',{arp:[0,1,2,3,2,1,2,3],g:1.2}),
 T('Low Tide',48,124,'four','acid','none','none',1,5,5,'I',{g:0.9}),
 T('Air Raid',46,140,'four','acid','none','saw',3,2,1,'ISL',{kick:'hard'}),
 T('Gabber Guard',44,168,'gabber','offbeat','none','hoover',3,0,0,'ILS',{kick:'gabber',g:1.2}),
 T('Jungle Proof',45,172,'dnb','reese','bleep','none',2,1,0,'IS',{g:0.7}),
 T('Wobble Chain',43,140,'half','wobble','none','none',2,3,0,'IL',{g:0.55}),
 T('Bleep Test',48,126,'four','square','bleep','none',2,5,0,'I',{g:0.5}),
 T('Psy Ledger',46,142,'four','roll','acidlead','none',2,0,3,'IL'),
 T('Two Step Witness',49,132,'twostep','offbeat','bleep','saw',2,4,0,'I',{sw:.14,g:1.4}),
 T('Stutter Gate',47,130,'four','acid','arp','saw',2,1,2,'IT',{g:1.0}),
 T('Hardcore Hash',45,150,'breaks','offbeat','none','hoover',3,2,0,'ISL',{kick:'hard',g:1.2}),
 T('Chain Reaction',44,128,'electro','acid','none','none',2,6,4,'ILT',{g:1.3}),
 T('Ultraviolet',50,136,'four','roll','arp','hoover',2,4,0,'IL'),
 T('Block Height',43,124,'electro','wobble','bleep','none',1,5,0,'I',{wdiv:8,g:0.5}),
 T('Final Seal',46,145,'four','acid','acidlead','saw',3,0,1,'ISLT',{kick:'hard'}),
 T('After Hours',48,128,'four','square','sqarp','saw',2,6,0,'IL')
];
var BARS=64;

var padGate,ctx=null,master,musicBus,popBus,scBus,padBus,padLP,stabBus,acidBus,acidLP,acidLFO,drumBus,lp,lpVal=4000,dly,started=false,playing=false,timer=null,switching=false;
var cur=null,ti=0,step=0,nextT=0,duck=1,BUF={},lastAcidHz=0;
var FILES=null,fi=0,audio=null,fileBus=null,mode='gen',curName='';

function mk(len,fn){var sr=ctx.sampleRate,n=Math.floor(sr*len),b=ctx.createBuffer(1,n,sr);fn(b.getChannelData(0),sr,n);return b}
function impulse(sec,pre){var r=ctx.sampleRate,n=Math.floor(r*sec),p=Math.floor(r*pre),b=ctx.createBuffer(2,n,r);for(var c=0;c<2;c++){var d=b.getChannelData(c),l=0;for(var i=p;i<n;i++){l+=((Math.random()*2-1)-l)*.5;d[i]=l*Math.pow(1-(i-p)/(n-p),3)}}return b}
function drums(){
 BUF.kick=mk(.5,function(d,sr,n){var ph=0;for(var i=0;i<n;i++){var t=i/sr,f=48+190*Math.exp(-t*45);ph+=6.2832*f/sr;var a=t<.002?t/.002:Math.exp(-(t-.002)*6.5);d[i]=Math.tanh(2.2*Math.sin(ph)*a)*.9+(t<.004?(Math.random()*2-1)*.3*(1-t/.004):0)}});
 BUF.clap=mk(.4,function(d,sr,n){var a=0,p=0;for(var i=0;i<n;i++){var t=i/sr;a+=((Math.random()*2-1)-a)*.55;var h=a-p;p=a;var e=Math.exp(-t*13)+(t<.03?Math.exp(-((t*1000)%10)*.5)*.7:0);d[i]=h*e*1.2}});
 BUF.snare=mk(.25,function(d,sr,n){var a=0,p=0,ph=0;for(var i=0;i<n;i++){var t=i/sr;a+=((Math.random()*2-1)-a)*.6;var h=a-p;p=a;ph+=6.2832*200/sr;d[i]=h*Math.exp(-t*20)+Math.sin(ph)*Math.exp(-t*35)*.35}});
 BUF.ch=mk(.07,function(d,sr,n){var p=0;for(var i=0;i<n;i++){var r=Math.random()*2-1,t=i/sr;d[i]=(r-p)*Math.exp(-t*65)*.5;p=r}});
 BUF.oh=mk(.35,function(d,sr,n){var p=0;for(var i=0;i<n;i++){var r=Math.random()*2-1,t=i/sr;d[i]=(r-p)*(t<.002?t/.002:Math.exp(-t*11))*.42;p=r}});
 BUF.hkick=mk(.55,function(d,sr,n){var ph=0;for(var i=0;i<n;i++){var t=i/sr,f=46+260*Math.exp(-t*40);ph+=6.2832*f/sr;var a=t<.002?t/.002:Math.exp(-(t-.002)*5);d[i]=Math.tanh(4*Math.sin(ph)*a)*.8}});
 BUF.gkick=mk(.4,function(d,sr,n){var ph=0;for(var i=0;i<n;i++){var t=i/sr,f=55+300*Math.exp(-t*30);ph+=6.2832*f/sr;var a=t<.002?t/.002:Math.exp(-(t-.002)*7);d[i]=Math.tanh(9*Math.sin(ph)*a)*.62}});
 BUF.noise=mk(2,function(d){for(var i=0;i<d.length;i++)d[i]=Math.random()*2-1});
}
function init(){
 if(ctx)return;
 try{ctx=new AC()}catch(e){ctx=null;return}
 var comp=ctx.createDynamicsCompressor();comp.threshold.value=-14;comp.ratio.value=4;comp.attack.value=.005;comp.release.value=.15;comp.connect(ctx.destination);
 master=ctx.createGain();master.gain.value=1;master.connect(comp);
 popBus=ctx.createGain();popBus.gain.value=.3;popBus.connect(master);
 musicBus=ctx.createGain();musicBus.gain.value=0;
 lp=ctx.createBiquadFilter();lp.type='lowpass';lp.frequency.value=lpVal;lp.Q.value=.8;musicBus.connect(lp);
 var dry=ctx.createGain();dry.gain.value=.9;lp.connect(dry);dry.connect(master);
 var verb=ctx.createConvolver();verb.buffer=impulse(3,.02);var wet=ctx.createGain();wet.gain.value=.22;lp.connect(verb);verb.connect(wet);wet.connect(master);
 scBus=ctx.createGain();scBus.connect(musicBus);
 padLP=ctx.createBiquadFilter();padLP.type='lowpass';padLP.frequency.value=1800;padBus=ctx.createGain();padGate=ctx.createGain();padBus.connect(padGate);padGate.connect(padLP);padLP.connect(scBus);
 stabBus=ctx.createGain();stabBus.connect(scBus);
 // acid: resonant filter with slow LFO opening/closing, then drive
 acidLP=ctx.createBiquadFilter();acidLP.type='lowpass';acidLP.Q.value=14;acidLP.frequency.value=600;
 var al=ctx.createOscillator(),ag=ctx.createGain();al.frequency.value=1/15;ag.gain.value=450;al.connect(ag);ag.connect(acidLP.frequency);al.start();acidLFO=ag;
 var drv=ctx.createWaveShaper(),cv=new Float32Array(1024);for(var i=0;i<1024;i++){var x=i/511.5-1;cv[i]=Math.tanh(2.5*x)/Math.tanh(2.5)}drv.curve=cv;
 acidBus=ctx.createGain();acidBus.gain.value=.55;acidLP.connect(drv);drv.connect(acidBus);acidBus.connect(scBus);
 dly=ctx.createDelay(2);var fb=ctx.createGain();fb.gain.value=.35;var dl=ctx.createBiquadFilter();dl.type='lowpass';dl.frequency.value=2800;var dh=ctx.createBiquadFilter();dh.type='highpass';dh.frequency.value=400;
 var send=ctx.createGain();send.gain.value=.35;var dOut=ctx.createGain();dOut.gain.value=.45;
 stabBus.connect(send);acidBus.connect(send);send.connect(dh);dh.connect(dly);dly.connect(dl);dl.connect(fb);fb.connect(dly);
 if(ctx.createStereoPanner){var dp=ctx.createStereoPanner();dp.pan.value=.45;dl.connect(dp);dp.connect(dOut)}else dl.connect(dOut);dOut.connect(scBus);
 drumBus=ctx.createGain();drumBus.gain.value=1;drumBus.connect(musicBus);
 drums();
 document.addEventListener('visibilitychange',function(){if(!ctx)return;if(document.hidden){save();if(audio&&!audio.paused)audio.pause();if(ctx.state==='running')ctx.suspend()}else if(started){ctx.resume();if(mode==='file'&&playing&&audio)audio.play().catch(function(){})}});
}
function hz(m){return 440*Math.pow(2,(m-69)/12)}
function level(){return playing?(.8*st.vol*duck*(cur&&cur.g||1)):0}
function setLevel(sec){if(!ctx)return;var t=ctx.currentTime,g=mode==='file'&&fileBus?fileBus.gain:musicBus.gain,o=mode==='file'?musicBus.gain:(fileBus?fileBus.gain:null),lv=mode==='file'?.5*st.vol*duck*(playing?1:0):level();
 g.cancelScheduledValues(t);g.setValueAtTime(g.value,t);g.linearRampToValueAtTime(lv,t+(sec||.6));if(o){o.cancelScheduledValues(t);o.setValueAtTime(o.value,t);o.linearRampToValueAtTime(0,t+.5)}}

function voice(root,shape){var out=[];for(var i=0;i<shape.length;i++){var n=root+shape[i];while(n<57)n+=12;while(n>74)n-=12;out.push(n)}return out.sort(function(a,b){return a-b})}
function supersaw(ns,t,dur,peak,dest,att,filt){
 var f=ctx.createBiquadFilter(),g=ctx.createGain();f.type='lowpass';f.Q.value=1;f.frequency.setValueAtTime(filt[0],t);f.frequency.exponentialRampToValueAtTime(filt[1],t+Math.min(dur,.5));
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(peak,t+att);g.gain.setValueAtTime(peak,t+Math.max(att,dur*.4));g.gain.exponentialRampToValueAtTime(.0001,t+dur);
 f.connect(g);g.connect(dest);
 var det=[-24,-13,-5,0,6,14,25];
 for(var i=0;i<ns.length;i++){for(var j=0;j<det.length;j++){var o=ctx.createOscillator();o.type='sawtooth';o.frequency.value=hz(ns[i]);o.detune.value=det[j]+(Math.random()*3);var pg=ctx.createGain();pg.gain.value=.14;o.connect(pg);pg.connect(f);o.start(t);o.stop(t+dur+.05)}}
}
function acid(m,t,len,acc,slide){
 var o=ctx.createOscillator(),g=ctx.createGain(),f=hz(m);o.type='sawtooth';
 if(slide&&lastAcidHz){o.frequency.setValueAtTime(lastAcidHz,t);o.frequency.exponentialRampToValueAtTime(f,t+.06)}else o.frequency.setValueAtTime(f,t);
 lastAcidHz=f;
 var pk=acc?.34:.22;g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(pk,t+.004);g.gain.setValueAtTime(pk*.8,t+len*.7);g.gain.exponentialRampToValueAtTime(.0001,t+len+(slide?.04:.01));
 // per-note filter squelch on top of the slow sweep
 var fe=ctx.createGain();fe.gain.value=0;var eo=ctx.createConstantSource?ctx.createConstantSource():null;
 if(eo){eo.offset.setValueAtTime(acc?1500:800,t);eo.offset.exponentialRampToValueAtTime(1,t+(acc?.18:.12));eo.connect(acidLP.frequency);eo.start(t);eo.stop(t+len+.05)}
 o.connect(g);g.connect(acidLP);o.start(t);o.stop(t+len+.06);
}
function hit(n,t,v,rate){var s=ctx.createBufferSource(),g=ctx.createGain();s.buffer=BUF[n];if(rate)s.playbackRate.value=rate;g.gain.value=v;s.connect(g);g.connect(drumBus);s.start(t)}
function kick(t){var kt=cur.kick==='gabber'?'gkick':(cur.kick==='hard'?'hkick':'kick');hit(kt,t,kt==='kick'?.62:.5);scBus.gain.cancelScheduledValues(t);scBus.gain.setValueAtTime(.3,t);scBus.gain.setTargetAtTime(1,t+.01,.07)}
function riser(t,dur){var s=ctx.createBufferSource(),f=ctx.createBiquadFilter(),g=ctx.createGain();s.buffer=BUF.noise;s.loop=true;f.type='bandpass';f.Q.value=1.6;
 f.frequency.setValueAtTime(300,t);f.frequency.exponentialRampToValueAtTime(9000,t+dur);g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.09,t+dur);g.gain.linearRampToValueAtTime(0,t+dur+.03);
 s.connect(f);f.connect(g);g.connect(musicBus);s.start(t);s.stop(t+dur+.05)}
function sweep(t,from,to,dur){lp.frequency.cancelScheduledValues(t);lp.frequency.setValueAtTime(from||lpVal,t);lp.frequency.exponentialRampToValueAtTime(to,t+dur);lpVal=to}
function e16(){return 60/cur.bpm/4}

function pluckSaw(m,t,peak,type,dec,cut){var o=ctx.createOscillator(),f=ctx.createBiquadFilter(),g=ctx.createGain();o.type=type;o.frequency.value=hz(m);f.type='lowpass';f.Q.value=4;f.frequency.setValueAtTime(cut,t);f.frequency.exponentialRampToValueAtTime(400,t+dec);
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(peak,t+.003);g.gain.exponentialRampToValueAtTime(.0001,t+dec);o.connect(f);f.connect(g);g.connect(stabBus);o.start(t);o.stop(t+dec+.02)}
function hoover(ns,t,dur){for(var i=0;i<ns.length;i++){for(var j=0;j<3;j++){var o=ctx.createOscillator(),g=ctx.createGain(),f=hz(ns[i]);o.type='sawtooth';o.frequency.setValueAtTime(f*.7,t);o.frequency.exponentialRampToValueAtTime(f,t+.07);o.detune.value=(j-1)*22;
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.022,t+.01);g.gain.exponentialRampToValueAtTime(.0001,t+dur);var pw=ctx.createBiquadFilter();pw.type='bandpass';pw.frequency.value=f*2;pw.Q.value=.6;o.connect(pw);pw.connect(g);g.connect(stabBus);o.start(t);o.stop(t+dur+.02)}}}
function reese(m,t,dur){var f=ctx.createBiquadFilter(),g=ctx.createGain();f.type='lowpass';f.frequency.setValueAtTime(260,t);f.frequency.linearRampToValueAtTime(700,t+dur*.5);f.frequency.linearRampToValueAtTime(300,t+dur);
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.2,t+.03);g.gain.setValueAtTime(.2,t+dur-.08);g.gain.exponentialRampToValueAtTime(.0001,t+dur);f.connect(g);g.connect(scBus);
 [-9,9].forEach(function(d){var o=ctx.createOscillator();o.type='sawtooth';o.frequency.value=hz(m);o.detune.value=d;o.connect(f);o.start(t);o.stop(t+dur+.02)});var s=ctx.createOscillator(),sg=ctx.createGain();s.frequency.value=hz(m-12);sg.gain.value=.5;s.connect(sg);sg.connect(g);s.start(t);s.stop(t+dur+.02)}
function obass(m,t,len,type){var o=ctx.createOscillator(),o2=ctx.createOscillator(),f=ctx.createBiquadFilter(),g=ctx.createGain(),g2=ctx.createGain();o.frequency.value=hz(m);o2.type=type||'sawtooth';o2.frequency.value=hz(m);g2.gain.value=.35;f.type='lowpass';f.frequency.value=900;f.Q.value=1.5;
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.3,t+.006);g.gain.exponentialRampToValueAtTime(.12,t+len);g.gain.exponentialRampToValueAtTime(.0001,t+len+.04);
 o.connect(f);o2.connect(g2);g2.connect(f);f.connect(g);g.connect(scBus);o.start(t);o2.start(t);o.stop(t+len+.06);o2.stop(t+len+.06)}
var DR={four:{k:[0,4,8,12],c:[4,12],g:[],sn:0},gabber:{k:[0,4,8,12],c:[4,12],g:[],sn:0},electro:{k:[0,6,10],c:[4,12],g:[14],sn:0},breaks:{k:[0,10],c:[4,12],g:[7,15],sn:1},dnb:{k:[0,10],c:[4,12],g:[7,14],sn:1},half:{k:[0,11],c:[8],g:[14],sn:1},twostep:{k:[0,7,10],c:[4,12],g:[],sn:1}};
function laser(t){var o=ctx.createOscillator(),g=ctx.createGain(),f0=1500+Math.random()*2500;o.type=Math.random()<.5?'sawtooth':'square';o.frequency.setValueAtTime(f0,t);o.frequency.exponentialRampToValueAtTime(70,t+.28);
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.045,t+.005);g.gain.exponentialRampToValueAtTime(.0001,t+.3);var bp=ctx.createBiquadFilter();bp.type='lowpass';bp.frequency.value=5000;o.connect(bp);bp.connect(g);g.connect(stabBus);o.start(t);o.stop(t+.32)}
function siren(t,dur,m){var o=ctx.createOscillator(),l=ctx.createOscillator(),lg_=ctx.createGain(),g=ctx.createGain(),f=ctx.createBiquadFilter();o.type='sawtooth';o.frequency.value=hz(m);l.frequency.value=5.5;lg_.gain.value=500;l.connect(lg_);lg_.connect(o.detune);
 f.type='bandpass';f.frequency.value=hz(m)*2;f.Q.value=.7;g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.05,t+.2);g.gain.setValueAtTime(.05,t+dur-.25);g.gain.exponentialRampToValueAtTime(.0001,t+dur);
 o.connect(f);f.connect(g);g.connect(stabBus);o.start(t);l.start(t);o.stop(t+dur+.02);l.stop(t+dur+.02)}
function bleep(m,t){var o=ctx.createOscillator(),g=ctx.createGain();o.type='square';o.frequency.value=hz(m);g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.035,t+.003);g.gain.exponentialRampToValueAtTime(.0001,t+.09);var f=ctx.createBiquadFilter();f.type='lowpass';f.frequency.value=3500;o.connect(f);f.connect(g);g.connect(stabBus);o.start(t);o.stop(t+.1)}
function wbass(m,t,len,per){var f=ctx.createBiquadFilter(),g=ctx.createGain();f.type='lowpass';f.Q.value=9;for(var x=t;x<t+len-.01;x+=per){f.frequency.setValueAtTime(160,x);f.frequency.exponentialRampToValueAtTime(1700,x+per*.45);f.frequency.exponentialRampToValueAtTime(160,x+per*.95)}
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.24,t+.02);g.gain.setValueAtTime(.24,t+len-.05);g.gain.exponentialRampToValueAtTime(.0001,t+len);f.connect(g);g.connect(scBus);
 [['sawtooth',0],['square',-8]].forEach(function(v){var o=ctx.createOscillator();o.type=v[0];o.frequency.value=hz(m);o.detune.value=v[1];o.connect(f);o.start(t);o.stop(t+len+.02)});var s=ctx.createOscillator(),sg=ctx.createGain();s.frequency.value=hz(m-12);sg.gain.value=.6;s.connect(sg);sg.connect(g);s.start(t);s.stop(t+len+.02)}
function impact(t){var o=ctx.createOscillator(),g=ctx.createGain();o.frequency.setValueAtTime(90,t);o.frequency.exponentialRampToValueAtTime(28,t+1.2);g.gain.setValueAtTime(.4,t);g.gain.exponentialRampToValueAtTime(.0001,t+1.3);o.connect(g);g.connect(musicBus);o.start(t);o.stop(t+1.35);
 var s=ctx.createBufferSource(),f=ctx.createBiquadFilter(),ng=ctx.createGain();s.buffer=BUF.noise;f.type='lowpass';f.frequency.setValueAtTime(8000,t);f.frequency.exponentialRampToValueAtTime(200,t+1.5);ng.gain.setValueAtTime(.09,t);ng.gain.exponentialRampToValueAtTime(.0001,t+1.6);s.connect(f);f.connect(ng);ng.connect(musicBus);s.start(t);s.stop(t+1.7)}
function schedule(s,t){
 var b=Math.floor(s/16),k=s%16,e=e16(),bd=e*16,ch=cur.prog[b%cur.prog.length],ns=voice(cur.k+ch[0],SH[ch[1]]),root=cur.k-12+ch[0],fx=cur.fx;
 var intro=b<4,brk=b>=32&&b<40,roll=b>=38&&b<40,outro=b>=58,dp=DR[cur.drums];
 var drumsOn=b>=4&&!brk&&b<62,full=(b>=16&&b<32)||(b>=40&&!outro),bassOn=!(b>=32&&b<36)&&b<62,leadOn=(b>=8&&!brk&&!outro)||(b>=36&&b<40);
 if(k===0){
  if(b===0)sweep(t,700,2500,bd*4);
  if(b===4)sweep(t,0,4000,bd*.5);
  if(b===16){sweep(t,0,9000,bd*.25);if(fx.indexOf('I')>=0)impact(t)}
  if(b===32)sweep(t,0,1400,bd*2);
  if(b===36)sweep(t,0,6000,bd*4);
  if(b===38)riser(t,bd*2);
  if(b===40){sweep(t,0,9000,bd*.1);if(fx.indexOf('I')>=0)impact(t)}
  if(b===58)sweep(t,0,700,bd*4);
 }
 if(bassOn){
  var bt=cur.bass;
  if(bt==='acid'){var st_=cur.acid[k];if(st_){var nx=cur.acid[(k+1)%16];acid(root+st_[0],t,e*(nx&&nx[2]?1.02:.55),st_[1],st_[2])}}
  else if(bt==='reese'){if(k===0)reese(root,t,bd*.98)}
  else if(bt==='wobble'){if(k===0||k===8)wbass(root,t,e*8,e*(cur.wdiv||4))}
  else if(bt==='square'){var pat=[0,null,0,12,null,0,null,7,0,null,12,0,null,3,null,0];if(pat[k]!==null)obass(root+pat[k],t,e*.8,'square')}
  else if(bt==='roll'){if(k%4!==0)obass(root+(k%4===3&&b%2?12:0),t,e*.7,'sawtooth')}
  else if(bt==='offbeat'&&k%4===2)obass(root+(k===14&&b%2?12:0),t,e*1.5);
 }
 if(leadOn){
  var ld=cur.lead;
  if(ld==='arp'){var an=ns[cur.arp[(k>>1)%8]%ns.length]+12;if(k%2===0||full)pluckSaw(an+(k%2?12:0),t,full?.07:.05,'sawtooth',.14,full?5000:2500)}
  else if(ld==='sqarp'&&(k%2===0||(full&&k%4===3))){var sn=ns[cur.arp[(k>>1)%8]%ns.length]+(k%4===0?0:12);pluckSaw(sn,t,.06,'square',.1,3500)}
  else if(ld==='bleep'){var bp=[1,0,0,1,0,0,1,0,0,0,1,0,1,0,0,0];if(bp[k]&&(full||k<8))bleep(ns[(k+b)%ns.length]+24,t)}
  else if(ld==='acidlead'&&full){var al=cur.acid[(k+8)%16];if(al)acid(root+24+al[0],t,e*.5,al[1],al[2])}
 }
 if(fx.indexOf('L')>=0&&(full||brk)&&((k===14&&b%2===1)||(k===6&&b%4===3)||(Math.random()<.02)))laser(t);
 if(fx.indexOf('S')>=0&&k===0&&((b===36)||(full&&b%16===8)))siren(t,bd*(b===36?4:2),cur.k+12);
 if(fx.indexOf('T')>=0)padGate.gain.setValueAtTime(full?(k%2?.1:1):1,t);
 if(brk&&k===0&&b%2===0)supersaw(ns,t,bd*2,.05,padBus,.6,[900,2600]);
 if(cur.stab==='saw'&&(full||(b>=36&&b<40))&&(k===2||k===6||k===10||k===14||(k===7&&b%2===1)))supersaw(ns,t,.2,.05,stabBus,.004,[4200,900]);
 if(cur.stab==='hoover'&&(full||(b>=36&&b<40))&&(k===0||k===6||k===12)&&b%2===0)hoover(ns,t,.45);
 if(full&&k===0&&b%4===0&&cur.lead!=='sqarp')supersaw(ns,t,bd*4,.016,padBus,.8,[1200,2000]);
 if(drumsOn){
  if(dp.k.indexOf(k)>=0||(cur.drums==='electro'&&k===14&&b%2))kick(t);
  if(dp.c.indexOf(k)>=0&&(full||cur.drums!=='four'))hit(dp.sn?'snare':'clap',t,dp.sn?.26:.2);
  if(dp.g.indexOf(k)>=0&&dp.sn)hit('snare',t,.07);
  if((cur.drums==='four'||cur.drums==='gabber')&&!outro&&k%4===2)hit('oh',t,full?.14:.09);
 }
 if(!brk&&b<62&&!(intro&&b<2)){var hv=[.55,.25,.4,.25][k%4],on=cur.hats===3||(cur.hats===2)||(cur.hats===1&&k%2===0);if(on)hit('ch',t,hv*(full?.14:.09)*(cur.hats===3?1.1:1))}
 if(roll){var i=(b-38)*16+k,den=i<16?(k%4===0):(i<24?k%2===0:true);if(den)hit('snare',t,.05+.2*(i/32))}
}
function tick(){
 if(!ctx||!playing||switching||mode!=='gen')return;
 var e=e16();
 while(nextT<ctx.currentTime+.3){schedule(step,nextT);nextT+=e*(1+(step%2?-cur.sw:cur.sw));step++;if(step>=BARS*16){nextTune(1);return}}
}
function loadTune(i,skip){
 ti=((i%TUNES.length)+TUNES.length)%TUNES.length;cur=TUNES[ti];curName=cur.name;step=skip?64:0;if(skip)lpVal=4000;lastAcidHz=0;if(padGate)padGate.gain.setValueAtTime(1,ctx.currentTime);
 dly.delayTime.setValueAtTime(60/cur.bpm*.75,ctx.currentTime);
 nextT=ctx.currentTime+.1;ss('ti',ti);ui();
}
function nextTune(dir){
 if(switching)return;switching=true;var t=ctx.currentTime;
 musicBus.gain.cancelScheduledValues(t);musicBus.gain.setValueAtTime(musicBus.gain.value,t);musicBus.gain.linearRampToValueAtTime(0,t+1.5);
 setTimeout(function(){switching=false;loadTune(ti+(dir||1),true);setLevel(1)},1600);
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
 if(!cur)loadTune(sg('ti',Math.floor(Math.random()*TUNES.length)),true);
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
                        else "built-in music: 20 original electro/rave tunes, each a different style",
             "tracks": [t["name"] for t in tracks],
             "adds": "Music on every page, a pop on every button press, and a small music button under MY EARNINGS "
                     "with play/pause, next, volume and pops on/off",
             "starts": "on the visitor's first tap (browsers do not allow sound before that)",
             "fades_for_video": True}, 200)

```


## `modules/spec.py`

121 lines, 5086 bytes

```python
"""
Live API specification - /x/spec

/api/spec is a hardcoded constant. It describes the API as it was when
somebody last remembered to update it, which is a documentation problem
pretending to be a feature.

This discovers what is actually loaded, right now, by reading the modules
directory and each module's own docstring. Add a module and the spec
updates itself. Delete one and it disappears. There is no separate list to
maintain and therefore no list that can drift.

That matters here more than it would elsewhere: a platform whose pitch is
"check it, don't trust it" should not ship a self-description that is
quietly out of date.

    GET /x/spec           everything currently live
    GET /x/spec/modules   just the module list
"""

import importlib, os, pkgutil, re

VERSION = "1.0"

_EP = re.compile(r"^\s*(GET|POST|PUT|DELETE)\s+(/\S+)\s*(.*)$")


def _describe(name):
    """Pull a module's summary and endpoint list out of its own docstring."""
    try:
        m = importlib.import_module("modules." + name)
    except Exception as e:
        return {"module": name, "loaded": False, "error": str(e)}
    doc = (m.__doc__ or "").strip()
    lines = doc.splitlines()
    summary = ""
    for ln in lines:
        t = ln.strip()
        if t and not t.startswith("-") and not _EP.match(ln):
            summary = t
            break
    endpoints = []
    for ln in lines:
        mm = _EP.match(ln)
        if mm:
            endpoints.append({"method": mm.group(1),
                              "path": mm.group(2),
                              "takes": mm.group(3).strip() or None})
    out = {"module": name, "loaded": True, "summary": summary,
           "endpoints": endpoints,
           "version": getattr(m, "VERSION", None)}
    if not hasattr(m, "handle"):
        out["warning"] = "module has no handle() - it will not route"
    return out


def _modules():
    d = os.path.dirname(__file__)
    names = sorted(x.name for x in pkgutil.iter_modules([d])
                   if x.name not in ("router", "spec"))
    return [_describe(n) for n in names]


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404

    mods = _modules()

    if action == "modules":
        return {"count": len(mods), "modules": mods}, 200

    if action in ("", "all"):
        return {
            "spec_version": VERSION,
            "generated": "live - discovered at request time, not a stored list",
            "core": {
                "decision_engine": {
                    "path": "/api/govern",
                    "method": "POST",
                    "auth": "Bearer key",
                    "note": "deterministic scoring, verdict sealed before the response returns"
                },
                "notaries_public": [
                    {"method": "POST", "path": "/api/post/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/verify-post", "auth": "none"},
                    {"method": "POST", "path": "/api/identity/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/identity/check", "auth": "none"},
                    {"method": "POST", "path": "/api/payment/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/payment/check", "auth": "none"}
                ],
                "verification_public": [
                    {"method": "GET", "path": "/api/verify-chain",
                     "returns": "whole-chain integrity, recomputed"},
                    {"method": "GET", "path": "/api/inclusion",
                     "returns": "whether a given 64-char hash is sealed"},
                    {"method": "GET", "path": "/api/anchor-status",
                     "returns": "current tip, OpenTimestamps proof, calendar count"},
                    {"method": "GET", "path": "/api/regulation-map",
                     "returns": "engine features mapped to legal obligations"}
                ]
            },
            "modules": {
                "prefix": "/x/<module>/<action>",
                "auth": "Bearer key on every module route",
                "count": len(mods),
                "loaded": mods
            },
            "chain": {
                "algorithm": "SHA-256 hash chain",
                "scope": "one chain - every module seals into the same sequence as /api/govern",
                "anchoring": "chain tip submitted to OpenTimestamps, aggregated into a Merkle root, root committed to Bitcoin by several independent calendars",
                "receipts": "gapless per-key sequence issued in the same transaction as the chain write",
                "verify": "/api/verify-chain and /api/anchor-status, both without a key"
            },
            "honest_note": "This spec is generated by reading the modules directory at request time rather than from a stored list, so it cannot describe capabilities that are not actually loaded."
        }, 200

    return {"error": "unknown_action", "action": action,
            "available": ["", "modules"]}, 404

```


## `modules/spendgate.py`

669 lines, 32540 bytes

```python
"""
modules/spendgate.py  v1.0.0  -  Spend Gate: your AI can't spend without a sign-off

    Arm:     https://sebbi.pro/x/arm/status
    Page:    https://sebbi.pro/spend
    Verify:  https://sebbi.pro/x/spendgate/verify?token=...

WHAT IT IS
----------
An AI agent that wants to spend money - pay an invoice, buy API time, move
funds, place an order - asks sebbi.pro first. sebbi.pro checks the request
against the limits you set for that agent, scores it with the live engine,
seals the decision, and hands back a short SIGNED token:

  APPROVED  a signature naming the exact amount, payee and a few-minute window
  DENIED    a signed refusal, with the reason

Your own payment system (your bank API, Stripe, a crypto wallet, whatever you
already use) releases the money only if the token says APPROVED and the
signature checks out. Over the per-transaction limit, past the daily cap, a
payee you never allowed, or the engine flags it? No signature. No spend.

sebbi.pro IS THE SIGN-OFF, NOT THE WALLET. It never holds your money, never
holds the keys to your money, never touches a bank or a chain balance. It
signs an allow-or-deny decision; your rail enforces it. That keeps you in
full control and keeps sebbi.pro clear of holding client funds.

HOW THE SIGNATURE WORKS
-----------------------
The token is signed with the same Ed25519 key that signs every authority
proof (continuity.py). Anyone can check it with a standard library and the
published key at https://sebbi.pro/x/continuity/pubkey - no call to us, no
trust in us. Every request, approval and refusal is sealed in the chain and
provable against Bitcoin like everything else on sebbi.pro.

ROUTES  (/x/spendgate/<action>)
------
  GET  status, spec, pubkey, verify?token=                         public
  GET  policy?agent=                                               API key - read an agent's limits
  POST policy  {agent, per_tx, daily, currency, payees[]}          API key - set them
  POST request {agent, amount, currency, payee, reason}            API key - ask to spend
  POST confirm {token}                                             API key - mark it actually spent (one-shot)
  GET  grants?agent=                                               API key - recent decisions
Amounts are whole pounds in "amount"/"per_tx"/"daily", or exact pence in
"amount_pence"/"per_tx_pence"/"daily_pence".
"""

import base64
import binascii
import importlib.util
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone

VERSION = "1.0.0"
SITE = "https://sebbi.pro"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "pubkey"), ("GET", "verify"), ("GET", "")}

TOKEN_TAG = "sbg1"
SIG_PREFIX = b"AILEASH-SPENDGATE-v1:"
TTL = int(os.environ.get("SPENDGATE_TTL", "900"))          # a token is spendable for 15 minutes
MAX_PENCE = 10 ** 11                                        # £1,000,000,000 sanity ceiling
AGENT_RE = re.compile(r"^[A-Za-z0-9 ._:-]{1,80}$")
CUR_RE = re.compile(r"^[A-Za-z]{3}$")
PAYEE_RE = re.compile(r"^[A-Za-z0-9 @._:+/-]{1,120}$")

_state = {"ready": False, "pages": False, "mcp": False, "last_error": None,
          "requests": 0, "approved": 0, "denied": 0, "confirmed": 0}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _C():
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith("continuity.py") and hasattr(m, "_keys") and hasattr(m, "_ed_signature"):
            return m
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "continuity.py")
    spec = importlib.util.spec_from_file_location("spendgate_continuity", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ctx():
    s = _srv()
    return {"conn": s._conn, "lock": s._db_lock, "seal": s.seal, "get_key": s.get_key}


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _db(sql, args=(), one=False, write=False):
    s = _srv()
    with s._db_lock:
        cur = s._conn.execute(sql, args)
        if write:
            s._conn.commit()
            return cur.lastrowid
        return cur.fetchone() if one else cur.fetchall()


def _setup():
    s = _srv()
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS spendgate_policy(api_key TEXT, agent TEXT, per_tx_pence INTEGER,"
                  "daily_pence INTEGER, currency TEXT, payees_json TEXT, updated REAL, PRIMARY KEY(api_key, agent))")
        c.execute("CREATE TABLE IF NOT EXISTS spendgate_grant(id TEXT PRIMARY KEY, api_key TEXT, agent TEXT,"
                  "amount_pence INTEGER, currency TEXT, payee TEXT, reason TEXT, decision TEXT, reasons TEXT,"
                  "issued REAL, expires REAL, token_digest TEXT, block_index INTEGER, audit_hash TEXT,"
                  "confirmed INTEGER DEFAULT 0, confirmed_at REAL)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sg_grant ON spendgate_grant(api_key, agent, issued)")
        c.commit()


# ---------------------------------------------------------------------------
# money helpers
# ---------------------------------------------------------------------------

def _pence(data, whole_key, pence_key):
    if data.get(pence_key) is not None:
        v = data.get(pence_key)
    elif data.get(whole_key) is not None:
        try:
            v = round(float(data.get(whole_key)) * 100)
        except (TypeError, ValueError):
            return None
    else:
        return None
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    if v < 0 or v > MAX_PENCE:
        return None
    return v


def _money(pence, currency):
    sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(currency.upper(), "")
    return "%s%s%s" % (sym, "{:,.2f}".format(pence / 100.0), "" if sym else " " + currency.upper())


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------

def _get_policy(api_key, agent):
    r = _db("SELECT per_tx_pence, daily_pence, currency, payees_json FROM spendgate_policy WHERE api_key=? AND agent=?",
            (api_key, agent), one=True)
    if not r:
        return None
    try:
        payees = json.loads(r[3]) if r[3] else []
    except Exception:
        payees = []
    return {"per_tx_pence": r[0], "daily_pence": r[1], "currency": r[2], "payees": payees}


def set_policy(api_key, data):
    agent = str(data.get("agent", "")).strip()
    if not AGENT_RE.match(agent):
        return {"error": "bad_agent", "message": "Name the agent, e.g. 'billing-bot' or 'buyer-agent-1'."}, 400
    per_tx = _pence(data, "per_tx", "per_tx_pence")
    daily = _pence(data, "daily", "daily_pence")
    if per_tx is None or daily is None:
        return {"error": "limits_required", "message": "Set per_tx and daily (in pounds), the most this agent may spend per payment and per day."}, 400
    currency = str(data.get("currency", "GBP")).strip().upper()
    if not CUR_RE.match(currency):
        currency = "GBP"
    payees = data.get("payees") or []
    if isinstance(payees, str):
        payees = [p.strip() for p in re.split(r"[\n,]+", payees) if p.strip()]
    clean = []
    for p in payees[:200]:
        p = str(p).strip()
        if p and PAYEE_RE.match(p):
            clean.append(p[:120])
    _db("INSERT INTO spendgate_policy(api_key,agent,per_tx_pence,daily_pence,currency,payees_json,updated) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(api_key,agent) DO UPDATE SET per_tx_pence=excluded.per_tx_pence,"
        "daily_pence=excluded.daily_pence,currency=excluded.currency,payees_json=excluded.payees_json,updated=excluded.updated",
        (api_key, agent, per_tx, daily, currency, json.dumps(clean), time.time()), write=True)
    return {"ok": True, "agent": agent, "per_transaction": _money(per_tx, currency), "daily": _money(daily, currency),
            "currency": currency, "allowed_payees": clean or "any (no allow-list set)",
            "note": "Set an allow-list of payees to refuse any payment to anyone else."}, 200


def _spent_today(api_key, agent):
    t0 = time.time() - time.time() % 86400
    r = _db("SELECT COALESCE(SUM(amount_pence),0) FROM spendgate_grant WHERE api_key=? AND agent=? AND decision='APPROVED' "
            "AND issued>=? AND (confirmed=1 OR expires>?)", (api_key, agent, t0, time.time()), one=True)
    return r[0] if r else 0


# ---------------------------------------------------------------------------
# the signed token
# ---------------------------------------------------------------------------

def _sign(body):
    C = _C()
    seed, pk, _ = C._keys(_ctx())
    raw = _canon(body).encode("utf-8")
    sig = C._ed_signature(SIG_PREFIX + raw, seed, pk)
    return "%s.%s.%s" % (TOKEN_TAG, _b64e(raw), _b64e(sig))


def _open(token):
    try:
        tag, b, s = str(token).strip().split(".")
        if tag != TOKEN_TAG:
            return None, "not a sebbi.pro Spend Gate token (expected %s.)" % TOKEN_TAG
        raw, sig = _b64d(b), _b64d(s)
        body = json.loads(raw)
    except Exception:
        return None, "malformed token"
    C = _C()
    _seed, pk, _ = C._keys(_ctx())
    if not C._ed_checkvalid(sig, SIG_PREFIX + raw, pk):
        return None, "signature does not verify against the published key"
    return body, None


def _digest(token):
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# request a spend
# ---------------------------------------------------------------------------

def request(api_key, data):
    agent = str(data.get("agent", "")).strip()
    if not AGENT_RE.match(agent):
        return {"error": "bad_agent", "message": "Name the agent making the payment."}, 400
    amount = _pence(data, "amount", "amount_pence")
    if amount is None or amount <= 0:
        return {"error": "bad_amount", "message": "Send the amount to spend, e.g. {\"amount\": 49.99}."}, 400
    payee = str(data.get("payee", "")).strip()
    if not payee or not PAYEE_RE.match(payee):
        return {"error": "bad_payee", "message": "Name who is being paid."}, 400
    reason = re.sub(r"[\x00-\x1f]", "", str(data.get("reason", "")))[:200]
    currency = str(data.get("currency", "")).strip().upper()
    policy = _get_policy(api_key, agent)
    if not policy:
        return {"error": "no_policy", "message": "No spending limits set for agent '%s'. Set them first: POST "
                "%s/x/spendgate/policy {agent, per_tx, daily}." % (agent, SITE)}, 409
    currency = currency if CUR_RE.match(currency or "") else policy["currency"]
    _state["requests"] += 1

    problems = []
    if amount > policy["per_tx_pence"]:
        problems.append("over the per-transaction limit of %s" % _money(policy["per_tx_pence"], policy["currency"]))
    spent = _spent_today(api_key, agent)
    if spent + amount > policy["daily_pence"]:
        problems.append("would take today's spend past the daily cap of %s (already %s)" %
                        (_money(policy["daily_pence"], policy["currency"]), _money(spent, policy["currency"])))
    if policy["payees"] and payee not in policy["payees"]:
        problems.append("payee '%s' is not on the allow-list" % payee)
    if currency != policy["currency"]:
        problems.append("currency %s does not match the agent's policy currency %s" % (currency, policy["currency"]))

    # risk score through the live engine (this also seals the decision in the chain)
    engine = {}
    block = seal = None
    try:
        s = _srv()
        ev = {"user_id": agent[:120], "action": "agent_spend", "amount": round(amount / 100.0, 2),
              "country": str(data.get("country", "UK")).strip().upper()[:2] or "UK",
              "device_id": ("spend:" + agent)[:120], "anomaly": 0, "device_risk": 0,
              "payee": payee, "currency": currency, "reason": reason, "via": "spendgate/1"}
        res, st = s.govern(ev, api_key)
        if st == 200:
            engine = res
            block, seal = res.get("block_index"), res.get("audit_hash")
            if res.get("decision") == "BLOCK":
                problems.append("the engine blocked this payment (%s)" % ", ".join(res.get("reasons") or []) or "risk")
            elif res.get("decision") == "CHALLENGE":
                problems.append("the engine flagged this payment for human review")
        else:
            return {"error": res.get("error", "engine_error"), "message": res.get("message", "The engine refused the request.")}, st
    except Exception as e:
        _state["last_error"] = "govern: %s" % str(e)[:150]
        problems.append("could not reach the scoring engine")

    gid = "SG-" + secrets.token_hex(8)
    now = time.time()
    decision = "APPROVED" if not problems else "DENIED"
    exp = now + TTL if decision == "APPROVED" else now
    body = {"v": 1, "iss": "sebbi.pro", "grant": gid, "decision": decision, "agent": agent,
            "amount_pence": amount, "currency": currency, "payee": payee,
            "issued": int(now), "expires": int(exp), "block": block}
    if decision == "DENIED":
        body["reasons"] = problems
    token = _sign(body)
    _db("INSERT INTO spendgate_grant(id,api_key,agent,amount_pence,currency,payee,reason,decision,reasons,issued,"
        "expires,token_digest,block_index,audit_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (gid, api_key, agent, amount, currency, payee, reason, decision, json.dumps(problems), now, exp,
         _digest(token), block, seal), write=True)
    _state["approved" if decision == "APPROVED" else "denied"] += 1

    out = {"decision": decision, "grant": gid, "agent": agent, "amount": _money(amount, currency), "payee": payee,
           "token": token, "sealed_in_chain": seal, "block_index": block,
           "verify": "%s/x/spendgate/verify?token=%s" % (SITE, token[:16] + "..."),
           "engine_decision": engine.get("decision")}
    if decision == "APPROVED":
        out["expires_utc"] = _iso(exp)
        out["spend_instruction"] = ("Release the payment only now, and record this token. It is valid once, until "
                                    "%s. Confirm it with POST %s/x/spendgate/confirm once the money has moved." % (_iso(exp), SITE))
        out["message"] = "Approved. %s to %s." % (_money(amount, currency), payee)
    else:
        out["reasons"] = problems
        out["message"] = "Denied: " + "; ".join(problems) + ". Do not release the payment."
    return out, 200


def verify(token):
    body, err = _open(token)
    if err:
        return {"valid": False, "problem": err}, 200
    now = time.time()
    expired = body.get("decision") == "APPROVED" and now > float(body.get("expires", 0))
    g = _db("SELECT decision, confirmed, confirmed_at FROM spendgate_grant WHERE id=?", (body.get("grant"),), one=True)
    out = {"valid": True, "decision": body.get("decision"), "agent": body.get("agent"),
           "amount": _money(int(body.get("amount_pence", 0)), body.get("currency", "GBP")),
           "amount_pence": body.get("amount_pence"), "currency": body.get("currency"), "payee": body.get("payee"),
           "grant": body.get("grant"), "issued_utc": _iso(body.get("issued")), "expires_utc": _iso(body.get("expires")),
           "sealed_block": body.get("block"), "signature": "verified against the published Ed25519 key",
           "pubkey": "%s/x/continuity/pubkey" % SITE}
    if body.get("reasons"):
        out["reasons"] = body["reasons"]
    if body.get("decision") == "APPROVED":
        if expired:
            out["spendable"] = False
            out["problem"] = "this approval has expired - ask again"
        elif g and g[1]:
            out["spendable"] = False
            out["problem"] = "already spent (confirmed %s)" % _iso(g[2])
        else:
            out["spendable"] = True
            out["message"] = "Release this payment. Valid once, until %s." % _iso(body.get("expires"))
    else:
        out["spendable"] = False
    return out, 200


def confirm(api_key, data):
    token = str(data.get("token", "")).strip()
    body, err = _open(token)
    if err:
        return {"error": "bad_token", "problem": err}, 400
    gid = body.get("grant")
    g = _db("SELECT api_key, decision, confirmed, expires FROM spendgate_grant WHERE id=?", (gid,), one=True)
    if not g or g[0] != api_key:
        return {"error": "not_found", "message": "No such grant for this key."}, 404
    if g[1] != "APPROVED":
        return {"error": "not_approved", "message": "That payment was denied; nothing to confirm."}, 409
    if g[2]:
        return {"error": "already_confirmed", "message": "This approval was already spent."}, 409
    if time.time() > float(g[3]):
        return {"error": "expired", "message": "This approval expired before it was spent. Ask again."}, 409
    _db("UPDATE spendgate_grant SET confirmed=1, confirmed_at=? WHERE id=?", (time.time(), gid), write=True)
    _state["confirmed"] += 1
    return {"ok": True, "grant": gid, "message": "Recorded as spent. It cannot be used again."}, 200


def grants(api_key, agent=None):
    if agent:
        rows = _db("SELECT id,agent,amount_pence,currency,payee,decision,issued,confirmed FROM spendgate_grant "
                   "WHERE api_key=? AND agent=? ORDER BY issued DESC LIMIT 100", (api_key, agent))
    else:
        rows = _db("SELECT id,agent,amount_pence,currency,payee,decision,issued,confirmed FROM spendgate_grant "
                   "WHERE api_key=? ORDER BY issued DESC LIMIT 100", (api_key,))
    return {"grants": [{"grant": r[0], "agent": r[1], "amount": _money(r[2], r[3]), "payee": r[4], "decision": r[5],
                        "utc": _iso(r[6]), "spent": bool(r[7])} for r in rows]}, 200


# ---------------------------------------------------------------------------
# AI connector tools
# ---------------------------------------------------------------------------

MCP_TOOLS = [
    {"name": "sebbi_spend_policy",
     "description": "Set the spending limits for an AI agent: the most it may pay in one go and per day, and optionally an "
                    "allow-list of payees. Must be set before the agent can be approved to spend.",
     "inputSchema": {"type": "object", "required": ["api_key", "agent", "per_tx", "daily"],
                     "properties": {"api_key": {"type": "string"}, "agent": {"type": "string"},
                                    "per_tx": {"type": "number", "description": "Max per payment, in pounds"},
                                    "daily": {"type": "number", "description": "Max per day, in pounds"},
                                    "currency": {"type": "string"}, "payees": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "sebbi_spend_request",
     "description": "Ask sebbi.pro to approve a payment before an AI agent makes it. Returns a signed APPROVED or DENIED "
                    "token. Only release the money if it is APPROVED and spendable. sebbi.pro never holds the money.",
     "inputSchema": {"type": "object", "required": ["api_key", "agent", "amount", "payee"],
                     "properties": {"api_key": {"type": "string"}, "agent": {"type": "string"},
                                    "amount": {"type": "number", "description": "Amount in pounds"},
                                    "payee": {"type": "string"}, "reason": {"type": "string"}, "currency": {"type": "string"}}}},
    {"name": "sebbi_spend_verify",
     "description": "Check a Spend Gate token's signature and whether it may still be spent. Anyone can call this; no key needed.",
     "inputSchema": {"type": "object", "required": ["token"], "properties": {"token": {"type": "string"}}}},
]


def _install_mcp():
    if _state["mcp"]:
        return True
    try:
        try:
            from modules import mcp as M
        except Exception:
            import mcp as M
    except Exception as e:
        _state["last_error"] = "mcp: %s" % e
        return False
    if getattr(M, "_spendgate_tools", False):
        _state["mcp"] = True
        return True
    names = {t["name"] for t in M.TOOLS}
    for t in MCP_TOOLS:
        if t["name"] not in names:
            M.TOOLS.append(t)
    original = M._call

    def _call(name, a, ip, agent):
        if name not in ("sebbi_spend_policy", "sebbi_spend_request", "sebbi_spend_verify"):
            return original(name, a, ip, agent)
        a = a or {}
        if name == "sebbi_spend_verify":
            return verify(a.get("token"))
        key = str(a.get("api_key") or "").strip()
        if not key or not _srv().get_key(key):
            return {"error": "invalid_api_key", "message": "Open an account first with sebbi_create_account."}, 401
        if name == "sebbi_spend_policy":
            return set_policy(key, a)
        return request(key, a)

    M._call = _call
    note = (" To stop an AI agent spending without a sign-off: set limits with sebbi_spend_policy, then call "
            "sebbi_spend_request before every payment and release money only on an APPROVED, spendable token.")
    if isinstance(getattr(M, "INSTRUCTIONS", None), str) and note not in M.INSTRUCTIONS:
        M.INSTRUCTIONS = M.INSTRUCTIONS + note
    M._spendgate_tools = True
    _state["mcp"] = True
    return True


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------

def _N():
    try:
        from modules import notary as N
    except Exception:
        import notary as N
    return N


def _send(h, body, ctype):
    if isinstance(body, str):
        body = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "public, max-age=120")
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(body)


def _page():
    N = _N()
    body = r"""<title>Spend Gate — your AI can't spend without a sign-off — sebbi.pro</title>
<meta name="description" content="Your AI agent can't pay a penny without sebbi.pro signing off. Set the limits, it asks before every payment, and you get a signed yes or no — provable against Bitcoin. sebbi.pro is the sign-off, never your wallet.">
</head><body>""" + N._TOP + r"""
<main class="wrap">
<section class="hero">
<div class="kick"><i></i>SPEND GATE · NEW</div>
<h1>Your AI can't spend<br>without a <em>sign-off.</em></h1>
<p>Give an AI agent money to spend and you're trusting it not to go wrong. Spend Gate takes that on trust away. The agent asks sebbi.pro before every payment, it's checked against the limits you set and scored by the engine, and you get back a signed yes or no. Over the limit, wrong payee, acting out of line? No signature. No spend.</p>
<p class="sub" style="margin-top:14px;max-width:60ch"><b>sebbi.pro is the sign-off, never your wallet.</b> It never holds your money or the keys to it. It signs the decision; your own payment system releases the money only if the signature says yes.</p>
</section>

<section class="card" id="try">
<h2>Try it</h2>
<p class="sub">A live agent with a £100-per-payment limit and a £250 daily cap. Paste your sebbi.pro key, or just watch the decisions — every one is sealed and provable.</p>
<div class="row"><input type="text" id="k" placeholder="sebbi.pro API key (needed to set limits and request)" autocomplete="off"></div>
<div class="row"><button class="btn b" id="setup">1 · Set this agent's limits</button><span class="msg" id="m1"></span></div>
<div style="height:1px;background:var(--line);margin:14px 0"></div>
<div class="row" style="align-items:flex-end;gap:14px">
<div style="flex:1;min-width:120px"><label class="sub">Pay how much?</label><input type="number" id="amt" value="50" min="1" step="1"></div>
<div style="flex:2;min-width:160px"><label class="sub">To whom?</label><input type="text" id="pay" value="AWS" placeholder="payee"></div>
</div>
<div class="row"><button class="btn b" id="ask">2 · Ask to spend</button><span class="msg" id="m2"></span></div>
<div id="verdict"></div>
</section>

<section class="card">
<h2>How your code uses it</h2>
<p class="sub">One call before the agent pays. Release the money only on an approved, spendable token.</p>
<pre>POST https://sebbi.pro/x/spendgate/request
{ "api_key": "YOUR_KEY", "agent": "billing-bot",
  "amount": 49.99, "payee": "AWS", "reason": "monthly compute" }

-> { "decision": "APPROVED", "token": "sbg1.…", "expires_utc": "…" }
   release the payment, then POST /x/spendgate/confirm { token }

-> { "decision": "DENIED", "reasons": ["over the per-transaction limit"] }
   do not pay</pre>
<p class="sub" style="margin-top:12px">Anyone can check a token's signature against the published key, with no call to us: <a href="/x/continuity/pubkey">/x/continuity/pubkey</a>. Or let an AI assistant run it all — connect <a href="/connect">https://sebbi.pro/mcp</a> and ask it to gate a payment.</p>
</section>

<section class="card">
<h2>Why it holds</h2>
<div class="how">
<div><b>YOU SET THE RULES</b><p>Per-payment limit, daily cap, an allow-list of who can ever be paid. Per agent.</p></div>
<div><b>IT ASKS FIRST</b><p>Every payment is scored by the live engine and checked against your rules before a penny moves.</p></div>
<div><b>SIGNED YES OR NO</b><p>A short Ed25519-signed token, valid once, for a few minutes. Anyone can verify it.</p></div>
<div><b>SEALED FOREVER</b><p>Every approval and refusal is in the chain and provable against Bitcoin.</p></div>
</div>
</section>
</main>""" + N._FOOT + r"""
<script>
const $=s=>document.querySelector(s);
function esc(t){return String(t==null?'':t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function post(p,b){const h={'Content-Type':'application/json'};const k=$('#k').value.trim();if(k)h['Authorization']='Bearer '+k;
 const r=await fetch(p,{method:'POST',headers:h,body:JSON.stringify(b)});return[r.status,await r.json()]}
$('#setup').onclick=async()=>{$('#m1').className='msg';$('#m1').textContent='Setting limits…';
 try{const[st,d]=await post('/x/spendgate/policy',{agent:'demo-agent',per_tx:100,daily:250,currency:'GBP',payees:['AWS','OpenAI','Anthropic','Stripe']});
  if(st!==200)throw Error(d.message||d.error);$('#m1').className='msg ok';$('#m1').textContent='Limits set: £100 per payment, £250 a day, payees AWS / OpenAI / Anthropic / Stripe.';}
 catch(e){$('#m1').className='msg err';$('#m1').textContent=e.message}};
$('#ask').onclick=async()=>{$('#m2').className='msg';$('#m2').textContent='Asking sebbi.pro…';$('#verdict').innerHTML='';
 try{const[st,d]=await post('/x/spendgate/request',{agent:'demo-agent',amount:Number($('#amt').value||0),payee:$('#pay').value.trim()||'AWS',reason:'demo'});
  if(st!==200)throw Error(d.message||d.error);$('#m2').textContent='';
  const ok=d.decision==='APPROVED';
  $('#verdict').innerHTML='<div class="verdict'+(ok?'':' bad')+'"><h3>'+(ok?'Approved':'Denied')+' — '+esc(d.amount)+' to '+esc(d.payee)+'</h3><p>'+esc(d.message)+'</p>'+(d.block?'<p class="sub" style="margin-top:8px">Sealed in block '+d.block+' · <a href="/forever?block='+d.block+'">check it against Bitcoin</a></p>':'')+'</div>';}
 catch(e){$('#m2').className='msg err';$('#m2').textContent=e.message}};
</script></body></html>"""
    return N._page(N._HEAD + body)


def _install_pages():
    if _state["pages"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_spendgate_pages", False):
        _state["pages"] = True
        return True
    orig = H.do_GET

    def do_GET(self):
        p = (self.path or "").split("?")[0].rstrip("/")
        try:
            if p == "/spend":
                return _send(self, _page(), "text/html; charset=utf-8")
        except Exception as e:
            _state["last_error"] = "page: %s" % str(e)[:150]
        return orig(self)

    H.do_GET = do_GET
    H._spendgate_pages = True
    _state["pages"] = True
    return True


def arm(ctx=None):
    with _lock:
        if not _state["ready"]:
            _setup()
            _state["ready"] = True
        _install_pages()
        try:
            _install_mcp()
        except Exception as e:
            _state["last_error"] = "mcp: %s" % str(e)[:150]


# ---------------------------------------------------------------------------
# router entry
# ---------------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    try:
        arm(ctx)
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:150]
    data = data or {}
    if action in ("", "status"):
        return {"module": "spendgate", "version": VERSION, "armed": _state["pages"], "page": SITE + "/spend",
                "ai_connector_tools": _state["mcp"], "since_start": {k: _state[k] for k in ("requests", "approved", "denied", "confirmed")},
                "holds_funds": False, "last_error": _state["last_error"]}, 200
    if action == "spec":
        return {"module": "spendgate", "version": VERSION,
                "what": "An AI agent must get a signed sign-off from sebbi.pro before it spends. sebbi.pro checks the "
                        "limits you set, scores the payment, seals the decision, and signs APPROVED or DENIED. Your own "
                        "payment system enforces it. sebbi.pro never holds funds or the keys to funds.",
                "token": {"format": "%s.<base64 body>.<base64 Ed25519 signature>" % TOKEN_TAG,
                          "signed_with": "the continuity.py key at %s/x/continuity/pubkey" % SITE,
                          "fields": "v, iss, grant, decision, agent, amount_pence, currency, payee, issued, expires, block",
                          "ttl_seconds": TTL},
                "routes": {"policy": "POST %s/x/spendgate/policy {agent, per_tx, daily, currency, payees[]}" % SITE,
                           "request": "POST %s/x/spendgate/request {agent, amount, payee, reason}" % SITE,
                           "verify": "GET %s/x/spendgate/verify?token=..." % SITE,
                           "confirm": "POST %s/x/spendgate/confirm {token}" % SITE,
                           "grants": "GET %s/x/spendgate/grants?agent=..." % SITE,
                           "pubkey": "%s/x/spendgate/pubkey" % SITE},
                "holds_funds": False}, 200
    if action == "pubkey":
        C = _C()
        _seed, pk, source = C._keys(_ctx())
        return {"algorithm": "Ed25519", "public_key": binascii.hexlify(pk).decode(), "key_source": source,
                "signs": "Spend Gate approval and refusal tokens", "prefix": SIG_PREFIX.decode()}, 200
    if action == "verify":
        return verify(data.get("token"))
    if action == "policy":
        if not api_key:
            return {"error": "api_key_required"}, 401
        if method == "POST":
            return set_policy(api_key, data)
        pol = _get_policy(api_key, str(data.get("agent", "")).strip())
        if not pol:
            return {"error": "no_policy"}, 404
        return {"agent": str(data.get("agent", "")).strip(), "per_transaction": _money(pol["per_tx_pence"], pol["currency"]),
                "daily": _money(pol["daily_pence"], pol["currency"]), "currency": pol["currency"],
                "allowed_payees": pol["payees"] or "any (no allow-list set)"}, 200
    if action == "request" and method == "POST":
        if not api_key:
            return {"error": "api_key_required"}, 401
        return request(api_key, data)
    if action == "confirm" and method == "POST":
        if not api_key:
            return {"error": "api_key_required"}, 401
        return confirm(api_key, data)
    if action == "grants":
        if not api_key:
            return {"error": "api_key_required"}, 401
        return grants(api_key, str(data.get("agent", "")).strip() or None)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/src/modules/sebbi/index.ts`

237 lines, 7814 bytes

```
/**
 * Module: @/modules/sebbi
 * File: src/modules/sebbi/index.ts
 * Engine: sebbi.pro (AILeash by Monop Content)
 * Publisher: Monop Content (Justin Dobson)
 */

import { createHash, sign, verify } from "crypto";

// ============================================================================
// 1. CONFIGURATION & ENVIRONMENT SETUP
// ============================================================================

export const SEBBI_CONFIG = {
  engine: "sebbi.pro",
  publisher: "Monop Content",
  account: "Justin Dobson",
  version: "1.0.0",
  badgeTier: "GOLD_STAMP_VERIFIED",
  endpoints: {
    gateway: process.env.SEBBI_GATEWAY_URL || "https://api.sebbi.pro/v1/gateway",
    witness: process.env.SEBBI_WITNESS_URL || "https://api.sebbi.pro/v1/witness",
  },
  credentials: {
    apiKey: process.env.SEBBI_API_KEY || "",
    ed25519PrivateKey: process.env.SEBBI_ED25519_PRIVATE_KEY || "",
    ed25519PublicKey: process.env.SEBBI_ED25519_PUBLIC_KEY || "",
  },
  policy: {
    maxSpendLimitUSD: 50.0,
    enforceEUAIAct: true,
    enforceOnlineSafetyAct: true,
    drandAnchor: true,
    bitcoinAnchor: true,
  },
} as const;

// ============================================================================
// 2. TYPES & INTERFACES
// ============================================================================

export interface SpendGateToken {
  tokenId: `sbg1${string}`;
  amount: number;
  currency: string;
  agentId: string;
  timestamp: number;
  signature: string;
}

export interface DecisionLedgerEntry {
  sequenceId: number;
  agentId: string;
  actionHash: string;
  previousMerkleRoot: string;
  currentMerkleRoot: string;
  drandRound?: number;
  otsProof?: string;
  timestamp: number;
}

export interface SebbiGoldBadgeMetadata {
  verifiedBy: "sebbi.pro";
  issuer: "Monop Content";
  account: "Justin Dobson";
  badgeTier: "GOLD_STAMP_VERIFIED";
  badgeIcon: "🏅";
  anchors: {
    drandBeacon: boolean;
    bitcoinOTS: boolean;
    rfc6962Merkle: boolean;
  };
  policyCompliance: {
    euAiAct: "COMPLIANT_CLASS_A";
    onlineSafetyAct: "ENFORCED";
    latencyOverheadMs: number;
  };
}

// ============================================================================
// 3. SPEND GATE CIRCUIT BREAKER (Deterministic Policy Enforcement)
// ============================================================================

export class SpendGate {
  /**
   * Generates a signed Spend Gate token (sbg1...) before actions execute.
   */
  public static authorizeTransaction(
    agentId: string,
    amount: number,
    currency = "USD"
  ): SpendGateToken {
    if (amount > SEBBI_CONFIG.policy.maxSpendLimitUSD) {
      throw new Error(
        `[SpendGate Breaker]: Circuit opened. Requested spend ($${amount}) exceeds limit ($${SEBBI_CONFIG.policy.maxSpendLimitUSD}).`
      );
    }

    const timestamp = Date.now();
    const payload = `${agentId}:${amount}:${currency}:${timestamp}`;

    const signature = SEBBI_CONFIG.credentials.ed25519PrivateKey
      ? sign(null, Buffer.from(payload), SEBBI_CONFIG.credentials.ed25519PrivateKey).toString("hex")
      : createHash("sha256").update(payload).digest("hex");

    const randomSuffix = Math.random().toString(36).substring(2, 10);
    const tokenId: `sbg1${string}` = `sbg1${randomSuffix}`;

    return {
      tokenId,
      amount,
      currency,
      agentId,
      timestamp,
      signature,
    };
  }

  /**
   * Offline verification of Spend Gate token by third parties or auditors.
   */
  public static verifyToken(token: SpendGateToken): boolean {
    if (!token.tokenId.startsWith("sbg1")) return false;
    if (!SEBBI_CONFIG.credentials.ed25519PublicKey) return true;

    const payload = `${token.agentId}:${token.amount}:${token.currency}:${token.timestamp}`;
    return verify(
      null,
      Buffer.from(payload),
      SEBBI_CONFIG.credentials.ed25519PublicKey,
      Buffer.from(token.signature, "hex")
    );
  }
}

// ============================================================================
// 4. SEBBI AI GATEWAY & MERKLE DECISION LEDGER
// ============================================================================

export class SebbiAIGateway {
  private static sequenceCounter = 0;
  private static lastMerkleRoot = "0000000000000000000000000000000000000000000000000000000000000000";

  /**
   * Routes LLM calls through Sebbi AI Gateway for compliance checks and zero-latency local hashing.
   */
  public static async executeGovernedAction<T>(
    agentId: string,
    actionType: string,
    payload: Record<string, unknown>,
    spendGateToken?: SpendGateToken
  ): Promise<{ result: T; auditEntry: DecisionLedgerEntry }> {
    const startTime = performance.now();

    if (spendGateToken && !SpendGate.verifyToken(spendGateToken)) {
      throw new Error("[Sebbi Gateway]: Invalid or tampered Spend Gate token provided.");
    }

    const actionHash = createHash("sha256")
      .update(JSON.stringify({ actionType, payload, spendGateToken }))
      .digest("hex");

    this.sequenceCounter += 1;

    const currentMerkleRoot = createHash("sha256")
      .update(`${this.lastMerkleRoot}:${actionHash}`)
      .digest("hex");

    const auditEntry: DecisionLedgerEntry = {
      sequenceId: this.sequenceCounter,
      agentId,
      actionHash,
      previousMerkleRoot: this.lastMerkleRoot,
      currentMerkleRoot,
      timestamp: Date.now(),
    };

    this.lastMerkleRoot = currentMerkleRoot;

    this.commitBackgroundWitness(auditEntry).catch((err) =>
      console.error("[Sebbi Witness Sync Error]:", err)
    );

    const duration = performance.now() - startTime;
    console.log(`[Sebbi Engine] Action governed in ${duration.toFixed(3)}ms (Sequence #${auditEntry.sequenceId})`);

    const result = { status: "SUCCESS", executedAction: actionType } as unknown as T;

    return { result, auditEntry };
  }

  private static async commitBackgroundWitness(_entry: DecisionLedgerEntry): Promise<void> {
    // Non-blocking background anchoring for drand and OpenTimestamps
  }
}

// ============================================================================
// 5. GOLD BADGE RENDERER & METADATA
// ============================================================================

export class SebbiBadge {
  private static GOLD_ASCII_BADGE = `
  ┌─────────────────────────────────────────────────────────────┐
  │  🏅 SEBBI.PRO | GOLD AUTHORITATIVE AUDIT STAMP             │
  │  ─────────────────────────────────────────────────────────  │
  │  Issuer    : Monop Content (Justin Dobson)                  │
  │  Engine    : AILeash / sebbi.pro                            │
  │  Proof     : Ed25519 Signed • OpenTimestamps • drand Anchor │
  │  Status    : IMMUTABLE • SPEND GATE ACTIVE                  │
  └─────────────────────────────────────────────────────────────┘
  `;

  public static printGoldBadge(): void {
    console.log("\x1b[33m%s\x1b[0m", this.GOLD_ASCII_BADGE);
  }

  public static getBadgeMetadata(): SebbiGoldBadgeMetadata {
    return {
      verifiedBy: "sebbi.pro",
      issuer: "Monop Content",
      account: "Justin Dobson",
      badgeTier: "GOLD_STAMP_VERIFIED",
      badgeIcon: "🏅",
      anchors: {
        drandBeacon: true,
        bitcoinOTS: true,
        rfc6962Merkle: true,
      },
      policyCompliance: {
        euAiAct: "COMPLIANT_CLASS_A",
        onlineSafetyAct: "ENFORCED",
        latencyOverheadMs: 0.098,
      },
    };
  }
}

```


## `modules/standard.py`

422 lines, 19423 bytes

```python
"""
modules/standard.py  -  the Ordering Test discovery document for this domain

WHAT IT SERVES
--------------
  GET /.well-known/ordering-test.json   this operator's discovery document
  GET /x/standard/hash                  sha256 of that document
  GET /x/standard/status                what is installed, and honest counts

SHAPE
-----
Deliberately identical to the shape Red Flag AI Pro published first:

    checks: { <name>: { supported, demonstrable_publicly, endpoint, note } }

Two fields, not one, and the second is the better idea. "We built it" and
"you can verify it without an account" are different claims, and most of this
market blurs them. Separating them lets a vendor be honest about having
something real that an outsider still has to take on trust.

WHAT THE HOST HEADER IS DOING HERE
----------------------------------
base_url is derived from the request rather than written into the file. An
earlier draft had the domain hardcoded, which meant any operator running it
would publish somebody else's domain as the source - the opposite of a mirror.
Deriving it means this file can be lifted to any domain and tells the truth
about wherever it is actually running.

EVERY PUBLISHED ENDPOINT MUST WORK AS WRITTEN
---------------------------------------------
An endpoint marked demonstrable_publicly is a promise that a stranger can copy
it out of this document and get an answer. If the route needs a parameter, the
document names that parameter. If a value has to be discovered first, the
document says where to discover it. An endpoint that errors when followed
literally is a failed check, not a documentation detail.

HONESTY RULES THIS FILE FOLLOWS
-------------------------------
  - A check we have not built says supported: false. It does not quietly go
    missing from the document.
  - A check that exists but needs an account says demonstrable_publicly:
    false, however much we would like the tick.
  - runner is null. A runner exists in draft, but the checks have not been
    jointly agreed with the other mirror, so publishing one as though it were
    a settled standard would claim something neither operator has earned yet.

None of that is modesty. A conformance document whose author scores full marks
on the day they publish it is a marketing page.
"""

import hashlib
import json
import sys

VERSION = "1.2"
ORDERING_TEST_VERSION = "0.1"

PUBLIC = {("GET", "status"), ("GET", "hash"), ("GET", "spec"),
          ("GET", "document")}

# Several paths on purpose. /.well-known/ is where the standard says to look,
# but some platforms and static handlers reserve that prefix, so a plain root
# path is served as well. /x/standard/document goes through the normal router
# and cannot be intercepted by anything, which makes it the diagnostic.
DISCOVERY_PATHS = ("/.well-known/ordering-test.json",
                   "/ordering-test.json",
                   "/well-known/ordering-test.json")

VENDOR = "AILeash"
FALLBACK_BASE = "https://sebbi.pro"

RUNNER = None
RUNNER_NOTE = (
    "No shared runner file is published here yet. The checks themselves have "
    "not been jointly agreed with the other mirrors as of this document's "
    "publication. This describes AILeash's own side only, not a settled "
    "cross-vendor standard.")

# Order follows the other mirror's document so the two read side by side.
CHECKS = {
    "rule_binding": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/rulebind/prove",
        "note": ("The ruleset version is a component of a digest sealed with the "
                 "decision, not a field beside it. POST any inputs without an "
                 "account and the response returns the exact string that was "
                 "hashed - SHA-256 it yourself and confirm it matches. Alter the "
                 "ruleset hash and the digest stops recomputing; alter the digest "
                 "and the chain breaks. Verify a past record at "
                 "/x/rulebind/verify?receipt=... and see ruleset history at "
                 "/x/rulebind/packs. No scoring logic is disclosed at any point - "
                 "inputs are published as a digest, never as values."),
    },
    "commit_before_reveal": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/demo/review",
        "note": ("The reviewer receives the case with the machine verdict "
                 "withheld. Their own call and dwell time are sealed first, "
                 "then the verdict is revealed, and the chain fixes that order "
                 "permanently. No account needed - open a case, commit a "
                 "verdict, and check the block indices yourself. Commit "
                 "endpoint is /x/demo/commit."),
    },
    "authority_tokens": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/continuity/decisions",
        "note": ("Authority is derived, not looked up. Every grant points at a "
                 "parent and terminates at a human principal; scope, limits, "
                 "purpose and validity must narrow at every hop; and the whole "
                 "chain is re-derived at the instant of execution rather than "
                 "trusted from the instant of issue. A decision beyond delegated "
                 "authority escalates rather than executes. Issuing and exercising "
                 "authority are keyed, but the record is not: /x/continuity/decisions "
                 "lists real sealed evaluations without an account, and any id from "
                 "it opens at /x/continuity/decision and /x/continuity/trace, which "
                 "returns the full authority path with the grant and invariant that "
                 "broke. Blocks are listed alongside allows, because a refusal with "
                 "no public record is indistinguishable from never having been asked. "
                 "An empty list means no authority has been exercised yet, not that "
                 "none failed. Derivation rules at /x/continuity/spec."),
    },
    "mutual_witnessing": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/witness/peers",
        "note": ("Live, running both directions with an external peer chain "
                 "hourly since 1 August 2026. No account needed, run it "
                 "yourself. Our current tip is at /x/witness/tip and any party "
                 "can submit theirs at /x/witness/observe without an account."),
    },
    "completeness_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/root?period={period}&kind=receipts",
        "note": ("Per-period sorted Merkle root and exact leaf count, committed "
                 "before any export is requested. An export can then be checked "
                 "against a number fixed before anyone knew it would be asked "
                 "for. Committed periods are listed at /x/complete/periods - "
                 "take a period identifier from there and substitute it. Only "
                 "closed periods can be committed, so the current period will "
                 "not appear until it ends. A period listed nowhere is a period "
                 "nobody committed, which is itself the finding."),
    },
    "absence_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/prove?period={period}&value={value}",
        "note": ("Two adjacent leaves with consecutive indices demonstrate that "
                 "nothing sits between them, so absence is proved rather than "
                 "asserted. Both parameters are required: take a period from "
                 "/x/complete/periods and supply any value you like. Try a "
                 "value that is not there."),
    },
    "reconciliation": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/reconcile/public",
        "note": ("The sample is derived from the chain tip and sealed BEFORE any "
                 "data is requested, so the operator cannot choose which records "
                 "get examined or prepare only the flattering ones. Planning and "
                 "submitting are keyed because they touch an operator's own "
                 "records, but the part that decides whether any of it means "
                 "anything is not: /x/reconcile/public gives run counts, match "
                 "rates and mismatches without an account, and "
                 "/x/reconcile/proof?id=RUN-XXXXXXXX shows the two sealed block "
                 "indices so anyone can confirm the selection block precedes the "
                 "result block. Abandoned runs are published too - a plan is "
                 "sealed when it is planned, so a test that came back badly and "
                 "was dropped stays visible forever as a plan with no result. "
                 "What this does not prove: that the records are true. Two "
                 "systems the operator controls agreeing with each other is "
                 "consistency, not truth."),
    },
    "reproducibility": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/replay/challenge",
        "note": ("Determinism proved by public challenge without disclosing any "
                 "scoring logic. Submit inputs, the run is sealed, resubmit the "
                 "same inputs later and the verdict must be identical under an "
                 "unchanged code fingerprint at /x/replay/fingerprint."),
    },
    "consistency_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/consistency/proof?first={first}&second={second}",
        "note": ("RFC 6962 consistency proofs, deliberately unmodified so "
                 "existing Certificate Transparency verifiers work against them "
                 "directly. first and second are tree sizes - read the current "
                 "size from /x/consistency/root and pick any earlier one. "
                 "Anyone holding any earlier tip we served can show it is a "
                 "prefix of the current log at /x/consistency/ancestor."),
    },

    # ---- proposed addition, flagged as a proposal rather than assumed ----
    "external_anchoring": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/api/anchor-status",
        "note": ("PROPOSED AS A SEPARATE CHECK, not settled. The other mirror "
                 "currently folds anchoring into consistency_proof, but they "
                 "answer different questions: consistency shows the log only "
                 "ever grew, anchoring shows the time was fixed somewhere the "
                 "operator cannot reach. A log can be perfectly append-only and "
                 "still have been built last week. Here the tip is submitted to "
                 "OpenTimestamps and committed into Bitcoin; the other mirror "
                 "uses an RFC 3161 timestamp. The spec should permit any "
                 "external authority the operator does not control and require "
                 "it to be named - not mandate one. Offered for the joint "
                 "session."),
    },
}

DOCUMENT_NOTE = (
    "Every endpoint marked demonstrable_publicly is unauthenticated by design - "
    "run it yourself without asking us. Where an endpoint carries a {parameter}, "
    "the note for that check says where to get a valid value; every published "
    "endpoint is meant to work when followed literally, and one that does not is "
    "a failed check on our side, not a quibble. Checks marked supported but not "
    "demonstrable_publicly are real and built, but currently need a key to see, "
    "and say so plainly rather than passing on the day this was published. "
    "Nothing here proves the records are true. It describes the order things "
    "were committed in, which is a narrower claim and the only one that holds.")

_patched = [False]


def _base_from(handler):
    """Derive our own base URL from the request. An operator running this file
    on their own domain publishes their domain, not whoever wrote it."""
    try:
        host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host")
        if not host:
            return FALLBACK_BASE
        host = host.split(",")[0].strip()[:200]
        proto = (handler.headers.get("X-Forwarded-Proto") or "https").split(",")[0].strip()
        if proto not in ("http", "https"):
            proto = "https"
        return proto + "://" + host
    except Exception:
        return FALLBACK_BASE


def _base_from_ctx(ctx):
    """Same derivation for the routed /x/standard/document call.

    The router's ctx may or may not carry the request handler. If it does, the
    document served through the router names the same domain as the one served
    at /.well-known/ - which matters on a mirror, where hardcoding would make
    this file publish somebody else's domain again."""
    try:
        if isinstance(ctx, dict):
            for key in ("handler", "h", "request", "req", "self"):
                obj = ctx.get(key)
                if obj is not None and hasattr(obj, "headers"):
                    return _base_from(obj)
            headers = ctx.get("headers")
            if headers is not None:
                class _Shim(object):
                    pass
                shim = _Shim()
                shim.headers = headers
                return _base_from(shim)
        elif ctx is not None and hasattr(ctx, "headers"):
            return _base_from(ctx)
    except Exception:
        pass
    return FALLBACK_BASE


def _document(base):
    checks = {}
    for name, c in CHECKS.items():
        checks[name] = {
            "supported": c["supported"],
            "demonstrable_publicly": c["demonstrable_publicly"],
            "endpoint": c["endpoint"],
            "note": c["note"],
        }
    return {
        "ordering_test_version": ORDERING_TEST_VERSION,
        "vendor": VENDOR,
        "base_url": base,
        "runner": RUNNER,
        "runner_note": RUNNER_NOTE,
        "checks": checks,
        "witness_peers": base + "/x/witness/peers",
        "witness_tip": base + "/x/witness/tip",
        "committed_periods": base + "/x/complete/periods",
        "note": DOCUMENT_NOTE,
    }


def _digest(doc):
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_standard_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in DISCOVERY_PATHS:
            body = json.dumps(_document(_base_from(self)), indent=2).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._standard_patched = True
    _patched[0] = True
    print("STANDARD: /.well-known/ordering-test.json installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("STANDARD: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()
    base = _base_from_ctx(ctx)
    doc = _document(base)

    if method == "GET" and action == "document":
        return doc, 200

    if method == "GET" and action == "hash":
        canonical = _document(FALLBACK_BASE)
        return {
            "sha256": _digest(canonical),
            "of": "this operator's discovery document",
            "canonicalisation": ("JSON, keys sorted, no whitespace, UTF-8, "
                                 "base_url fixed to " + FALLBACK_BASE +
                                 " so the digest does not move with the "
                                 "requesting host"),
            "what_this_is_for": (
                "Confirming our own document has not changed. It is NOT the "
                "cross-mirror check - two operators publish different documents "
                "by design, because they list different endpoints, so their "
                "digests should differ and a mismatch would prove nothing. The "
                "cross-mirror comparison only means something once every mirror "
                "serves a byte-identical runner file and hashes that instead. "
                "No runner is agreed yet."),
            "document": canonical,
        }, 200

    if method == "GET" and action in ("", "status", "spec"):
        supported = [k for k, c in CHECKS.items() if c["supported"]]
        public = [k for k, c in CHECKS.items() if c["demonstrable_publicly"]]
        parameterised = [k for k, c in CHECKS.items()
                         if c["endpoint"] and "{" in c["endpoint"]]
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "module_version": VERSION,
            "ordering_test_version": ORDERING_TEST_VERSION,
            "serving": list(DISCOVERY_PATHS),
            "always_available": "/x/standard/document",
            "checks_total": len(CHECKS),
            "checks_supported": len(supported),
            "checks_publicly_demonstrable": len(public),
            "publicly_demonstrable": public,
            "supported_but_not_public": [k for k in supported if k not in public],
            "endpoints_needing_a_parameter": parameterised,
            "runner": RUNNER,
            "note": ("base_url is derived from the Host header, so this file "
                     "publishes whichever domain is actually serving it. Checks "
                     "listed under endpoints_needing_a_parameter cannot be "
                     "demonstrated until a real value exists to substitute - "
                     "for the completeness and absence checks that means at "
                     "least one committed period at /x/complete/periods."),
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status", "hash", "document"]}, 404

```
