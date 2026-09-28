import os,re,time,json,hashlib,secrets,subprocess,sys,shutil,asyncio,hmac
from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
from urllib.parse import urlparse
from fastapi import FastAPI,Request,HTTPException,Query
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel,Field
from sqlalchemy import select,func,delete
from .config import ROOT,MAX_UPLOAD,CHUNK_SIZE,Options,PROFILES,DEFAULT_WEIGHTS
from .db import uploads,documents,jobs,pages,differences,engine,one,ident,log,update_job
from .util import isolated,write_json,read_json,digest_file,lock
from .pipeline import document_path

def state_guard(fn):
    from functools import wraps
    @wraps(fn)
    def guarded(*args,**kwargs):
        with lock(ROOT/'state.lock'):return fn(*args,**kwargs)
    return guarded

TOKEN=os.getenv('AUTH_TOKEN','')
@asynccontextmanager
async def lifespan(app):
    p=None
    if os.getenv('QUEUE_BACKEND','local')=='local' and os.getenv('START_WORKER','1')=='1':p=subprocess.Popen([sys.executable,'-m','app.worker'])
    yield
    if p:p.terminate();p.wait(timeout=10)
app=FastAPI(title='PDF Sentinel',version='1.1.0',lifespan=lifespan)

@app.middleware('http')
async def safety(request,call_next):
    api=request.url.path.startswith('/api/')
    if api and request.url.path not in ('/api/health','/api/session'):
        supplied=request.headers.get('authorization','').removeprefix('Bearer ') or request.cookies.get('sentinel_session','')
        if TOKEN and not hmac.compare_digest(supplied,TOKEN):return JSONResponse({'detail':'Sign in with the application access key.'},401)
    if api and request.method not in ('GET','HEAD','OPTIONS'):
        if request.headers.get('x-sentinel-client')!='1':return JSONResponse({'detail':'Required X-Sentinel-Client header missing.'},403)
        origin=request.headers.get('origin')
        if origin and urlparse(origin).netloc!=request.headers.get('host'):return JSONResponse({'detail':'Cross-origin writes are disabled.'},403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY';response.headers['Cache-Control']='no-store' if api else 'no-cache'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    return response

@app.get('/api/health')
def health():
    from .ocr import available
    return dict(status='ok',auth_required=bool(TOKEN),ocr_available=available(),max_upload=MAX_UPLOAD,chunk_size=CHUNK_SIZE,version='1.1.0')

class Session(BaseModel):token:str=Field(max_length=2048)
@app.post('/api/session')
def login(body:Session,request:Request):
    if TOKEN and not hmac.compare_digest(body.token,TOKEN):raise HTTPException(401,'Incorrect access key')
    r=JSONResponse({'ok':True});r.set_cookie('sentinel_session',body.token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=43200);return r
@app.delete('/api/session')
def logout():
    r=JSONResponse({'ok':True});r.delete_cookie('sentinel_session');return r

@app.get('/api/profiles')
def profiles():return dict(profiles=PROFILES,default_weights=DEFAULT_WEIGHTS)
class UploadCreate(BaseModel):
    name:str=Field(min_length=1,max_length=255)
    size:int=Field(gt=0)
@app.post('/api/uploads')
def create_upload(body:UploadCreate):
    if body.size>MAX_UPLOAD:raise HTTPException(413,f'File exceeds configured {MAX_UPLOAD} byte limit')
    if not body.name.lower().endswith('.pdf'):raise HTTPException(400,'Choose a PDF file')
    id=ident();name=Path(body.name.replace('\\','/')).name
    with engine.begin() as c:c.execute(uploads.insert().values(id=id,name=name,size=body.size,offset=0,created=time.time()))
    (ROOT/'uploads'/f'{id}.part').touch(mode=0o600);log('upload_created',id,{'size':body.size});return dict(id=id,offset=0,chunk_size=CHUNK_SIZE)

def required(table,id):
    row=one(table,id)
    if not row:raise HTTPException(404,'Not found')
    return row

@app.get('/api/uploads/{id}')
def get_upload(id:str):return required(uploads,id)
@contextmanager
def upload_guard(path):
    try:
        with lock(path,blocking=False):yield
    except BlockingIOError:raise HTTPException(409,'Upload is already receiving a chunk; retry after it finishes')

@app.put('/api/uploads/{id}')
async def upload_chunk(id:str,request:Request,offset:int=Query(ge=0)):
    row=required(uploads,id)
    if row['document_id']:raise HTTPException(409,'Upload already finalized')
    path=ROOT/'uploads'/f'{id}.part'
    # Holding the per-upload lock across a streamed request serializes retries for this file.
    with upload_guard(path.with_suffix('.lock')):
        row=required(uploads,id)
        if offset!=row['offset']:raise HTTPException(409,f'Expected offset {row["offset"]}')
        written=0
        with open(path,'r+b') as f:
            f.seek(offset)
            try:
                async for chunk in request.stream():
                    written+=len(chunk)
                    if written>CHUNK_SIZE or offset+written>row['size']:raise HTTPException(413,'Chunk exceeds limit or declared file size')
                    f.write(chunk)
                f.flush();os.fsync(f.fileno())
            except BaseException:f.truncate(offset);raise
        with engine.begin() as c:c.execute(uploads.update().where(uploads.c.id==id).values(offset=offset+written))
    return dict(id=id,offset=offset+written)

@app.post('/api/uploads/{id}/complete')
def complete_upload(id:str):
    row=required(uploads,id);path=ROOT/'uploads'/f'{id}.part'
    with lock(path.with_suffix('.lock')):
        row=required(uploads,id)
        if row['document_id']:return required(documents,row['document_id'])
        if row['offset']!=row['size']:raise HTTPException(409,'Upload is incomplete')
        with open(path,'rb') as f:
            if not f.read(1024).lstrip().startswith(b'%PDF-'):raise HTTPException(400,'Invalid PDF header')
        infofile=ROOT/'tmp'/f'{id}-inspection.json'
        try:
            isolated(['inspect',path,infofile],timeout=180)
            if infofile.stat().st_size>16*1024**2:raise ValueError('Document inspection exceeds the 16 MiB metadata budget')
            info=read_json(infofile)
        except Exception as e:raise HTTPException(422,f'PDF validation failed: {str(e)[-1000:]}')
        finally:infofile.unlink(missing_ok=True)
        sha=digest_file(path);docid=ident();dest=document_path(docid);os.replace(path,dest)
        record=dict(id=docid,name=row['name'],size=row['size'],sha256=sha,info=info,created=time.time())
        with engine.begin() as c:
            c.execute(documents.insert().values(**record));c.execute(uploads.update().where(uploads.c.id==id).values(document_id=docid))
        from .storage import archive_document
        archive_document(docid)
        log('upload_validated',docid,{'pages':info['pages']});return record

@app.get('/api/documents/{id}')
def document(id:str):return required(documents,id)
@app.get('/api/documents/{id}/pages/{page}.png')
def page_image(id:str,page:int,dpi:int=Query(default=120,ge=36,le=200)):
    doc=required(documents,id)
    if page<1 or page>doc['info']['pages']:raise HTTPException(404,'Page not found')
    target=ROOT/'cache'/doc['sha256']/f'render-{page}-{dpi}.png';target.parent.mkdir(parents=True,exist_ok=True)
    with lock(target.with_suffix('.lock')):
        if not target.exists():
            try:isolated(['render',document_path(id),page-1,target,dpi])
            except Exception as e:raise HTTPException(422,str(e)[-500:])
    return FileResponse(target,media_type='image/png')

class JobCreate(BaseModel):
    reference:str
    candidate:str
    options:dict=Field(default_factory=dict)
@app.post('/api/jobs')
@state_guard
def create_job(body:JobCreate):
    required(documents,body.reference);required(documents,body.candidate)
    try:opts=Options.from_input(body.options).model_dump()
    except Exception as e:raise HTTPException(422,str(e))
    id=ident();now=time.time()
    row=dict(id=id,a=body.reference,b=body.candidate,options=opts,status='queued',stage='Queued',done=0,total=0,created=now,updated=now,summary=None,error=None,cancel=0,generation=0)
    with engine.begin() as c:c.execute(jobs.insert().values(**row))
    enqueue(id);log('job_created',id);return row

def enqueue(id):
    if os.getenv('QUEUE_BACKEND','local')=='celery':
        from .queue import compare
        try:compare.delay(id)
        except Exception as e:update_job(id,status='failed',error='Queue unavailable. Resume after restoring Redis.');raise HTTPException(503,'Queue unavailable')

@app.get('/api/jobs')
def list_jobs(limit:int=Query(30,ge=1,le=100)):
    with engine.connect() as c:
        rows=[dict(r) for r in c.execute(select(jobs).order_by(jobs.c.created.desc()).limit(limit)).mappings()]
    for r in rows:
        a,b=one(documents,r['a']),one(documents,r['b']);r['reference_name']=a['name'] if a else '';r['candidate_name']=b['name'] if b else ''
        r['summary']={k:r['summary'].get(k) for k in ('overall','total_differences','incomplete')} if r['summary'] else None
    return rows
@app.get('/api/jobs/{id}')
def job(id:str):return required(jobs,id)
@app.post('/api/jobs/{id}/cancel')
def cancel(id:str):
    row=required(jobs,id)
    if row['status'] in ('queued','running'):update_job(id,cancel=1,status='cancelled' if row['status']=='queued' else row['status'])
    log('job_cancel_requested',id);return {'ok':True}
@app.post('/api/jobs/{id}/resume')
@state_guard
def resume(id:str):
    row=required(jobs,id)
    if row['status'] in ('running','queued'):raise HTTPException(409,'Job is already active')
    update_job(id,cancel=0,status='queued',stage='Resuming',error=None,generation=row['generation']+1);enqueue(id);log('job_resumed',id);return {'ok':True}
@app.get('/api/jobs/{id}/pages')
def job_pages(id:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200),sort:str='page'):
    required(jobs,id)
    with engine.connect() as c:
        rows=c.execute(select(pages).where(pages.c.job==id,pages.c.idx>=0).order_by(pages.c.score if sort=='score' else pages.c.idx).offset(offset).limit(limit)).mappings()
        return [dict(r) for r in rows]
