import json, time, hashlib, concurrent.futures, traceback, os, resource
from pathlib import Path
from collections import Counter,defaultdict
from sqlalchemy import select,delete,func
from .config import ROOT, CONCURRENCY, ENGINE_VERSION, PAGE_TIMEOUT, BATCH_SIZE
from .db import jobs,documents,pages,differences,engine,one,update_job,log
from .util import isolated,write_json,read_json,lock
from .align import align_pages
from .compare import build_diff,DIMENSIONS

class Cancelled(Exception):pass

def ensure_active(job):
    state=one(jobs,job)
    if not state or state['cancel']:raise Cancelled()

def cache_dir(doc,options):
    from .ocr import available
    key=hashlib.sha256(json.dumps({'version':ENGINE_VERSION,'pymupdf':__import__('importlib.metadata',fromlist=['version']).version('pymupdf'),'ocr':options['ocr'],'ocr_ready':available(),'ocr_url':os.getenv('SURYA_INFERENCE_URL','')},sort_keys=True).encode()).hexdigest()[:16]
    return ROOT/'cache'/doc['sha256']/key

def document_path(id):return ROOT/'documents'/f'{id}.pdf'

def bounded_map(fn,items):
    # Executor.map pre-submits the finite page inventory; results are only small manifests, never bitmaps.
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        for result in pool.map(fn,items):yield result

def extract_document(doc,options,job,side):
    cache=cache_dir(doc,options);cache.mkdir(parents=True,exist_ok=True)
    count=doc['info']['pages'];update_job(job,stage=f'Extracting {side}',done=0,total=count)
    def work(start):
        end=min(count,start+BATCH_SIZE);ensure_active(job)
        with lock(cache/f'batch-{start}.lock'):
            if any(not (cache/f'{i}.json').exists() for i in range(start,end)):
                for attempt in range(2):
                    try:isolated(['extract-batch',document_path(doc['id']),start,end,cache,int(options['ocr'])],timeout=PAGE_TIMEOUT*(end-start));break
                    except Exception:
                        if attempt:raise
        return [(i,read_json(cache/f'{i}.json')['fingerprint']) for i in range(start,end)]
    inventory=[]
    for batch in bounded_map(work,range(0,count,BATCH_SIZE)):
        ensure_active(job)
        for i,fp in batch:inventory.append(fp)
        update_job(job,done=len(inventory))
    return cache,inventory

def store_page(job,idx,data):
    # Atomic replacement makes retries idempotent and prevents duplicate findings.
    with engine.begin() as c:
        c.execute(delete(differences).where(differences.c.job==job,differences.c.idx==idx));c.execute(delete(pages).where(pages.c.job==job,pages.c.idx==idx))
        c.execute(pages.insert().values(job=job,idx=idx,a=data['mapping']['a'],b=data['mapping']['b'],status=data.get('status','complete'),score=data.get('overall'),data={k:v for k,v in data.items() if k!='differences'}))
        for d in data.get('differences',[]):
            d['page_pair']=idx
            c.execute(differences.insert().values(id=f'{job}-{d["difference_id"]}',job=job,idx=idx,category=d['category'],severity=d['severity'],confidence=d['confidence'],search=json.dumps([d['reference_value'],d['candidate_value'],d['explanation']],ensure_ascii=False),data=d))

