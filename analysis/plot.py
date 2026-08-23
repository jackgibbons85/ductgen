import numpy as np, sys, os, glob
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,r"C:/Users/redre/sldtool/analysis")
from stlread import read_stl
from section import slice_y

files=sorted(glob.glob(sys.argv[1]))
Y=[float(x) for x in sys.argv[2].split(',')]
fig,axes=plt.subplots(1,len(Y),figsize=(11*len(Y),11))
if len(Y)==1: axes=[axes]
cmap=plt.get_cmap('tab20')
for ax,y in zip(axes,Y):
    for i,p in enumerate(files):
        tris,_=read_stl(p)
        if tris[:,:,1].min()>y or tris[:,:,1].max()<y: continue
        s=slice_y(tris,y)
        if len(s)==0: continue
        c=cmap(i%20)
        for a,b in s:
            ax.plot([a[0],b[0]],[a[2],b[2]],color=c,lw=0.8)
        v=s.reshape(-1,3)
        nm=os.path.basename(p).replace('juiva - ','').replace('^Drone2','').replace('.STL','')
        ax.text(v[:,0].mean(),v[:,2].mean(),nm,fontsize=6,color='k',ha='center',
                bbox=dict(fc='w',alpha=.6,pad=0.5,lw=0))
    ax.set_aspect('equal'); ax.set_title(f"Y = {y} mm"); ax.grid(alpha=.3)
    ax.invert_yaxis()
plt.tight_layout(); plt.savefig(sys.argv[3],dpi=110)
print("saved",sys.argv[3])
