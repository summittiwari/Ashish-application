"""Retention sweeps. Only terminal jobs and unreferenced documents can expire."""
import os,time,shutil,json
from sqlalchemy import select,delete
from .config import ROOT
from .db import engine,jobs,pages,differences,documents,uploads,audit,log
from .util import lock

def cleanup(days=None,apply=False):
    days=float(os.getenv('RETENTION_DAYS','30')) if days is None else days
    if days<=0:return {'enabled':False}
    cutoff=time.time()-days*86400
    result={'enabled':True,'apply':apply,'jobs':0,'documents':0,'uploads':0}
    # Run between local jobs, or externally while intake/workers are stopped for distributed deployments.
    with lock(ROOT/'maintenance.lock',blocking=False),lock(ROOT/'state.lock'),engine.begin() as c:
        expired=list(c.execute(select(jobs.c.id).where(jobs.c.updated<cutoff,jobs.c.status.in_(['complete','partial','failed','cancelled']))).scalars())
        result['jobs']=len(expired)
        if apply:
            for jid in expired:
                with lock(ROOT/'jobs'/jid/'run.lock',blocking=False):
                    for table in (differences,pages):c.execute(delete(table).where(table.c.job==jid))
                    c.execute(delete(jobs).where(jobs.c.id==jid))
                    shutil.rmtree(ROOT/'jobs'/jid,ignore_errors=True)
        keep_jobs=list(c.execute(select(jobs.c.a,jobs.c.b).where(~jobs.c.id.in_(expired))).all())
        refs={doc for pair in keep_jobs for doc in pair}
        stale=list(c.execute(select(documents).where(documents.c.created<cutoff)).mappings())
        for doc in stale:
            if doc['id'] in refs:continue
            result['documents']+=1
            if apply:
                (ROOT/'documents'/f'{doc["id"]}.pdf').unlink(missing_ok=True)
                c.execute(delete(documents).where(documents.c.id==doc['id']))
        if apply:
            live_hashes=set(c.execute(select(documents.c.sha256)).scalars())
            for folder in (ROOT/'cache').iterdir():
                if folder.is_dir() and folder.name not in live_hashes:shutil.rmtree(folder)
        for row in c.execute(select(uploads).where(uploads.c.created<cutoff)).mappings():
            result['uploads']+=1
            if apply:
                part=ROOT/'uploads'/f'{row["id"]}.part'
                try:
                    with lock(part.with_suffix('.lock'),blocking=False):
                        part.unlink(missing_ok=True);c.execute(delete(uploads).where(uploads.c.id==row['id']))
                except BlockingIOError:continue
        if apply:c.execute(delete(audit).where(audit.c.time<cutoff))
    if apply:log('retention_sweep','system',result)
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description='Preview retention; stop intake/workers before --apply in distributed mode.')
    p.add_argument('--days',type=float);p.add_argument('--apply',action='store_true');args=p.parse_args()
    print(json.dumps(cleanup(args.days,args.apply),indent=2))