def doc_diffs(a,b,opts):
    out=[]
    for key in sorted(set(a['info']['metadata'])|set(b['info']['metadata'])):
        x,y=a['info']['metadata'].get(key),b['info']['metadata'].get(key)
        if x!=y:
            d=build_diff('METADATA_CHANGED',x,y,dimension='metadata',explanation=f'Metadata {key} changed.',property=key)
            if key in opts['ignore_metadata']:d['severity']='informational';d['no_score']=True
            out.append(d)
    for key in ('xml_metadata','custom_metadata'):
        x,y=a['info'].get(key),b['info'].get(key)
        if isinstance(x,dict):
            aliases={'/CreationDate':'creationDate','/ModDate':'modDate','/Producer':'producer','/Creator':'creator'}
            x={k:v for k,v in x.items() if aliases.get(k,k) not in opts['ignore_metadata'] and k not in ('/Title','/Author','/Subject','/Keywords','/Creator','/Producer','/CreationDate','/ModDate')}
            y={k:v for k,v in (y or {}).items() if aliases.get(k,k) not in opts['ignore_metadata'] and k not in ('/Title','/Author','/Subject','/Keywords','/Creator','/Producer','/CreationDate','/ModDate')}
        if x!=y:out.append(build_diff('METADATA_CHANGED',x,y,dimension='metadata',explanation=f'{key} changed.'))
    # Font presence/name/type/encoding/embedding are already compared on each page.
    # Here inspect program descriptors for fonts common to both inventories.
    all_a=a['info'].get('embedded_fonts',[]);all_b=b['info'].get('embedded_fonts',[])
    common={f['name'] for f in all_a}&{f['name'] for f in all_b}
    fa=[f for f in all_a if f['name'] in common];fb=[f for f in all_b if f['name'] in common]
    descriptors=lambda fs:[{k:v for k,v in f.items() if k not in ('program_sha256','program_bytes','subset','tables')} for f in fs]
    if descriptors(fa)!=descriptors(fb):out.append(build_diff('FONT_EMBEDDING_CHANGED',descriptors(fa),descriptors(fb),dimension='structure',explanation='Embedded font descriptors changed.'))
    elif fa!=fb:
        d=build_diff('FONT_PROGRAM_ENCODING_CHANGED',fa,fb,dimension='structure',explanation='Font subset/program encoding changed with equivalent inspected descriptors. Visual and text checks determine visible impact.');d['severity']='informational';d['no_score']=True;out.append(d)
    for key in ('outlines','layers','attachments','structure','pdf_version','permissions','encryption'):
        x,y=a['info'].get(key),b['info'].get(key)
        if key=='structure':
            # Widget values/defaults are primary FORM_CHANGED evidence on their pages.
            def without_values(v):
                if isinstance(v,dict):return {k:without_values(z) for k,z in v.items() if k not in ('/V','/DV')}
                if isinstance(v,list):return [without_values(z) for z in v]
                return v
            x=without_values(x);y=without_values(y)
        if x!=y:out.append(build_diff('STRUCTURE_CHANGED',x,y,dimension='structure',explanation=f'Document {key} changed.'))
    for i,d in enumerate(out):
        d.update(page_a=None,page_b=None,region='document',difference_id=f'document-{i:05}',score_impact=0.)
        d['severity']=opts['severity'].get(d['category'],d['severity'])
    return out