@app.get('/api/jobs/{id}/differences')
def job_diffs(id:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200),category:str='',severity:str='',q:str='',page_pair:int|None=None,min_confidence:float=Query(0,ge=0,le=1)):
    required(jobs,id);conditions=[differences.c.job==id,differences.c.confidence>=min_confidence]
    if category:conditions.append(differences.c.category==category)
    if severity:conditions.append(differences.c.severity==severity)
    if q:conditions.append(differences.c.search.ilike('%'+q.replace('%','\\%').replace('_','\\_')+'%',escape='\\'))
    if page_pair is not None:conditions.append(differences.c.idx==page_pair)
    with engine.connect() as c:
        total=c.execute(select(func.count()).select_from(differences).where(*conditions)).scalar()
        result=[r[0] for r in c.execute(select(differences.c.data).where(*conditions).order_by(differences.c.idx,differences.c.id).offset(offset).limit(limit))]
    return {'total':total,'items':result}
@app.get('/api/jobs/{id}/visual/{pair}/{mode}.png')
def visual(id:str,pair:int,mode:str):
    required(jobs,id)
    if mode not in ('mask','heatmap') or pair<0:raise HTTPException(404)
    path=ROOT/'jobs'/id/'pages'/str(pair)/f'{mode}.png'
    if not path.exists():raise HTTPException(404,'Visual artifact unavailable')
    return FileResponse(path,media_type='image/png')
