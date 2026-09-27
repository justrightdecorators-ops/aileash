"""
modules/sound.py  v1.0.0
Soft background music and button pops across sebbi.pro.

Arm after each deploy:  https://sebbi.pro/x/sound/status
(or everything at once:  https://sebbi.pro/x/arm/status)

What visitors get on every page:
  - Original music written in a sparse, late-night style: clean picked
    guitar with echo, deep sub bass, soft half-time beats, lots of space.
    Eight tunes, each about two and a half minutes, rotating on their own.
    Every tune is generated live in the browser, so there are no audio files
    to host and no music licence to pay for.
  - A soft "pop" whenever a button or link is pressed.
  - A small music button under MY EARNINGS: play/pause, next tune, volume,
    and pops on/off. Their choice is remembered.
  - Browsers only allow sound after the visitor's first tap, so the music
    starts on the first tap anywhere and picks up again on each new page.
  - It fades out while any video on the page is playing, and pauses when the
    visitor switches tab.

Nothing in server.py is edited. Pages are left untouched if they are not
plain HTML pages.
"""

import io
import sys

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

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

var SC={minor:[0,2,3,5,7,8,10],dorian:[0,2,3,5,7,9,10],aeolian:[0,2,3,5,7,8,10],phryg:[0,1,3,5,7,8,10]};
var TUNES=[
 {name:'Night Shift',root:45,scale:'minor',bpm:96,prog:[0,5,2,6],dens:.42,beat:1},
 {name:'Slow Signal',root:47,scale:'dorian',bpm:92,prog:[0,3,0,3],dens:.36,beat:1},
 {name:'North Sea',root:50,scale:'minor',bpm:88,prog:[0,5,3,4],dens:.30,beat:0},
 {name:'Quiet Ledger',root:48,scale:'aeolian',bpm:100,prog:[0,6,5,6],dens:.45,beat:1},
 {name:'Harbour Light',root:43,scale:'dorian',bpm:94,prog:[0,6,3,0],dens:.38,beat:1},
 {name:'After Hours',root:46,scale:'minor',bpm:90,prog:[0,2,5,6],dens:.34,beat:1},
 {name:'Second Witness',root:44,scale:'phryg',bpm:98,prog:[0,1,0,6],dens:.40,beat:1},
 {name:'Low Tide',root:49,scale:'aeolian',bpm:86,prog:[0,3,5,4],dens:.28,beat:0}
];
var TUNE_BARS=60;

var ctx=null,master,comp,musicBus,popBus,gtrBus,padBus,padLP,dly,dlyFb,started=false,playing=false,timer=null;
var cur=null,ti=0,step=0,bar=0,nextT=0,motif=[],motif2=[],duck=1,switching=false;

