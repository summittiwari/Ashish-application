"""Exercise the real HTTP server, durable queue, report downloads, cancel and resume."""
import sys,os,time,json,subprocess,socket,signal,tempfile
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
env=os.environ.copy();env.update(SENTINEL_DATA=str(root/'data/live-test'),START_WORKER='1',RETENTION_DAYS='0',AUTH_TOKEN='integration-only-access-key',PAGE_CONCURRENCY='1')
log=open(root/'data/tmp/live-api.log','w')
server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=log,stderr=log,start_new_session=True)
started=time.monotonic();evidence={}
try:
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=60,trust_env=False) as c:
        for _ in range(100):
            try:
                if c.get('/api/health').status_code==200:break
            except httpx.ConnectError:pass
            time.sleep(.1)
        else:raise RuntimeError('Server did not become healthy')
        assert c.get('/api/jobs').status_code==401
        c.headers.update({'X-Sentinel-Client':'1'})
        assert c.post('/api/session',json={'token':'integration-only-access-key'}).status_code==200
        docs=c.post('/api/demo').json()
        job=c.post('/api/jobs',json={'reference':docs['reference']['id'],'candidate':docs['candidate']['id'],'options':{'ocr':False,'dpi':72}}).json()['id']
        def wait_job():
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                state=c.get(f'/api/jobs/{job}').json()
                if state['status'] in ('complete','partial','failed','cancelled'):return state
                time.sleep(.2)
            raise RuntimeError('Queue deadline exceeded')
        state=wait_job();assert state['status']=='complete',state
        evidence['comparison_status']=state['status'];evidence['findings']=state['summary']['total_differences']
        evidence['exports']={}
        for name in ('report.pdf','detailed-report.zip','result.json','differences.csv','comparison.xlsx','annotated-a.pdf','annotated-b.pdf'):
            r=c.get(f'/api/jobs/{job}/exports/{name}');assert r.status_code==200 and len(r.content)>50
            evidence['exports'][name]=len(r.content)
        base=root/'data/live-test/jobs'/job
        before={p:p.stat().st_mtime_ns for p in base.glob('pages/*/result.json')}
        assert c.post(f'/api/jobs/{job}/resume').status_code==200
        state=wait_job();assert state['status']=='complete'
        assert all(p.stat().st_mtime_ns==stamp for p,stamp in before.items())
        evidence['completed_page_checkpoints_reused']=len(before)
        job=c.post('/api/jobs',json={'reference':docs['reference']['id'],'candidate':docs['candidate']['id'],'options':{'ocr':False,'dpi':300}}).json()['id']
        assert c.post(f'/api/jobs/{job}/cancel').status_code==200
        state=wait_job();assert state['status']=='cancelled',state
        evidence['cancellation_status']=state['status']
        assert c.post(f'/api/jobs/{job}/resume').status_code==200
        assert wait_job()['status']=='complete'
        evidence['resume_after_cancel']='complete'
        assert c.get('/api/audit').json()
        evidence['authenticated_cookie_session']=True
        evidence['seconds']=round(time.monotonic()-started,2)
        (root/'docs/live-api-validation.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence,indent=2))
finally:
    server.terminate()
    try:server.wait(timeout=15)
    except subprocess.TimeoutExpired:os.killpg(server.pid,signal.SIGKILL);server.wait()
    log.close()
