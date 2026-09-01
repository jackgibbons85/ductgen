import numpy as np, sys, os
sys.path.insert(0,r"C:/Users/redre/sldtool/analysis")
from stlread import read_stl
from components import weld, DSU

def circle_fit(P):
    x,y=P[:,0],P[:,1]
    A=np.c_[2*x,2*y,np.ones(len(P))]
    b=x**2+y**2
    sol,*_=np.linalg.lstsq(A,b,rcond=None)
    cx,cy=sol[0],sol[1]; r=np.sqrt(max(sol[2]+cx**2+cy**2,1e-9))
    res=np.abs(np.hypot(x-cx,y-cy)-r)
    return cx,cy,r,res.max()

def run(path, rmax=200.0):
    tris,nrm=read_stl(path)
    n=nrm/(np.linalg.norm(nrm,axis=1,keepdims=True)+1e-12)
    sel=np.abs(n[:,1])<0.06
    t=tris[sel]; nn=n[sel]
    if len(t)==0: print(path,"no walls"); return
    faces,verts=weld(t)
    d=DSU(len(verts))
    for f in faces:
        d.union(f[0],f[1]); d.union(f[0],f[2])
    root=np.array([d.find(i) for i in range(len(verts))])
    lab=root[faces[:,0]]
    print(f"== {os.path.basename(path)}  ({len(np.unique(lab))} wall groups)")
    res=[]
    for r_ in np.unique(lab):
        g=(lab==r_)
        if g.sum()<6: continue
        pts=t[g].reshape(-1,3)
        P=pts[:,[0,2]]
        ang=np.degrees(np.arctan2(nn[g][:,2],nn[g][:,0]))%360
        a=np.sort(ang); spread=max(a[-1]-a[0], 360-(a[-1]-a[0]) if len(a)>1 else 0)
        cx,cy,rr,err=circle_fit(P)
        if err<0.8 and rr<rmax and g.sum()>=8:
            res.append((rr,cx,cy,g.sum(),pts[:,1].min(),pts[:,1].max(),err))
    res.sort()
    for rr,cx,cy,cnt,y0,y1,err in res:
        print(f"   d={2*rr:8.2f}  ctr=({cx:8.2f},{cy:8.2f})  y=[{y0:6.2f},{y1:6.2f}] facets={cnt:4} err={err:.3f}")

for p in sys.argv[1:]: run(p)
