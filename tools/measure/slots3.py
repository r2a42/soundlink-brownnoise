import sys, wave, re, numpy as np
from faster_whisper import WhisperModel
f=sys.argv[1]; t0=float(sys.argv[2])
w=wave.open(f); r=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
m=WhisperModel('small.en',device='cpu',compute_type='int8')
dig=[]
for n in range(14):
    s=t0+9+3.5*n-0.8; e=s+3.5
    seg=x[int(s*r):int(e*r)]
    rms=float(np.sqrt((seg**2).mean()))
    if rms<0.003:
        dig.append(None); print('slot %2d %6.1f-%6.1f: SILENT rms %.4f'%(n,s,e,rms)); continue
    out,_=m.transcribe(seg,language='en',beam_size=5,vad_filter=False,condition_on_previous_text=False,initial_prompt="Battery 20%.")
    txt=" | ".join(o.text.strip() for o in out)
    mm=re.findall(r'(\d+)\s*%|(\d+) percent',txt)
    p=None
    for a,b in mm:
        v=int(a or b)
        if v%10==0 and 10<=v<=100: p=v
    d=None if p is None else p//10-1
    dig.append(d)
    print("slot %2d %6.1f-%6.1f: %-30s -> %s"%(n,s,e,txt,d))
for wi in (0,1):
    ds=dig[wi*7:wi*7+7]
    if None in ds: print("word",wi,"digits",ds,"UNREADABLE"); continue
    chk=sum(ds[:6])%8
    val=sum(d*8**i for i,d in enumerate(ds[:6]))
    print("word",wi,"digits(low first)",ds[:6],"check",ds[6],"expected",chk,"OK" if chk==ds[6] else "CHECK FAILS","value",val,hex(val))
