"""Global page assignment with occurrence-aware exact matches and reorder detection."""
import math, difflib
import numpy as np
from scipy.optimize import linear_sum_assignment
from rapidfuzz.fuzz import ratio

def affinity(a,b):
    dims=min(a['width'],b['width'])/max(a['width'],b['width'])*min(a['height'],b['height'])/max(a['height'],b['height'])
    visual=1-sum(x!=y for x,y in zip(a['visual_hash'],b['visual_hash']))/64
    if a['text'].strip() and b['text'].strip():
        text=ratio(a['text'],b['text'])/100
        return .70*text+.22*visual+.08*dims
    return .90*visual+.10*dims

def align_pages(a,b,threshold=.53):
    free_a=set(range(len(a)));free_b=set(range(len(b)));pairs=[]
    lookup={}
    for j,p in enumerate(b):lookup.setdefault((p['text_hash'],p['render_hash']),[]).append(j)
    for i,p in enumerate(a):
        candidates=lookup.get((p['text_hash'],p['render_hash']),[])
        if candidates:
            j=candidates.pop(0);pairs.append(dict(a=i+1,b=j+1,confidence=1.,ambiguous=False));free_a.remove(i);free_b.remove(j)
    ia=sorted(free_a);ib=sorted(free_b)
    if ia and ib:
        scores=np.array([[affinity(a[i],b[j]) for j in ib] for i in ia],dtype=np.float32)
        # Dummy assignments allow omissions instead of forcing unrelated pages together.
        augmented=np.full((len(ia),len(ib)+len(ia)),threshold,dtype=np.float32)
        augmented[:,:len(ib)]=scores
        rows,cols=linear_sum_assignment(-augmented)
        for x,y in zip(rows,cols):
            if y<len(ib) and scores[x,y]>=threshold:
                s=float(scores[x,y]);others=np.delete(scores[x],y)
                gap=s-float(others.max()) if len(others) else 1.
                i,j=ia[x],ib[y];pairs.append(dict(a=i+1,b=j+1,confidence=round(s,4),ambiguous=gap<.035));free_a.remove(i);free_b.remove(j)
    pairs.sort(key=lambda x:x['a'])
    # Pages shifted by insertions are not reordered. The longest increasing mapped subsequence stays in order.
    seq=[x['b'] for x in pairs];n=len(seq);length=[1]*n;previous=[-1]*n
    for i in range(n):
        for j in range(i):
            if seq[j]<seq[i] and length[j]+1>length[i]:length[i]=length[j]+1;previous[i]=j
    keep=set();i=max(range(n),key=lambda k:length[k]) if n else -1
    while i>=0:keep.add(i);i=previous[i]
    for i,p in enumerate(pairs):p['reordered']=i not in keep
    pairs.extend(dict(a=i+1,b=None,confidence=1.,ambiguous=False,reordered=False) for i in sorted(free_a))
    pairs.extend(dict(a=None,b=j+1,confidence=1.,ambiguous=False,reordered=False) for j in sorted(free_b))
    pairs.sort(key=lambda p:((p['a'] if p['a'] else p['b']) or 0,p['a'] is None))
    seen_a={};seen_b={}
    for p in pairs:
        for side,inv,seen in [('a',a,seen_a),('b',b,seen_b)]:
            if p[side]:
                fp=inv[p[side]-1];key=fp['text_hash']+fp['render_hash']
                p['duplicate_'+side]=seen.get(key)
                seen.setdefault(key,p[side])
    return pairs
