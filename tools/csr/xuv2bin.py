import sys,struct
inp,out=sys.argv[1],sys.argv[2]
b=bytearray()
n=0
for line in open(inp):
    line=line.strip()
    if not line or not line.startswith('@'): continue
    a,v=line.split()
    w=int(v,16)
    b+=struct.pack('<H',w)
    n+=1
open(out,'wb').write(bytes(b))
print(n,'words ->',len(b),'bytes')
