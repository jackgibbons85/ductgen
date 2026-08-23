import numpy as np, struct, sys, os

def read_stl(path):
    with open(path,'rb') as f:
        head = f.read(84)
        n = struct.unpack('<I', head[80:84])[0]
        rest = f.read()
    if len(rest) == n*50:
        data = np.frombuffer(rest, dtype=np.uint8).reshape(n,50)
        f32 = data[:,:48].copy().view(np.float32).reshape(n,4,3)
        normals = f32[:,0,:]
        tris = f32[:,1:,:]
        return tris.astype(np.float64), normals.astype(np.float64)
    # ascii fallback
    txt = open(path,'r',errors='ignore').read().split()
    v=[]
    for i,t in enumerate(txt):
        if t=='vertex': v.append([float(txt[i+1]),float(txt[i+2]),float(txt[i+3])])
    v=np.array(v); return v.reshape(-1,3,3), None

def info(path):
    t,nz = read_stl(path)
    v = t.reshape(-1,3)
    mn, mx = v.min(0), v.max(0)
    # volume via divergence
    a,b,c = t[:,0],t[:,1],t[:,2]
    vol = np.einsum('ij,ij->i', a, np.cross(b,c)).sum()/6.0
    area = 0.5*np.linalg.norm(np.cross(b-a,c-a),axis=1).sum()
    return dict(path=os.path.basename(path), tris=len(t), min=mn, max=mx, size=mx-mn,
                vol=vol, area=area)

if __name__=='__main__':
    for p in sys.argv[1:]:
        d = info(p)
        print(f"{d['path']:<45} tris={d['tris']:>7}  size={d['size'][0]:8.2f} x {d['size'][1]:8.2f} x {d['size'][2]:8.2f}  "
              f"min=({d['min'][0]:8.2f},{d['min'][1]:8.2f},{d['min'][2]:8.2f})  vol={d['vol']/1000:9.2f}cm3")