def summarize(job,doca,docb,opts,started):
    with engine.connect() as c:
        pp=list(c.execute(select(pages).where(pages.c.job==job,pages.c.idx>=0).order_by(pages.c.idx)).mappings())
        cats=dict(c.execute(select(differences.c.category,func.count()).where(differences.c.job==job).group_by(differences.c.category)).all())
        sevs=dict(c.execute(select(differences.c.severity,func.count()).where(differences.c.job==job).group_by(differences.c.severity)).all())
    totals={d:[] for d in DIMENSIONS};groups=defaultdict(list);warnings=set(doca['info'].get('warnings',[])+docb['info'].get('warnings',[]));failed=0
    for p in pp:
        data=p['data']
        if p['status']!='complete':failed+=1
        warnings.update(data.get('warnings',[]))
        for d,score in data.get('scores',{}).items():
            if score is not None:totals[d].append(score)
    from .db import iterate_diffs
    dimensions=Counter();n=0
    for d in iterate_diffs(job):
        n+=1;dimensions[d['dimension']]+=1
        if d.get('region') in ('header','footer'):
            # Group exact repeated edits; don't guess that differing amounts are one global change.
            key=json.dumps([d['region'],d['category'],d['reference_value'],d['candidate_value']],sort_keys=True,default=str)
            groups[key].append({'page_a':d['page_a'],'page_b':d['page_b'],'id':d['difference_id'],'page_pair':d['page_pair']})
    dd=doc_diffs(doca,docb,opts)
    meta_changes=sum(d['dimension']=='metadata' and not d.get('no_score') for d in dd)
    scores={d:sum(v)/len(v) if v else None for d,v in totals.items()}
    scores['metadata']=max(0,100*(1-meta_changes/max(1,len(set(doca['info']['metadata'])|set(docb['info']['metadata']))+2)))
    structural=sum(d['dimension']=='structure' and not d.get('no_score') for d in dd)
    if scores['structure'] is not None:scores['structure']=max(0,scores['structure']-min(100,structural*10))
    active={d:w for d,w in opts['weights'].items() if scores[d] is not None and w>0};den=sum(active.values())
    overall=sum(scores[d]*w for d,w in active.items())/den if den else None
    incomplete=failed>0 or any(any(term in w.lower() for term in ('not assessed','not fully assessed','ambiguous','unresolved','incomplete','failed','not inspected','not supported')) for w in warnings)
    per_page_coverage={d:dict(assessed=len(totals[d]),total=len(pp)) for d in DIMENSIONS if d!='metadata'}
    counts={p['idx']:0 for p in pp}
    with engine.connect() as c:
        counts.update(dict(c.execute(select(differences.c.idx,func.count()).where(differences.c.job==job,differences.c.idx>=0).group_by(differences.c.idx)).all()))
    summary=dict(overall=round(overall,4) if overall is not None else None,score_label='Measured match (incomplete coverage)' if incomplete else 'Overall match',incomplete=incomplete,
      scores={k:round(v,4) if v is not None else None for k,v in scores.items()},weights=opts['weights'],effective_weights={k:round(v/den,6) for k,v in active.items()} if den else {},
      formula='Sum(dimension score × active weight) / sum(active weights). N/A dimensions are excluded. Document dimension scores average applicable page pairs; page additions/removals score zero. Coverage is reported separately.',
      confidence_note='Confidence values express rule or OCR evidence strength, not empirically calibrated probabilities.',
      total_differences=n,categories=cats,severity=sevs,distribution=dict(dimensions),page_pairs=len(pp),matched_pages=sum(p['a'] is not None and p['b'] is not None for p in pp),
      changed_pages=sum(v>0 for v in counts.values()),failed_pages=failed,coverage=per_page_coverage,warnings=sorted(warnings),
      header_footer_groups=[dict(region=json.loads(k)[0],category=json.loads(k)[1],reference=json.loads(k)[2],candidate=json.loads(k)[3],occurrences=v) for k,v in groups.items() if len(v)>1],
      performance=dict(elapsed_seconds=round(time.monotonic()-started,3),page_pairs_per_second=round(len(pp)/max(.001,time.monotonic()-started),3),coordinator_peak_rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),child_peak_rss_mb=round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024,2),page_concurrency=CONCURRENCY),
      engine=ENGINE_VERSION,reference={k:v for k,v in doca.items() if k!='sha256'},candidate={k:v for k,v in docb.items() if k!='sha256'})
    # Attribute each weighted loss once across primary findings carrying that signal.
    signal_counts=Counter()
    for d in iterate_diffs(job):
        if not d.get('no_score'):
            for dim in set(d['signals']):signal_counts[dim]+=1
    with engine.begin() as c:
        for d in iterate_diffs(job):
            d['score_impact']=round(sum(summary['effective_weights'].get(dim,0)*(100-(scores[dim] or 0))/signal_counts[dim] for dim in set(d['signals']) if scores.get(dim) is not None and signal_counts[dim]) if not d.get('no_score') else 0,6)
            c.execute(differences.update().where(differences.c.id==f'{job}-{d["difference_id"]}').values(data=d))
    return summary

