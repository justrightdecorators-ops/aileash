"""End-to-end check of Human Keys (modules/humankeys.py), run by checks.yml in the no-network sandbox."""
import os,sys,subprocess,time,urllib.request,tempfile,socket,fcntl,struct,json,random,hashlib
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
try: fcntl.ioctl(s,0x8914,struct.pack("16sH14s",b"lo",0x49,b""))
except Exception: pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
w=tempfile.mkdtemp();env=dict(os.environ,PORT="8833",DB_PATH=w+"/a.db",ANCHOR_DIR=w+"/x",OTS_AUTO_UPGRADE="0",CREDITS_TEST_MODE="1")
p=subprocess.Popen([sys.executable,"server.py"],env=env,stdout=open(w+"/l","w"),stderr=subprocess.STDOUT);time.sleep(3)
P,F=[],[]
def chk(n,c,d=""):(P if c else F).append(n);print(("  ok   " if c else "  FAIL ")+n+("" if c else "  -> "+str(d)[:300]))
def req(m,u,b=None,raw=False):
    rq=urllib.request.Request("http://127.0.0.1:8833"+u,data=json.dumps(b).encode() if b is not None else None,method=m,
        headers={"Content-Type":"application/json","X-Forwarded-For":"10.%d.%d.1"%(random.randint(0,250),random.randint(0,250))})
    try:
        with urllib.request.urlopen(rq,timeout=60) as r: x=r.read(); return r.status,(x if raw else json.loads(x or b"{}")),r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        x=e.read()
        try: return e.code,json.loads(x),None
        except Exception: return e.code,x,None
try:
    st,a,_=req("GET","/x/arm/status"); hk=[r for r in a["results"] if r["module"]=="humankeys"]
    chk("arms", a["armed"] and hk and hk[0]["armed"], hk)
    viewer="testviewer123456"
    st,h,_=req("GET","/c/hello?viewer="+viewer); chk("wallet exists (test grant 100p)", h.get("balance_pence")==100, h)
    text="I am typing this by hand to see whether the proof works, with a few mistakes along the way."
    th=hashlib.sha256(text.encode()).hexdigest()
    st,ch,_=req("GET","/x/humankeys/challenge"); chk("challenge", "sig" in ch, ch)
    random.seed(4)
    human=[max(25,int(random.lognormvariate(5.0,0.55))) for _ in range(95)]+[3200,2600]
    time.sleep(sum(human)/1000.0+1)  # real time must cover the typing claimed
    counts={"inserts":95,"typed_chars":95,"deletes":4,"multi_inserts":0,"multi_chars":0,"paste_events":0,"paste_chars":0,"final_length":len(text),"blurs":0}
    st,d,_=req("POST","/x/humankeys/seal",{"challenge":ch["challenge"],"sig":ch["sig"],"text_hash":th,"intervals":human,"counts":counts,"viewer":viewer})
    chk("human session seals", st==200 and d.get("sealed"), (st,d))
    chk("verdict human typed", d.get("verdict")=="HUMAN_TYPED", d.get("verdict"), )
    chk("50p taken", d.get("balance_pence")==50, d.get("balance_pence"))
    code=d.get("code","")
    st,r,_=req("GET","/x/humankeys/check?code="+code); chk("public check", st==200 and r.get("text_hash")==th, r)
    chk("no text stored", text not in json.dumps(r))
    st,c,_=req("POST","/x/humankeys/compare",{"code":code,"text_hash":th}); chk("compare matches", c.get("matches") is True, c)
    st,c,_=req("POST","/x/humankeys/compare",{"code":code,"text_hash":hashlib.sha256(b"other").hexdigest()}); chk("compare rejects other text", c.get("matches") is False, c)
    # robot: perfectly even timing
    st,ch2,_=req("GET","/x/humankeys/challenge"); time.sleep(1)
    robot=[8]*95
    st,d2,_=req("POST","/x/humankeys/seal",{"challenge":ch2["challenge"],"sig":ch2["sig"],"text_hash":th,"intervals":robot,"counts":counts,"viewer":viewer})
    chk("robot flagged mechanical", d2.get("verdict")=="MECHANICAL", d2.get("verdict"))
    chk("wallet now empty", d2.get("balance_pence")==0, d2.get("balance_pence"))
    st,ch3,_=req("GET","/x/humankeys/challenge"); time.sleep(sum(human)/1000.0+1)
    st,d3,_=req("POST","/x/humankeys/seal",{"challenge":ch3["challenge"],"sig":ch3["sig"],"text_hash":th,"intervals":human,"counts":counts,"viewer":viewer})
    chk("empty wallet asks for 50p", st==402 and d3.get("reason")=="not_enough_credit", (st,d3))
    # claiming more typing time than really passed
    st,ch4,_=req("GET","/x/humankeys/challenge")
    long=[400]*95
    st,d4,_=req("POST","/x/humankeys/seal",{"challenge":ch4["challenge"],"sig":ch4["sig"],"text_hash":th,"intervals":long,"counts":counts,"viewer":"another12345678"})
    chk("refuses typing longer than real time", st==422 and d4.get("verdict")=="REFUSED", (st,d4))
    # forged challenge
    bad=dict(ch4["challenge"]);bad["issued"]=bad["issued"]-3000
    st,d5,_=req("POST","/x/humankeys/seal",{"challenge":bad,"sig":ch4["sig"],"text_hash":th,"intervals":human,"counts":counts,"viewer":viewer})
    chk("refuses forged challenge", st==400, (st,d5))
    # text that appeared from nowhere
    st,ch6,_=req("GET","/x/humankeys/challenge"); time.sleep(sum(human)/1000.0+1)
    c6=dict(counts,final_length=900)
    st,d6,_=req("POST","/x/humankeys/seal",{"challenge":ch6["challenge"],"sig":ch6["sig"],"text_hash":th,"intervals":human,"counts":c6,"viewer":viewer})
    chk("refuses text that was never typed", st==422, (st,d6))
    for u in ["/keys","/k/","/k/"+code]:
        st,b,ct=req("GET",u,raw=True); chk("page "+u, st==200 and b"Human" in b, st)
    st,b,ct=req("GET","/k/%s.svg"%code,raw=True); chk("badge svg", st==200 and b"Human typed" in b and "svg" in (ct or ""), (st,ct))
    st,v,_=req("GET","/api/verify-chain"); chk("chain still verifies", v.get("valid") is True, v)
finally:
    p.terminate()
print("\npassed %d, failed %d"%(len(P),len(F)))
if F: print(open(w+"/l").read()[-2000:])

sys.exit(1 if F else 0)
