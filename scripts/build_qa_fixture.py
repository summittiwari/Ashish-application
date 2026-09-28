import sys,json,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import one,jobs,pages,engine,iterate_diffs
from app.config import ROOT,PROFILES,DEFAULT_WEIGHTS
from app.pipeline import document_path
from app.extract import render
from sqlalchemy import select
import fitz
job=Path('data/tmp/integration-job.txt').read_text().strip();state=one(jobs,job);assert state['status']=='complete'
qa=Path('docs/qa');qa.mkdir(parents=True,exist_ok=True)
with engine.connect() as c:page_rows=[dict(x) for x in c.execute(select(pages).where(pages.c.job==job,pages.c.idx>=0).order_by(pages.c.idx)).mappings()]
fixture=dict(job=state,pages=page_rows,differences=list(iterate_diffs(job)),profiles={'profiles':PROFILES,'default_weights':DEFAULT_WEIGHTS})
(qa/'fixture.json').write_text(json.dumps(fixture))
for side,key in [('a','reference'),('b','candidate')]:
    doc=state['summary'][key]
    with fitz.open(document_path(doc['id'])) as d:
        for index,p in enumerate(d):
            im,_=render(p,120);im.save(qa/f'{doc["id"]}-{index+1}.png')
for p in page_rows:
    for name in ('mask','heatmap'):
        src=ROOT/'jobs'/job/'pages'/str(p['idx'])/f'{name}.png'
        if src.exists():shutil.copyfile(src,qa/f'{p["idx"]}-{name}.png')
print(job)