function impulse(sec){var r=ctx.sampleRate,n=Math.floor(r*sec),b=ctx.createBuffer(2,n,r);for(var c=0;c<2;c++){var d=b.getChannelData(c);for(var i=0;i<n;i++)d[i]=(Math.random()*2-1)*Math.pow(1-i/n,3);}return b}
var noiseBuf=null;
function init(){
 if(ctx)return;
 try{ctx=new AC()}catch(e){ctx=null;return}
 comp=ctx.createDynamicsCompressor();comp.threshold.value=-18;comp.ratio.value=3;comp.connect(ctx.destination);
 master=ctx.createGain();master.gain.value=1;master.connect(comp);
 popBus=ctx.createGain();popBus.gain.value=.32;popBus.connect(master);
 musicBus=ctx.createGain();musicBus.gain.value=0;
 var lp=ctx.createBiquadFilter();lp.type='lowpass';lp.frequency.value=3200;lp.Q.value=.2;musicBus.connect(lp);
 var dry=ctx.createGain();dry.gain.value=.85;lp.connect(dry);dry.connect(master);
 var verb=ctx.createConvolver();verb.buffer=impulse(3.2);var wet=ctx.createGain();wet.gain.value=.42;lp.connect(verb);verb.connect(wet);wet.connect(master);
 gtrBus=ctx.createGain();gtrBus.gain.value=1;gtrBus.connect(musicBus);
 dly=ctx.createDelay(2);dlyFb=ctx.createGain();dlyFb.gain.value=.34;var dlyLP=ctx.createBiquadFilter();dlyLP.type='lowpass';dlyLP.frequency.value=2200;
 var dlyOut=ctx.createGain();dlyOut.gain.value=.38;gtrBus.connect(dly);dly.connect(dlyLP);dlyLP.connect(dlyFb);dlyFb.connect(dly);dlyLP.connect(dlyOut);dlyOut.connect(musicBus);
 padLP=ctx.createBiquadFilter();padLP.type='lowpass';padLP.frequency.value=700;padBus=ctx.createGain();padBus.gain.value=1;padBus.connect(padLP);padLP.connect(musicBus);
 var n=ctx.sampleRate*.5;noiseBuf=ctx.createBuffer(1,n,ctx.sampleRate);var d=noiseBuf.getChannelData(0);for(var i=0;i<n;i++)d[i]=Math.random()*2-1;
 document.addEventListener('visibilitychange',function(){if(!ctx)return;if(document.hidden){save();if(ctx.state==='running')ctx.suspend()}else if(started&&(playing||st.pops))ctx.resume()});
}
function hz(m){return 440*Math.pow(2,(m-69)/12)}
function deg(i){var s=SC[cur.scale],o=Math.floor(i/7),k=((i%7)+7)%7;return s[k]+12*o}
function level(){return playing?(.8*st.vol*duck):0}
function setLevel(sec){if(!ctx)return;var t=ctx.currentTime;musicBus.gain.cancelScheduledValues(t);musicBus.gain.setValueAtTime(musicBus.gain.value,t);musicBus.gain.linearRampToValueAtTime(level(),t+(sec||.6))}

function env(g,t,a,peak,dec){g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(peak,t+a);g.gain.exponentialRampToValueAtTime(.0001,t+a+dec)}
function gtr(m,t,vel){
 var f=hz(m),parts=[[1,1,1.9],[2,.42,.9],[3,.2,.5],[4,.09,.3]];
 var pan=ctx.createStereoPanner?ctx.createStereoPanner():null,out=ctx.createGain();out.gain.value=.16*vel;
 if(pan){pan.pan.value=(Math.random()*.6-.3);out.connect(pan);pan.connect(gtrBus)}else out.connect(gtrBus);
 for(var i=0;i<parts.length;i++){var o=ctx.createOscillator(),g=ctx.createGain();o.type=i?'sine':'triangle';o.frequency.value=f*parts[i][0];o.detune.value=(Math.random()*6-3);env(g,t,.004,parts[i][1],parts[i][2]);o.connect(g);g.connect(out);o.start(t);o.stop(t+parts[i][2]+.1)}
}
function sub(m,t,dur){var o=ctx.createOscillator(),g=ctx.createGain();o.type='sine';o.frequency.value=hz(m);g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.2,t+.03);g.gain.setTargetAtTime(.12,t+.1,.4);g.gain.setTargetAtTime(.0001,t+dur-.25,.12);o.connect(g);g.connect(musicBus);o.start(t);o.stop(t+dur+.5)}
function pad(ms,t,dur){for(var i=0;i<ms.length;i++){for(var j=0;j<2;j++){var o=ctx.createOscillator(),g=ctx.createGain();o.type=j?'sine':'triangle';o.frequency.value=hz(ms[i]);o.detune.value=j?5:-5;g.gain.setValueAtTime(.0001,t);g.gain.linearRampToValueAtTime(.022,t+1.4);g.gain.setValueAtTime(.022,t+dur-1.2);g.gain.linearRampToValueAtTime(.0001,t+dur+.6);o.connect(g);g.connect(padBus);o.start(t);o.stop(t+dur+.8)}}}
function kick(t,v){var o=ctx.createOscillator(),g=ctx.createGain();o.frequency.setValueAtTime(120,t);o.frequency.exponentialRampToValueAtTime(42,t+.14);env(g,t,.003,.34*v,.32);o.connect(g);g.connect(musicBus);o.start(t);o.stop(t+.4)}
function noise(t,type,f,q,peak,dec){var s=ctx.createBufferSource(),bp=ctx.createBiquadFilter(),g=ctx.createGain();s.buffer=noiseBuf;bp.type=type;bp.frequency.value=f;bp.Q.value=q;env(g,t,.002,peak,dec);s.connect(bp);bp.connect(g);g.connect(musicBus);s.start(t);s.stop(t+dec+.05)}
function clap(t){noise(t,'bandpass',1500,.9,.09,.16);noise(t+.012,'bandpass',1900,1.2,.05,.12)}
function hat(t,v){noise(t,'highpass',7500,.5,.02*v,.035)}

