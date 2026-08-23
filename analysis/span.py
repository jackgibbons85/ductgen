import numpy as np, sys, os, glob
sys.path.insert(0,r"C:/Users/redre/sldtool/analysis")
from stlread import read_stl
MOT=[(192.65,192.64),(671.94,192.64),(192.65,671.93),(671.94,671.93)]
CEN=(432.30,432.29)
for p in sorted(glob.glob(sys.argv[1])):
    tris,_=read_stl(p)
    v=tris.reshape(-1,3)
    best=None
    for i,(cx,cz) in enumerate(MOT):
        r=np.hypot(v[:,0]-cx,v[:,2]-cz)
        near=(r<200).mean()
        if best is None or near>best[1]: best=(i,near,cx,cz)
    i,near,cx,cz=best
    r=np.hypot(v[:,0]-cx,v[:,2]-cz)
    th=np.degrees(np.arctan2(v[:,2]-cz,v[:,0]-cx))%360
    # angular span handling wraparound
    s=np.sort(np.unique(np.round(th,1)))
    gaps=np.diff(np.r_[s, s[0]+360])
    k=int(np.argmax(gaps))
    lo=s[(k+1)%len(s)]; hi=s[k]
    span=(hi-lo)%360
    inring=r[(r>160)&(r<200)]
    print(f"{os.path.basename(p):<44} motor#{i} near={near*100:4.1f}%  r=[{r.min():7.2f},{r.max():7.2f}]  "
          f"theta={lo:6.1f}->{hi:6.1f} ({span:5.1f} deg)  y=[{v[:,1].min():5.2f},{v[:,1].max():5.2f}]")
