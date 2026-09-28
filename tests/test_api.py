import os
os.environ['START_WORKER']='0'
from fastapi.testclient import TestClient
from app.main import app
import fitz

def headers():return {'X-Sentinel-Client':'1'}

def test_stream_upload_offsets_and_validation():
    with TestClient(app) as c:
        with fitz.open() as d:d.new_page();data=d.tobytes()
        r=c.post('/api/uploads',json={'name':'../../safe.pdf','size':len(data)},headers=headers());assert r.status_code==200;id=r.json()['id']
        assert c.put('/api/uploads/'+id+'?offset=1',content=data,headers=headers()).status_code==409
        half=len(data)//2
        assert c.put('/api/uploads/'+id+'?offset=0',content=data[:half],headers=headers()).json()['offset']==half
        assert c.post('/api/uploads/'+id+'/complete',headers=headers()).status_code==409
        assert c.put(f'/api/uploads/{id}?offset={half}',content=data[half:],headers=headers()).status_code==200
        r=c.post('/api/uploads/'+id+'/complete',headers=headers());assert r.status_code==200;assert r.json()['name']=='safe.pdf'
        assert c.post('/api/uploads/'+id+'/complete',headers=headers()).json()['id']==r.json()['id']

def test_invalid_pdf_and_cross_origin():
    with TestClient(app) as c:
        assert c.post('/api/uploads',json={'name':'x.pdf','size':4}).status_code==403
        assert c.post('/api/uploads',json={'name':'x.pdf','size':4},headers={**headers(),'Origin':'https://untrusted.example'}).status_code==403
        id=c.post('/api/uploads',json={'name':'x.pdf','size':4},headers=headers()).json()['id']
        c.put(f'/api/uploads/{id}?offset=0',content=b'FAKE',headers=headers())
        assert c.post('/api/uploads/'+id+'/complete',headers=headers()).status_code==400

def test_auth_required(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main,'TOKEN','test-access')
    with TestClient(app) as c:
        assert c.get('/api/jobs').status_code==401
        assert c.post('/api/session',json={'token':'wrong'},headers=headers()).status_code==401
        assert c.post('/api/session',json={'token':'test-access'},headers=headers()).status_code==200
        assert c.get('/api/jobs').status_code==200

def test_render_limit_and_missing_job():
    with TestClient(app) as c:
        assert c.get('/api/jobs/not-a-job').status_code==404
        assert c.get('/api/documents/no/pages/1.png?dpi=9999').status_code==422