var PENT=[0,2,3,4,6];
function makeMotif(dens){var m=[],last=9;for(var i=0;i<16;i++){if(i===0||Math.random()<dens){var c=PENT[Math.floor(Math.random()*5)]+7*(Math.random()<.25?2:1);if(Math.abs(c-last)>5)c=last+(c>last?2:-2);last=c;m.push(c)}else m.push(null)}return m}
function vary(m){var v=m.slice();for(var i=0;i<v.length;i++){if(Math.random()<.12)v[i]=v[i]===null?PENT[Math.floor(Math.random()*5)]+7:null}v[0]=m[0];return v}

function chordNotes(d){return [deg(d)+cur.root,deg(d+2)+cur.root,deg(d+4)+cur.root]}
function schedule(s,t){
 var b=Math.floor(s/8),k=s%8,e=60/cur.bpm/2,barDur=e*8,ch=cur.prog[Math.floor(b/2)%cur.prog.length];
 if(b%8===0&&k===0&&b>0)motif2=vary(motif);
 var mm=(Math.floor(b/8)%2)?motif2:motif,note=mm[(b%2)*8+k];
 if(note!==null){gtr(cur.root+12+deg(note),t,(k%2?.75:1)*(b<2?.8:1))}
 if(b>=16&&k===6&&Math.random()<.35)gtr(cur.root+24+deg(PENT[Math.floor(Math.random()*5)]),t,.45);
 if(k===0&&b%2===0)pad(chordNotes(ch),t,barDur*2);
 if(b>=4){if(k===0&&b%2===0)sub(cur.root-12+deg(ch),t,barDur*1.6);if(k===0&&b%2===1&&Math.random()<.5)sub(cur.root-12+deg(ch),t,barDur*.7)}
 if(cur.beat&&b>=8&&b<TUNE_BARS-4){if(k===0)kick(t,1);if(k===5&&Math.random()<.4)kick(t,.6);if(k===4)clap(t);if(k%2===0)hat(t,k===0?.6:1);else if(Math.random()<.25)hat(t,.5)}
}
function tick(){
 if(!ctx||!playing||switching)return;
 var e=60/cur.bpm/2;
 while(nextT<ctx.currentTime+.3){
  var sw=(step%2)?-.08:.08;schedule(step,nextT);nextT+=e*(1+sw);step++;
  if(step>=TUNE_BARS*8){nextTune(1);return}
 }
}
function loadTune(i,fresh){
 ti=((i%TUNES.length)+TUNES.length)%TUNES.length;cur=TUNES[ti];step=0;motif=makeMotif(cur.dens);motif2=vary(motif);
 if(dly){dly.delayTime.setValueAtTime(60/cur.bpm*.75,ctx.currentTime)}
 nextT=ctx.currentTime+.08;ss('ti',ti);ui();
}
function nextTune(dir){
 if(switching)return;switching=true;var t=ctx.currentTime;
 musicBus.gain.cancelScheduledValues(t);musicBus.gain.setValueAtTime(musicBus.gain.value,t);musicBus.gain.linearRampToValueAtTime(0,t+2.2);
 setTimeout(function(){switching=false;loadTune(ti+(dir||1));setLevel(2.5)},2300);
}
function play(){
 init();if(!ctx)return;ctx.resume();
 if(!cur)loadTune(sg('ti',Math.floor(Math.random()*TUNES.length)));
 playing=true;nextT=Math.max(nextT,ctx.currentTime+.08);
 if(!timer)timer=setInterval(tick,60);setLevel(2.5);ui();
}
function pause(){playing=false;setLevel(.8);ui()}
function save(){if(cur)ss('ti',ti)}
window.addEventListener('pagehide',save);

