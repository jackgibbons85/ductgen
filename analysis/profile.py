import numpy as np, sys
sys.path.insert(0,r"C:/Users/redre/sldtool/analysis")
from stlread import read_stl
from section import slice_y

p=sys.argv[1]; cx=float(sys.argv[2]); cz=float(sys.argv[3])
tris,_=read_stl(p)
ys=np.arange(0.3,40.0,0.75)
theta_t=float(sys.argv[4]) if len(sys.argv)>4 else None
rows=[]
for y in ys:
    s=slice_y(tris,y)
    if len(s)==0: continue
    pts=s.reshape(-1,3)
    r=np.hypot(pts[:,0]-cx,pts[:,2]-cz)
    th=np.degrees(np.arctan2(pts[:,2]-cz,pts[:,0]-cx))%360
    if theta_t is None:
        # pick middle of angular range
        theta_t=(th.min()+th.max())/2
    m=np.abs(th-theta_t)<1.2
    if m.sum()<2: rows.append((y,None)); continue
    rr=np.sort(r[m])
    # cluster radii
    cl=[]; cur=[rr[0]]
    for v in rr[1:]:
        if v-cur[-1]<1.5: cur.append(v)
        else: cl.append((min(cur),max(cur))); cur=[v]
    cl.append((min(cur),max(cur)))
    rows.append((y,cl))
print(f"theta={theta_t:.1f} deg, center=({cx},{cz})")
for y,cl in rows:
    if cl is None: print(f" y={y:5.2f}  --"); continue
    print(f" y={y:5.2f}  " + "  ".join(f"[{a:7.2f}..{b:7.2f}]" for a,b in cl))
