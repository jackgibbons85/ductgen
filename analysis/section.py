import numpy as np, sys, glob, os
sys.path.insert(0,r"C:/Users/redre/sldtool/analysis")
from stlread import read_stl

def slice_y(tris, y):
    segs=[]
    p=tris
    d = p[:,:,1]-y
    sgn = np.sign(d)
    mask = ~((sgn[:,0]==sgn[:,1])&(sgn[:,1]==sgn[:,2]))
    for t in p[mask]:
        pts=[]
        for i in range(3):
            a,b = t[i], t[(i+1)%3]
            if (a[1]-y)*(b[1]-y) < 0:
                f=(y-a[1])/(b[1]-a[1]); pts.append(a+f*(b-a))
            elif abs(a[1]-y)<1e-9: pts.append(a)
        if len(pts)>=2: segs.append((pts[0],pts[1]))
    return np.array(segs)

def radial(path, cx, cz, ys):
    tris,_ = read_stl(path)
    for y in ys:
        s = slice_y(tris,y)
        if len(s)==0: print(f"  y={y:6.2f}: empty"); continue
        pts = s.reshape(-1,3)
        r = np.hypot(pts[:,0]-cx, pts[:,2]-cz)
        th = np.degrees(np.arctan2(pts[:,2]-cz, pts[:,0]-cx))%360
        hist,edges = np.histogram(r, bins=60)
        peaks = [(f"{(edges[i]+edges[i+1])/2:.1f}",int(hist[i])) for i in range(60) if hist[i]>len(r)*0.01]
        print(f"  y={y:6.2f}: n={len(pts):5} rmin={r.min():7.2f} rmax={r.max():7.2f} th=[{th.min():.0f},{th.max():.0f}]")
        print(f"      r-clusters: {peaks}")

if __name__=='__main__':
    p=sys.argv[1]; cx=float(sys.argv[2]); cz=float(sys.argv[3])
    ys=[float(x) for x in sys.argv[4:]] or [1,5,10,20,30,39]
    print(os.path.basename(p))
    radial(p,cx,cz,ys)