function pop(){
 if(!ctx||ctx.state!=='running')return;
 var t=ctx.currentTime,o=ctx.createOscillator(),g=ctx.createGain(),f=480+Math.random()*320;
 o.type='sine';o.frequency.setValueAtTime(f*2,t);o.frequency.exponentialRampToValueAtTime(f*.55,t+.07);
 g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.55,t+.004);g.gain.exponentialRampToValueAtTime(.0001,t+.11);
 o.connect(g);g.connect(popBus);o.start(t);o.stop(t+.13);
}

function mediaPlaying(){var m=document.querySelectorAll('video,audio');for(var i=0;i<m.length;i++){if(!m[i].paused&&!m[i].ended&&!m[i].muted&&m[i].volume>0)return true}return false}
function recheck(){var d=mediaPlaying()?0:1;if(d!==duck){duck=d;setLevel(1.2)}}
['play','playing','pause','ended','volumechange'].forEach(function(ev){document.addEventListener(ev,function(){setTimeout(recheck,50)},true)});

function unlock(){
 init();if(!ctx)return;
 var p=ctx.resume();
 if(!started){started=true;hint(false);if(st.music)play()}
 if(p&&p.then)p.then(function(){if(ctx.state==='running')['pointerdown','touchend','click','keydown'].forEach(function(ev){document.removeEventListener(ev,unlock,true)})});
}
['pointerdown','touchend','click','keydown'].forEach(function(ev){document.addEventListener(ev,unlock,true)});
var SEL='a,button,[role=button],summary,label,input[type=submit],input[type=button],input[type=checkbox],input[type=radio],select,[onclick]';
document.addEventListener('pointerdown',function(e){if(!st.pops)return;var el=e.target&&e.target.closest?e.target.closest(SEL):null;if(!el)return;init();if(ctx&&ctx.state!=='running')ctx.resume();pop()},true);

