import sys, numpy as np
sys.path.insert(0,'tools')
import click_detect as cd
MULT,INC=-4508331,17
def w24(v):
    v&=0xFFFFFF; return v-(1<<24) if v&0x800000 else v
def gen(n,leak=11,ins=7,sa=6,sb=7,gsh=2,S=9,seed=21845):
    st=seed;acc=la=lb=0;out=np.empty(n,dtype=np.int32);mx=0;clip=0
    for i in range(n):
        st=w24(w24(st*MULT)+INC)
        acc=w24(acc-(acc>>leak)); acc=w24(acc+(st>>ins))
        la=w24(la+((acc-la)>>sa)); lb=w24(lb+((acc-lb)>>sb))
        v=w24(w24((la-lb)<<gsh)+acc); mx=max(mx,abs(acc),abs(v)); v>>=S
        if v>32767: v=32767;clip+=1
        if v<-32767: v=-32767;clip+=1
        out[i]=v
    return out,mx,clip
if __name__=="__main__":
    x=cd.decode_adpcm('build/payload/g10/brown_48000_58968_seamfix160_f480_b.adpcm').astype(np.float64)
    FS=48000
    def bands(sig):
        spec=np.abs(np.fft.rfft(sig*np.hanning(len(sig))))**2; fr=np.fft.rfftfreq(len(sig),1/FS)
        return np.array([10*np.log10(spec[(fr>f/2**0.5)&(fr<f*2**0.5)].mean()+1e-9) for f in (30,60,120,250,500,1000,2000,4000,8000,16000)])
    bp=bands(x); bp-=bp[5]
    for S in (8,9,10):
        g,mx,clip=gen(480000,S=S); gg=g[:len(x)].astype(float); b=bands(gg); b-=b[5]
        print("S",S,"rms %.0f peak %d clip %d maxreg %d (limit 8388607)"%(g.std(),abs(g).max(),clip,mx),"err %.2f"%np.sqrt(np.mean((b-bp)**2)))
    print("payload",np.round(bp,1)); print("model  ",np.round(b,1))
