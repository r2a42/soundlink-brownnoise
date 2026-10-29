import sys,wave,numpy as np
w=wave.open(sys.argv[1]);r=w.getframerate();x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
for t in range(0,int(len(x)/r),3):
    seg=x[t*r:(t+3)*r]; print(t,"%.4f"%np.sqrt((seg**2).mean()))
