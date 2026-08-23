import numpy as np, sys
sys.path.insert(0,r"C:/Users/redre/sldtool/analysis")
from stlread import read_stl

def weld(tris, tol=1e-4):
    v = tris.reshape(-1,3)
    key = np.round(v/tol).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    return inv.reshape(-1,3), uniq*tol

class DSU:
    def __init__(s,n): s.p=np.arange(n)
    def find(s,x):
        p=s.p
        while p[x]!=x:
            p[x]=p[p[x]]; x=p[x]
        return x
    def union(s,a,b):
        ra,rb=s.find(a),s.find(b)
        if ra!=rb: s.p[rb]=ra

def components(path):
    tris,_ = read_stl(path)
    faces, verts = weld(tris)
    d = DSU(len(verts))
    for f in faces:
        d.union(f[0],f[1]); d.union(f[0],f[2])
    roots = np.array([d.find(i) for i in range(len(verts))])
    lab = roots[faces[:,0]]
    out=[]
    for r in np.unique(lab):
        sel = tris[lab==r]
        v = sel.reshape(-1,3)
        a,b,c = sel[:,0],sel[:,1],sel[:,2]
        vol = np.einsum('ij,ij->i',a,np.cross(b,c)).sum()/6.0
        out.append(dict(tris=len(sel), min=v.min(0), max=v.max(0), size=v.max(0)-v.min(0),
                        ctr=(v.max(0)+v.min(0))/2, vol=vol, verts=v, faces=sel))
    out.sort(key=lambda d:-abs(d['vol']))
    return out

if __name__=='__main__':
    cs = components(sys.argv[1])
    print(f"{len(cs)} bodies")
    for i,c in enumerate(cs):
        print(f"[{i:2}] tris={c['tris']:>6} vol={c['vol']/1000:9.2f}cm3 "
              f"size=({c['size'][0]:7.2f},{c['size'][1]:7.2f},{c['size'][2]:7.2f}) "
              f"ctr=({c['ctr'][0]:8.2f},{c['ctr'][1]:7.2f},{c['ctr'][2]:8.2f})")