def run_job(job):
    started=time.monotonic();state=one(jobs,job)
    if not state:return
    folder=ROOT/'jobs'/job;folder.mkdir(parents=True,exist_ok=True)
    try:
        with lock(folder/'run.lock',blocking=False):
            try:
                ensure_active(job);update_job(job,status='running',stage='Inspecting',error=None)
                a,b=one(documents,state['a']),one(documents,state['b']);opts=state['options']
                ca,ia=extract_document(a,opts,job,'reference');cb,ib=extract_document(b,opts,job,'candidate')
                ensure_active(job);update_job(job,stage='Aligning pages',done=0)
                mappings=align_pages(ia,ib,opts['alignment_threshold'])
                checkpoint=dict(engine=ENGINE_VERSION,cache_a=str(ca),cache_b=str(cb),options=opts,mappings=mappings)
                checkpoint_file=folder/'checkpoint.json'
                if not checkpoint_file.exists() or read_json(checkpoint_file)!=checkpoint:
                    # An engine, OCR configuration, or alignment change invalidates page results.
                    with engine.begin() as c:
                        c.execute(delete(differences).where(differences.c.job==job))
                        c.execute(delete(pages).where(pages.c.job==job))
                    write_json(checkpoint_file,checkpoint)
                write_json(folder/'alignment.json',mappings)
                update_job(job,stage='Comparing text, visual, layout and objects',total=len(mappings),done=0)
                def compare_item(item):
                    idx,mapping=item;ensure_active(job)
                    with engine.connect() as c:
                        saved=c.execute(select(pages.c.status).where(pages.c.job==job,pages.c.idx==idx)).scalar()
                    if saved=='complete':return idx
                    pf=folder/'pages'/str(idx);pf.mkdir(parents=True,exist_ok=True)
                    spec=dict(cache_a=str(ca/f'{mapping["a"]-1}.json') if mapping['a'] else None,cache_b=str(cb/f'{mapping["b"]-1}.json') if mapping['b'] else None,path_a=str(document_path(a['id'])),path_b=str(document_path(b['id'])),mapping=mapping,options=opts,folder=str(pf))
                    write_json(pf/'input.json',spec)
                    for attempt in range(2):
                        try:
                            isolated(['compare',pf/'input.json',pf/'result.json'],timeout=PAGE_TIMEOUT*2)
                            data=read_json(pf/'result.json');store_page(job,idx,data);return idx
                        except Exception as e:
                            if attempt:
                                store_page(job,idx,dict(mapping=mapping,status='failed',overall=None,scores={},differences=[],warnings=[f'Pair {idx+1} failed: {str(e)[-500:]}']))
                    return idx
                for done,_ in enumerate(bounded_map(compare_item,enumerate(mappings)),1):ensure_active(job);update_job(job,done=done)
                dd=doc_diffs(a,b,opts);store_page(job,-1,dict(mapping={'a':None,'b':None},overall=None,differences=dd))
                update_job(job,stage='Scoring and correlating');summary=summarize(job,a,b,opts,started);write_json(folder/'summary.json',summary);update_job(job,summary=summary)
                ensure_active(job);update_job(job,stage='Generating reports')
                isolated(['exports',job],timeout=max(600,len(mappings)*10))
                from .storage import archive_job
                archive_job(job)
                update_job(job,status='partial' if summary['failed_pages'] else 'complete',stage='Complete',summary=summary,done=len(mappings));log('job_completed',job,{'differences':summary['total_differences']})
            except Cancelled:update_job(job,status='cancelled',stage='Cancelled')
            except Exception as e:update_job(job,status='failed',stage='Failed',error=str(e)[-2000:]);log('job_failed',job,{'type':type(e).__name__})
    except BlockingIOError:return
