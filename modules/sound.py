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
