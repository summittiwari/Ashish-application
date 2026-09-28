import numpy as np
import cv2
from PIL import Image
from skimage.metrics import structural_similarity
from .extract import render
from .config import MAX_PIXELS

def compare_visual(pa,pb,options,folder):
    a,sa=render(pa,options.dpi);b,sb=render(pb,options.dpi)
    # Pad to a common canvas, never rescale a changed page to conceal its size change.
    w=max(a.width,b.width);h=max(a.height,b.height)
    if w*h>MAX_PIXELS:
        factor=(MAX_PIXELS/(w*h))**.5
        a=a.resize((max(1,round(a.width*factor)),max(1,round(a.height*factor))));b=b.resize((max(1,round(b.width*factor)),max(1,round(b.height*factor))));sa*=factor;sb*=factor
        w=max(a.width,b.width);h=max(a.height,b.height)
    aa=np.full((h,w,3),255,dtype=np.uint8);bb=aa.copy()
    aa[:a.height,:a.width]=np.asarray(a);bb[:b.height,:b.width]=np.asarray(b)
    ga=cv2.cvtColor(aa,cv2.COLOR_RGB2GRAY);gb=cv2.cvtColor(bb,cv2.COLOR_RGB2GRAY)
    shift=[0.,0.];registered=False
    if options.registration_px and ga.std()>2 and gb.std()>2 and a.size==b.size:
        xy,response=cv2.phaseCorrelate(ga.astype(np.float32),gb.astype(np.float32))
        if response>.6 and max(abs(v) for v in xy)<=options.registration_px:
            shift=list(xy);registered=True
            bb=cv2.warpAffine(bb,np.float32([[1,0,-xy[0]],[0,1,-xy[1]]]),(w,h),borderValue=(255,255,255))
    delta=np.max(cv2.absdiff(aa,bb),axis=2)
    mask=(delta>options.pixel_threshold).astype(np.uint8)*255
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    keep=np.zeros(n,np.uint8)
    for i in range(1,n):
        if stats[i,cv2.CC_STAT_AREA]>=options.min_component_pixels:keep[i]=255
    mask=keep[labels];changed=int(np.count_nonzero(mask))
    # Group nearby pixels only for navigation boxes. Saved mask retains the exact changed pixels.
    grouping=cv2.dilate(mask,np.ones((5,5),np.uint8),iterations=1)
    contours,_=cv2.findContours(grouping,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    regions=[]
    for c in contours:
        x,y,cw,ch=cv2.boundingRect(c);pixels=int(np.count_nonzero(mask[y:y+ch,x:x+cw]))
        if pixels:regions.append(dict(bbox_a=[x/sa,y/sa,(x+cw)/sa,(y+ch)/sa],bbox_b=[(x+shift[0])/sb,(y+shift[1])/sb,(x+cw+shift[0])/sb,(y+ch+shift[1])/sb],pixels=pixels))
    folder.mkdir(parents=True,exist_ok=True)
    thumb=Image.fromarray(mask);thumb.save(folder/'mask.png')
    heat=np.asarray(a.resize((w,h))).copy();heat[mask>0]=[244,63,94];Image.fromarray(heat).save(folder/'heatmap.png')
    # SSIM is a supplementary downsampled metric, not a claimed detector accuracy.
    width=min(1200,w);height=max(8,round(h*width/w))
    xa=cv2.resize(ga,(width,height));xb=cv2.resize(cv2.cvtColor(bb,cv2.COLOR_RGB2GRAY),(width,height))
    ssim=float(structural_similarity(xa,xb,data_range=255)) if min(xa.shape)>=7 else None
    return dict(score=round(100*(1-changed/(w*h)),6),ssim=ssim,changed_pixels=changed,total_pixels=w*h,regions=regions,registration=dict(applied=registered,shift_px=shift),effective_dpi=[sa*72,sb*72],mask_dimensions=[w,h])
