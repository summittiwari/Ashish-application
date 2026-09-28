from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, Float, Text, JSON, select, event, Index
from contextlib import contextmanager
import time, uuid
from .config import DATABASE_URL
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread':False,'timeout':30} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def pragma(conn, _):
        conn.execute('PRAGMA journal_mode=WAL'); conn.execute('PRAGMA busy_timeout=30000')
meta=MetaData()
uploads=Table('uploads',meta,Column('id',String,primary_key=True),Column('name',Text),Column('size',Integer),Column('offset',Integer),Column('created',Float),Column('document_id',String))
documents=Table('documents',meta,Column('id',String,primary_key=True),Column('name',Text),Column('size',Integer),Column('sha256',String,index=True),Column('info',JSON),Column('created',Float))
jobs=Table('jobs',meta,Column('id',String,primary_key=True),Column('a',String),Column('b',String),Column('options',JSON),Column('status',String,index=True),Column('stage',String),Column('done',Integer),Column('total',Integer),Column('created',Float),Column('updated',Float),Column('summary',JSON),Column('error',Text),Column('cancel',Integer,default=0),Column('generation',Integer,default=0))
pages=Table('pages',meta,Column('job',String,primary_key=True),Column('idx',Integer,primary_key=True),Column('a',Integer),Column('b',Integer),Column('status',String),Column('score',Float),Column('data',JSON))
differences=Table('differences',meta,Column('id',String,primary_key=True),Column('job',String,index=True),Column('idx',Integer),Column('category',String),Column('severity',String),Column('confidence',Float),Column('search',Text),Column('data',JSON))
Index('ix_diff_job_idx',differences.c.job,differences.c.idx)
audit=Table('audit',meta,Column('id',String,primary_key=True),Column('time',Float),Column('action',String),Column('target',String),Column('detail',JSON))
meta.create_all(engine)
def ident(): return uuid.uuid4().hex

def one(table,id):
    with engine.connect() as c:
        r=c.execute(select(table).where(table.c.id==id)).mappings().first()
        return dict(r) if r else None

def update_job(id, **values):
    values['updated']=time.time()
    with engine.begin() as c:c.execute(jobs.update().where(jobs.c.id==id).values(**values))

def log(action,target,detail=None):
    with engine.begin() as c:c.execute(audit.insert().values(id=ident(),time=time.time(),action=action,target=target,detail=detail or {}))

def iterate_diffs(job, batch=200):
    offset=0
    while True:
        with engine.connect() as c:
            rows=c.execute(select(differences.c.data).where(differences.c.job==job).order_by(differences.c.idx,differences.c.id).offset(offset).limit(batch)).all()
        if not rows: break
        for r in rows:yield r[0]
        offset+=len(rows)