@app.get('/api/jobs/{id}/exports/{name}')
def exports(id:str,name:str):
    row=required(jobs,id)
    if name not in ('report.pdf','detailed-report.zip','result.json','differences.csv','comparison.xlsx','annotated-a.pdf','annotated-b.pdf'):raise HTTPException(404)
    if row['status'] not in ('complete','partial'):raise HTTPException(409,'Exports are available after processing finishes')
    path=ROOT/'jobs'/id/'exports'/name
    if not path.is_file():raise HTTPException(404,'Export unavailable')
    return FileResponse(path,filename=f'{id[:8]}-{name}')
@app.get('/api/audit')
def audit_log(limit:int=Query(100,ge=1,le=500)):
    from .db import audit
    with engine.connect() as c:return [dict(r) for r in c.execute(select(audit).order_by(audit.c.time.desc()).limit(limit)).mappings()]

STATIC=Path(__file__).parent/'static'
app.mount('/static',StaticFiles(directory=STATIC),name='static')
@app.get('/')
def index():return FileResponse(STATIC/'index.html')

@app.post('/api/demo')
def demo():
    result={}
    for side,name in [('reference','reference.pdf'),('candidate','candidate.pdf')]:
        src=Path(__file__).parent.parent/'examples'/name
        if not src.exists():raise HTTPException(404,'Run python scripts/make_examples.py to generate sample PDFs')
        id=ident();dest=document_path(id);shutil.copyfile(src,dest);infofile=ROOT/'tmp'/f'{id}.json'
        isolated(['inspect',dest,infofile]);info=read_json(infofile);infofile.unlink()
        row=dict(id=id,name='Example — '+name,size=dest.stat().st_size,sha256=digest_file(dest),info=info,created=time.time())
        with engine.begin() as c:c.execute(documents.insert().values(**row))
        result[side]=row
    return result
