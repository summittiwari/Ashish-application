"""Opt-in reproducible capacity tests. Simple synthetic PDFs are not a general capacity guarantee."""
import sys,os,time,json,resource,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ['START_WORKER']='0'
import fitz
from app.main import app
from app.pipeline import run_job
from app.db import jobs,one
from fastapi.testclient import TestClient
parser=argparse.ArgumentParser();parser.add_argument('--pages',type=int,default=500);parser.add_argument('--large-file-bytes',type=int,default=0);args=parser.parse_args()
out=Path('data/benchmarks');out.mkdir(parents=True,exist_ok=True)
def make_pages(path,n,changed=False):
    with fitz.open() as d:
        for i in range(n):
            p=d.new_page(width=400,height=300);p.insert_text((40,70),f'Controlled benchmark page {i+1:04}',fontsize=15);p.insert_text((40,110),f'Reference amount: {450 if changed and i==n//2 else 300}',fontsize=11)
        d.save(path)
def make_large(path,size):
    # A valid PDF with one large unreferenced binary stream; no unbounded decoded images.
    with open(path,'wb') as f:
        f.write(b'%PDF-1.7\n');offsets=[0]
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 300] /Resources << >> >>']
        for i,obj in enumerate(objects,1):offsets.append(f.tell());f.write(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
        offsets.append(f.tell());length=size-f.tell()-400;f.write(f'4 0 obj\n<< /Length {length} >>\nstream\n'.encode());f.seek(length,1);f.write(b'\nendstream\nendobj\n');xref=f.tell();f.write(b'xref\n0 5\n0000000000 65535 f \n')
        for off in offsets[1:]:f.write(f'{off:010} 00000 n \n'.encode())
        f.write(f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())

def upload(client,path):
    h={'X-Sentinel-Client':'1'}
    u=client.post('/api/uploads',json={'name':path.name,'size':path.stat().st_size},headers=h).json();id=u['id'];offset=0
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(8*1024**2),b''):
            r=client.put(f'/api/uploads/{id}?offset={offset}',content=chunk,headers=h);assert r.status_code==200,r.text;offset=r.json()['offset']
    r=client.post(f'/api/uploads/{id}/complete',headers=h);assert r.status_code==200,r.text;return r.json()
started=time.monotonic()
with TestClient(app) as client:
    if args.large_file_bytes:
        path=out/'large-stream.pdf';make_large(path,args.large_file_bytes);doc=upload(client,path);record={'scenario':'large inert binary stream upload and inspection','bytes':path.stat().st_size,'pages':doc['info']['pages'],'seconds':time.monotonic()-started,'test_process_peak_rss_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'limitation':'Not an image-heavy stress test; large decoded images and complex pages require separate capacity validation.'}
    else:
        pa,pb=out/f'{args.pages}-reference.pdf',out/f'{args.pages}-candidate.pdf';make_pages(pa,args.pages);make_pages(pb,args.pages,True);a,b=upload(client,pa),upload(client,pb);r=client.post('/api/jobs',headers={'X-Sentinel-Client':'1'},json={'reference':a['id'],'candidate':b['id'],'options':{'dpi':72,'ocr':False}});assert r.status_code==200,r.text
        id=r.json()['id'];run_job(id);j=one(jobs,id);assert j['status']=='complete',j['error'];s=j['summary'];assert s['page_pairs']==args.pages and s['failed_pages']==0
        record={'scenario':'native synthetic page benchmark','pages_per_pdf':args.pages,'job':id,'seconds_including_reports':time.monotonic()-started,'summary':s,'bytes':[pa.stat().st_size,pb.stat().st_size],'limitation':'Sparse native pages at 72 DPI; not representative of scanned or image-heavy PDFs.'}
Path(f'docs/benchmark-{args.large_file_bytes or args.pages}.json').write_text(json.dumps(record,indent=2));print(json.dumps({k:v for k,v in record.items() if k!='summary'},indent=2),flush=True)
