import time
from sqlalchemy import delete
from app.db import engine,jobs,documents,pages,differences,uploads,ident
from app.config import ROOT
from app.maintenance import cleanup

def test_retention_preserves_active_job_documents():
    old=time.time()-86400*60;keep,remove=ident(),ident();jid=ident()
    for did in (keep,remove):(ROOT/'documents'/f'{did}.pdf').write_bytes(b'test')
    with engine.begin() as c:
        for did in (keep,remove):c.execute(documents.insert().values(id=did,name='test.pdf',created=old,sha256=did))
        c.execute(jobs.insert().values(id=jid,a=keep,b=keep,status='running',created=old,updated=old))
    try:
        preview=cleanup(days=30);assert preview['documents']>=1
        assert (ROOT/'documents'/f'{remove}.pdf').exists()
        cleanup(days=30,apply=True)
        assert (ROOT/'documents'/f'{keep}.pdf').exists()
        assert not (ROOT/'documents'/f'{remove}.pdf').exists()
    finally:
        with engine.begin() as c:
            c.execute(delete(jobs).where(jobs.c.id==jid));c.execute(delete(documents).where(documents.c.id.in_([keep,remove])))
        (ROOT/'documents'/f'{keep}.pdf').unlink(missing_ok=True)

def test_archive_is_optional(monkeypatch):
    from app.storage import archive_document
    monkeypatch.delenv('S3_BUCKET',raising=False)
    assert archive_document('absent') is False
