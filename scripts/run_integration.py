import os,sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['START_WORKER']='0'
from fastapi.testclient import TestClient
from app.main import app
from app.pipeline import run_job
from app.db import jobs,one
with TestClient(app) as c:
    h={'X-Sentinel-Client':'1'}
    r=c.post('/api/demo',headers=h);assert r.status_code==200,r.text
    docs=r.json();r=c.post('/api/jobs',json={'reference':docs['reference']['id'],'candidate':docs['candidate']['id'],'options':{'ocr':False}},headers=h);assert r.status_code==200,r.text
    job=r.json()['id'];run_job(job);state=one(jobs,job)
    print(json.dumps({'id':job,'status':state['status'],'error':state['error'],'summary':state['summary']},indent=2),flush=True)
    Path('data/tmp/integration-job.txt').write_text(job)
    assert state['status']=='complete',state['error']
    for file in ['report.pdf','detailed-report.zip','result.json','differences.csv','comparison.xlsx','annotated-a.pdf','annotated-b.pdf']:
        r=c.get(f'/api/jobs/{job}/exports/{file}');assert r.status_code==200,(file,r.text);assert len(r.content)>20
    print('All seven exports downloaded successfully')
