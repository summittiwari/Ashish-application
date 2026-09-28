import hashlib, json, os, tempfile, fcntl, subprocess, sys
from pathlib import Path
from contextlib import contextmanager
from .config import ROOT, PAGE_TIMEOUT, MEMORY_MB

def digest_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()

def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f,ensure_ascii=False,allow_nan=False,default=str)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def read_json(path):
    with open(path) as f:return json.load(f)

@contextmanager
def lock(path, blocking=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a') as f:
        fcntl.flock(f,fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)

def isolated(args, timeout=PAGE_TIMEOUT):
    # No shell; parsing/rendering runs outside the API and has a hard deadline.
    env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    r=subprocess.run([sys.executable,'-m','app.task',*map(str,args)],env=env,capture_output=True,text=True,timeout=timeout)
    if r.returncode:raise RuntimeError((r.stderr or r.stdout)[-2000:] or f'Worker exited {r.returncode}')

def rect_union(boxes):
    bs=[b for b in boxes if b]
    return [min(b[0] for b in bs),min(b[1] for b in bs),max(b[2] for b in bs),max(b[3] for b in bs)] if bs else None

def overlap(a,b):
    if not a or not b:return 0.
    inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return inter/max(1,min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1])))

def bbox_delta(a,b): return max(abs(x-y) for x,y in zip(a,b))
def safe_cell(value):
    s=str(value if value is not None else '')
    return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