var css='#sebbi-snd{position:fixed;right:12px;top:calc(54px + env(safe-area-inset-top,0px));z-index:2147483000;width:36px;height:36px;border-radius:50%;'+
'background:rgba(10,15,30,.9);border:1.5px solid #8fd0ff;box-shadow:0 0 16px rgba(143,208,255,.35);display:flex;align-items:flex-end;justify-content:center;gap:3px;padding:0 0 10px;box-sizing:border-box;cursor:pointer;-webkit-tap-highlight-color:transparent}'+
'#sebbi-snd i{display:block;width:3px;background:#8fd0ff;border-radius:2px;height:5px;transition:height .3s}'+
'#sebbi-snd.on i{animation:sbsnd 1.1s ease-in-out infinite}#sebbi-snd.on i:nth-child(2){animation-delay:-.4s}#sebbi-snd.on i:nth-child(3){animation-delay:-.75s}'+
'#sebbi-snd.off{border-color:rgba(255,255,255,.3);box-shadow:none}#sebbi-snd.off i{background:rgba(255,255,255,.45);height:3px}'+
'@keyframes sbsnd{0%,100%{height:4px}50%{height:15px}}'+
'#sebbi-sndhint{position:fixed;right:54px;top:calc(61px + env(safe-area-inset-top,0px));z-index:2147483000;font:600 10.5px/1 "IBM Plex Mono",monospace;color:#8fd0ff;background:rgba(10,15,30,.85);padding:6px 9px;border-radius:999px;transition:opacity .6s;pointer-events:none}'+
'#sebbi-sndp{position:fixed;right:12px;top:calc(98px + env(safe-area-inset-top,0px));z-index:2147483001;width:232px;background:rgba(10,15,30,.96);color:#fff;border:1px solid rgba(143,208,255,.45);border-radius:14px;padding:12px 14px;box-shadow:0 10px 30px rgba(0,0,0,.45);font:500 12px/1.4 "IBM Plex Mono",monospace;display:none;box-sizing:border-box}'+
'#sebbi-sndp .l{font-size:9.5px;letter-spacing:.14em;color:#8fd0ff;opacity:.8}#sebbi-sndp .n{font-size:14px;font-weight:700;margin:3px 0 10px}'+
'#sebbi-sndp .r{display:flex;gap:8px;align-items:center;margin-bottom:10px}'+
'#sebbi-sndp button{flex:1;background:transparent;color:#fff;border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:7px 0;font:600 12px "IBM Plex Mono",monospace;cursor:pointer}'+
'#sebbi-sndp input[type=range]{flex:1;accent-color:#8fd0ff}#sebbi-sndp label{display:flex;gap:8px;align-items:center;cursor:pointer;font-size:11.5px}#sebbi-sndp input[type=checkbox]{accent-color:#8fd0ff}'+
'#sebbi-sndp .f{margin-top:9px;font-size:9.5px;opacity:.55}';
var btn,panel,hintEl,nameEl,ppBtn;
function build(){
 var s=document.createElement('style');s.textContent=css;document.head.appendChild(s);
 btn=document.createElement('div');btn.id='sebbi-snd';btn.setAttribute('role','button');btn.setAttribute('aria-label','Music');btn.innerHTML='<i></i><i></i><i></i>';
 panel=document.createElement('div');panel.id='sebbi-sndp';
 panel.innerHTML='<div class="l">NOW PLAYING</div><div class="n" id="sebbi-sndn">&nbsp;</div>'+
 '<div class="r"><button type="button" id="sebbi-sndpp">Play</button><button type="button" id="sebbi-sndnx">Next &#9654;&#9654;</button></div>'+
 '<div class="r"><span>&#128264;</span><input type="range" min="0" max="100" id="sebbi-sndv"><span>&#128266;</span></div>'+
 '<label><input type="checkbox" id="sebbi-sndpo"> Button pops</label><div class="f">Original music by sebbi.pro</div>';
 document.body.appendChild(btn);document.body.appendChild(panel);
 nameEl=panel.querySelector('#sebbi-sndn');ppBtn=panel.querySelector('#sebbi-sndpp');
 var v=panel.querySelector('#sebbi-sndv'),po=panel.querySelector('#sebbi-sndpo');v.value=Math.round(st.vol*100);po.checked=!!st.pops;
 btn.addEventListener('click',function(e){e.stopPropagation();panel.style.display=panel.style.display==='block'?'none':'block'});
 ppBtn.addEventListener('click',function(){if(playing){pause();st.music=false}else{play();st.music=true}ls('music',st.music)});
 panel.querySelector('#sebbi-sndnx').addEventListener('click',function(){if(!playing){play();st.music=true;ls('music',true)}else nextTune(1)});
 v.addEventListener('input',function(){st.vol=v.value/100;ls('vol',st.vol);setLevel(.2)});
 po.addEventListener('change',function(){st.pops=po.checked;ls('pops',st.pops)});
 document.addEventListener('click',function(e){if(panel.style.display==='block'&&!panel.contains(e.target)&&e.target!==btn&&!btn.contains(e.target))panel.style.display='none'});
 if(st.music){hintEl=document.createElement('div');hintEl.id='sebbi-sndhint';hintEl.textContent='♪ tap anywhere for music';document.body.appendChild(hintEl);setTimeout(function(){hint(false)},5000)}
 ui();
}
function hint(show){if(hintEl&&!show){hintEl.style.opacity='0';var h=hintEl;hintEl=null;setTimeout(function(){h.remove()},700)}}
function ui(){if(!btn)return;btn.className=playing?'on':'off';if(ppBtn)ppBtn.textContent=playing?'Pause':'Play';if(nameEl)nameEl.textContent=cur?cur.name:(TUNES[sg('ti',0)]||TUNES[0]).name}
if(document.body)build();else document.addEventListener('DOMContentLoaded',build);
})();
""".strip().encode("utf-8")

_patched = False


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


def _send_js(h):
    h.send_response(200)
    h.send_header("Content-Type", "application/javascript; charset=utf-8")
    h.send_header("Content-Length", str(len(JS)))
    h.send_header("Cache-Control", "public, max-age=86400")
    h.end_headers()
    h.wfile.write(JS)


_wrapper = [None]
_rewraps = [0]


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
            return _send_js(self)
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
    return ({"module": "sound", "version": VERSION, "armed": armed,
             "adds": "Soft original background music on every page (8 tunes, rotating), a pop on every button press, "
                     "and a small music button under MY EARNINGS with play/pause, next, volume and pops on/off",
             "starts": "on the visitor's first tap (browsers do not allow sound before that)",
             "fades_for_video": True,
             "script": "https://sebbi.pro/sound.js"}, 200)
