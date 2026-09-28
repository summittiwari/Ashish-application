"""Durable local queue. PostgreSQL/Redis deployments use the same pipeline via Celery."""
import os,time,subprocess,sys,signal
from sqlalchemy import select
from .db import jobs,engine,update_job,one
from .config import JOB_TIMEOUT,ROOT
from .util import lock

def execute(job):
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    process=subprocess.Popen([sys.executable,'-m','app.task','run',job],env=env,start_new_session=True)
    started=time.monotonic()
    try:
        while process.poll() is None:
            state=one(jobs,job)
            if not state or state['cancel'] or time.monotonic()-started>JOB_TIMEOUT:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                update_job(job,status='cancelled' if state and state['cancel'] else 'failed',stage='Stopped',error=None if state and state['cancel'] else 'Job time limit exceeded; completed pages retained for resume.')
                return
            time.sleep(.4)
        if process.returncode and one(jobs,job)['status']=='running':update_job(job,status='failed',error='Worker exited unexpectedly. Resume retries unfinished pages.')
    except BaseException:
        if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
        raise

def main():
    def stop(*_):raise SystemExit()
    signal.signal(signal.SIGTERM,stop)
    # Only the process holding the queue lock recovers running jobs, avoiding races on API restarts.
    with lock(ROOT/'worker.lock'):
        with engine.begin() as c:c.execute(jobs.update().where(jobs.c.status=='running').values(status='queued',stage='Recovering'))
        last_cleanup=0
        while True:
            with engine.connect() as c:job=c.execute(select(jobs.c.id).where(jobs.c.status=='queued').order_by(jobs.c.created).limit(1)).scalar()
            if job:execute(job)
            else:
                if time.monotonic()-last_cleanup>3600:
                    from .maintenance import cleanup
                    try:cleanup(apply=True)
                    except Exception:
                        from .db import log
                        log('retention_failed','system')
                    last_cleanup=time.monotonic()
                time.sleep(.5)
if __name__=='__main__':main()
