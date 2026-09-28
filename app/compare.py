import difflib, re, hashlib, json, math
from collections import Counter
from pathlib import Path
import fitz
from rapidfuzz.fuzz import ratio
from .util import rect_union, overlap, bbox_delta, write_json, read_json
from .semantic import compare_semantics
from .visual import compare_visual
from .config import Options

DIMENSIONS=('text','semantic','visual','layout','typography','images','logos','tables','structure','forms','metadata')
SEVERITY={'NUMERIC_CHANGE':'critical','POLARITY_CHANGE':'critical','OBLIGATION_CHANGE':'critical','PAGE_REMOVED':'critical','PAGE_ADDED':'major','TEXT_REMOVED':'major','TEXT_ADDED':'major','TEXT_MODIFIED':'major','TABLE_CELL_CHANGED':'critical','TABLE_STRUCTURE_CHANGED':'major','LOGO_MISSING':'critical','LOGO_CHANGED':'major','IMAGE_CHANGED':'major','IMAGE_REMOVED':'major','OCR_UNCERTAINTY':'informational'}

def build_diff(category,old=None,new=None,ba=None,bb=None,dimension='text',confidence=1.,explanation=None,**extra):
    return dict(category=category,subcategory=extra.pop('subcategory',None),severity=SEVERITY.get(category,'minor'),confidence=round(confidence,4),confidence_kind='rule evidence, not calibrated probability',reference_value=old,candidate_value=new,reference_bbox=ba,candidate_bbox=bb,explanation=explanation or category.replace('_',' ').capitalize(),dimension=dimension,signals=[dimension],score_impact=0.,**extra)

def align_elements(a,b):
    free=set(range(len(b)));pairs=[];unmatched=[]
    bytext={}
    for j,l in enumerate(b):bytext.setdefault(l['text'],[]).append(j)
    for i,l in enumerate(a):
        exact=[j for j in bytext.get(l['text'],[]) if j in free]
        if exact:
            j=min(exact,key=lambda j:bbox_delta(l['bbox'],b[j]['bbox']));free.remove(j);pairs.append((i,j));continue
        unmatched.append(i)
    for i in unmatched:
        choices=[]
        for j in free:
            text=ratio(a[i]['text'],b[j]['text'])/100
            distance=bbox_delta(a[i]['bbox'],b[j]['bbox'])
            score=.78*text+.22*max(0,1-distance/150)
            if text>=.25 or distance<5:choices.append((score,j))
        if choices:
            score,j=max(choices)
            if score>=.40:free.remove(j);pairs.append((i,j));continue
        pairs.append((i,None))
    pairs.extend((None,j) for j in sorted(free));return pairs

def text_edits(old,new):
    # Word-token alignment keeps several character edits within one number/word together.
    aa=list(re.finditer(r'\s+|\S+',old));bb=list(re.finditer(r'\s+|\S+',new))
    tokens_a=[m[0] for m in aa];tokens_b=[m[0] for m in bb]
    for tag,ai,aj,bi,bj in difflib.SequenceMatcher(None,tokens_a,tokens_b,autojunk=False).get_opcodes():
        if tag=='equal':continue
        i1=aa[ai].start() if ai<len(aa) else len(old);i2=aa[aj-1].end() if aj>ai else i1
        j1=bb[bi].start() if bi<len(bb) else len(new);j2=bb[bj-1].end() if bj>bi else j1
        if tag=='replace' and aj-ai==bj-bi==1 and not re.search(r'\d',old[i1:i2]+new[j1:j2]):
            while i1<i2 and j1<j2 and old[i1]==new[j1]:i1+=1;j1+=1
            while i2>i1 and j2>j1 and old[i2-1]==new[j2-1]:i2-=1;j2-=1
        yield tag,i1,i2,j1,j2

def span_box(line,start,end):
    chars=line.get('chars',[])
    if chars and end>start:return rect_union(c['bbox'] for c in chars[start:end])
    return line['bbox']

def style_diffs(a,b,tolerance,color_tolerance):
    sa=a.get('spans',[]);sb=b.get('spans',[]);diffs=[]
    for i,j in align_elements(sa,sb):
        if i is None or j is None:continue
        x,y=sa[i],sb[j]
        old,new=x['style'],y['style']
        for prop,category in [('font','FONT_CHANGE'),('size','FONT_SIZE_CHANGE'),('flags','FONT_STYLE_CHANGE'),('color','COLOR_CHANGE'),('alpha','TEXT_OPACITY_CHANGE'),('rotation','TEXT_ROTATION_CHANGE'),('wmode','WRITING_DIRECTION_CHANGE'),('underline','UNDERLINE_CHANGE'),('strike_through','STRIKE_THROUGH_CHANGE')]:
            ov,nv=old.get(prop),new.get(prop)
            if ov==nv:continue
            if prop=='size' and abs((ov or 0)-(nv or 0))<=.01:continue
            if prop=='color':
                rgb=lambda c:tuple(((c or 0)>>s)&255 for s in (16,8,0))
                if max(abs(u-v) for u,v in zip(rgb(ov),rgb(nv)))<=color_tolerance:continue
                ov=f'#{ov:06x}';nv=f'#{nv:06x}'
            diffs.append(build_diff(category,ov,nv,x['bbox'],y['bbox'],'typography',explanation=f'{prop}: {ov} → {nv}',property=prop))
        if x['text']==y['text'] and old.get('font')==new.get('font') and old.get('size')==new.get('size'):
            aa,ab=x.get('advances',[]),y.get('advances',[])
            if len(aa)==len(ab) and aa:
                for spaces,category in [(False,'CHARACTER_SPACING_CHANGE'),(True,'WORD_SPACING_CHANGE')]:
                    indices=[k for k in range(min(len(aa),len(x['text']))) if x['text'][k].isspace()==spaces]
                    if any(abs(aa[k]-ab[k])>max(.05,tolerance) for k in indices):
                        diffs.append(build_diff(category,[aa[k] for k in indices],[ab[k] for k in indices],x['bbox'],y['bbox'],'typography',explanation='Measured glyph advances changed with unchanged text, font and size.'))
    return diffs

def generic_pairs(a,b,key):
    used=set();pairs=[]
    for x in a:
        matches=[(j,y) for j,y in enumerate(b) if j not in used and x.get(key)==y.get(key)]
        if not matches:matches=[(j,y) for j,y in enumerate(b) if j not in used]
        if matches:
            j,y=min(matches,key=lambda v:bbox_delta(x.get('bbox') or [0]*4,v[1].get('bbox') or [0]*4));used.add(j);pairs.append((x,y))
        else:pairs.append((x,None))
    pairs.extend((None,y) for j,y in enumerate(b) if j not in used);return pairs

def compare_page(a,b,path_a,path_b,mapping,options,folder):
    opts=Options(**options);diffs=[];scores={d:None for d in DIMENSIONS};notes=[]
    if a is None or b is None:
        p=a or b;category='PAGE_REMOVED' if b is None else 'PAGE_ADDED'
        diffs=[build_diff(category,f'Page {mapping["a"]}' if a else None,f'Page {mapping["b"]}' if b else None,[0,0,p['width'],p['height']] if a else None,[0,0,p['width'],p['height']] if b else None,'structure')]
        scores.update({k:0 for k in ('text','visual','layout','structure')})
        return finish(diffs,scores,mapping,opts,notes,a,b)
    lines_a,lines_b=a['lines'],b['lines'];pairs=align_elements(lines_a,lines_b)
    assessed=a['text_assessed'] and b['text_assessed']
    native=any(l['source']=='native' for l in lines_a+lines_b)
    text_a=a['text'];text_b=b['text']
    eq_a=re.sub(r'\s+',' ',text_a).strip() if opts.ignore_whitespace else text_a
    eq_b=re.sub(r'\s+',' ',text_b).strip() if opts.ignore_whitespace else text_b
    if assessed:scores['text']=round(ratio(eq_a,eq_b),5) if eq_a or eq_b else None
    semantic=[];ocr_uncertain=False
    for i,j in pairs:
        x=lines_a[i] if i is not None else None;y=lines_b[j] if j is not None else None
        if x is None or y is None:
            # Text missing on an unassessed scan is unknown, not a deletion.
            if not assessed:continue
            category='TEXT_REMOVED' if y is None else 'TEXT_ADDED'
            confidence=(x or y)['confidence']
            diffs.append(build_diff(category,x['text'] if x else None,y['text'] if y else None,x['bbox'] if x else None,y['bbox'] if y else None,'text',confidence))
            semantic.append(0.);continue
        old,new=x['text'],y['text']
        ocr_pair=x['source']=='ocr' or y['source']=='ocr'
        if ocr_pair and min(x['confidence'],y['confidence'])<opts.ocr_confidence:ocr_uncertain=True
        sem=compare_semantics(old,new);semantic.append(sem['similarity'])
        if old!=new:
            for tag,i1,i2,j1,j2 in text_edits(old,new):
                if tag=='equal':continue
                ov,nv=old[i1:i2],new[j1:j2]
                if opts.ignore_whitespace and not (ov+nv).strip():continue
                category='TEXT_ADDED' if tag=='insert' else 'TEXT_REMOVED' if tag=='delete' else 'TEXT_MODIFIED'
                if not (ov+nv).strip():category='WHITESPACE_CHANGE'
                elif sem['kind'] in ('NUMERIC_CHANGE','POLARITY_CHANGE','OBLIGATION_CHANGE'):category=sem['kind']
                confidence=min(x['confidence'],y['confidence'])
                if (x['source']=='ocr' or y['source']=='ocr') and confidence<opts.ocr_confidence:category='OCR_UNCERTAINTY'
                d=build_diff(category,ov,nv,span_box(x,i1,i2),span_box(y,j1,j2),'text',confidence,explanation=f'{old} → {new}',semantic=sem,context={'reference':old,'candidate':new},ocr_evidence=ocr_pair)
                if category=='OCR_UNCERTAINTY':d['no_score']=True
                d['signals'].append('semantic');diffs.append(d)
        if native and x['source']==y['source']=='native':diffs.extend(style_diffs(x,y,opts.position_tolerance,opts.color_tolerance))
        if old==new and bbox_delta(x['bbox'],y['bbox'])>opts.position_tolerance:
            dx=y['bbox'][0]-x['bbox'][0];dy=y['bbox'][1]-x['bbox'][1]
            diffs.append(build_diff('POSITION_CHANGE',x['bbox'],y['bbox'],x['bbox'],y['bbox'],'layout',explanation=f'Element moved {dx:.2f} pt horizontally and {dy:.2f} pt vertically; width/height may also differ.'))
    if assessed and semantic and all(s is not None for s in semantic):scores['semantic']=sum(semantic)/len(semantic)*100
    elif any(s is None for s in semantic):notes.append('General paraphrase equivalence is unresolved. Semantic score is unavailable when deterministic rules cannot decide.')
    if not assessed:notes.append('Scanned/hybrid text is not fully assessed; text and semantic scores are unavailable.')
    if text_a!=text_b and re.sub(r'\s+',' ',text_a).strip()==re.sub(r'\s+',' ',text_b).strip() and len(lines_a)!=len(lines_b):
        diffs=[d for d in diffs if d['dimension']!='text']
        diffs.append(build_diff('TEXT_REFLOW',len(lines_a),len(lines_b),rect_union(l['bbox'] for l in lines_a),rect_union(l['bbox'] for l in lines_b),'layout',explanation='The same word sequence wraps across a different number of lines.'))
        if assessed:scores['text']=100.;scores['semantic']=100.
    for field in ('width','height','rotation','cropbox','mediabox'):
        if a[field]!=b[field]:diffs.append(build_diff('PAGE_GEOMETRY_CHANGED',a[field],b[field],dimension='layout',explanation=f'Page {field} changed.'))
    for x,y in generic_pairs(a['images'],b['images'],'digest'):
        if not x or not y:
            diffs.append(build_diff('IMAGE_REMOVED' if not y else 'IMAGE_ADDED',x,y,x['bbox'] if x else None,y['bbox'] if y else None,'images'));continue
        if x['digest']!=y['digest']:
            diffs.append(build_diff('IMAGE_CHANGED',x,y,x['bbox'],y['bbox'],'images',explanation='Decoded image pixels changed.'))
        elif x.get('encoded_hash')!=y.get('encoded_hash') or x.get('filter')!=y.get('filter'):
            d=build_diff('IMAGE_COMPRESSION_CHANGED',x.get('filter'),y.get('filter'),x['bbox'],y['bbox'],'images',explanation='Encoded image changed but decoded image digest is identical.');d['severity']='informational';d['no_score']=True;diffs.append(d)
        for field in ('bbox','width','height','has_mask','transform','colorspace'):
            if field=='bbox' and bbox_delta(x[field],y[field])<=opts.position_tolerance:continue
            if x.get(field)!=y.get(field):diffs.append(build_diff('IMAGE_GEOMETRY_CHANGED' if field in ('bbox','transform','width','height') else 'IMAGE_PROPERTY_CHANGED',x.get(field),y.get(field),x['bbox'],y['bbox'],'images',explanation=f'Image {field} changed.'))
    for ti,(x,y) in enumerate(generic_pairs(a['tables'],b['tables'],'columns'),1):
        if not x or not y:
            diffs.append(build_diff('TABLE_REMOVED' if not y else 'TABLE_ADDED',x,y,x['bbox'] if x else None,y['bbox'] if y else None,'tables'));continue
        if (x['rows'],x['columns'])!=(y['rows'],y['columns']):diffs.append(build_diff('TABLE_STRUCTURE_CHANGED',[x['rows'],x['columns']],[y['rows'],y['columns']],x['bbox'],y['bbox'],'tables'))
        ca={(c['row'],c['column']):c for c in x['cells']};cb={(c['row'],c['column']):c for c in y['cells']}
        for rc in sorted(ca.keys()|cb.keys()):
            xc,yc=ca.get(rc,{}),cb.get(rc,{})
            if xc.get('text')!=yc.get('text'):
                d=build_diff('TABLE_CELL_CHANGED',xc.get('text'),yc.get('text'),xc.get('bbox') or x['bbox'],yc.get('bbox') or y['bbox'],'tables',confidence=.8 if 'ocr' in (x['source'],y['source']) else 1.,explanation=f'Table {ti}, row {rc[0]}, column {rc[1]} changed.',table=ti,row=rc[0],column=rc[1]);diffs.append(d)
            elif xc.get('bbox') and yc.get('bbox') and bbox_delta(xc['bbox'],yc['bbox'])>opts.position_tolerance:
                diffs.append(build_diff('TABLE_CELL_GEOMETRY_CHANGED',xc['bbox'],yc['bbox'],xc['bbox'],yc['bbox'],'tables',explanation=f'Table {ti}, row {rc[0]}, column {rc[1]} geometry changed.'))
    for dim,field,category,key in [('forms','forms','FORM_CHANGED','name'),('structure','annotations','ANNOTATION_CHANGED','type'),('structure','links','LINK_CHANGED','uri'),('structure','fonts','FONT_EMBEDDING_CHANGED','name')]:
        for x,y in generic_pairs(a[field],b[field],key):
            clean=lambda v:{k:z for k,z in (v or {}).items() if k not in ('bbox','subset')}
            if clean(x)!=clean(y) or (x and y and x.get('bbox') and y.get('bbox') and bbox_delta(x['bbox'],y['bbox'])>opts.position_tolerance):
                diffs.append(build_diff(category,x,y,x.get('bbox') if x else None,y.get('bbox') if y else None,dim))
    if a.get('page_objects')!=b.get('page_objects'):
        diffs.append(build_diff('PDF_RESOURCE_CHANGED',a.get('page_objects'),b.get('page_objects'),dimension='structure',explanation='Canonical page resource properties changed.'))
    if a.get('operator_counts')!=b.get('operator_counts'):
        obj=build_diff('CONTENT_OPERATORS_CHANGED',a.get('operator_counts'),b.get('operator_counts'),dimension='structure',explanation='PDF drawing/text operator inventory changed; producer encoding can cause this without visible impact.')
        obj['severity']='informational';obj['no_score']=True;diffs.append(obj)
    for x,y in generic_pairs(a['vectors'],b['vectors'],'type'):
        if not x or not y or any(x.get(k)!=y.get(k) for k in ('fill','color','width','fill_opacity','stroke_opacity','dashes')) or (x and y and bbox_delta(x['bbox'],y['bbox'])>opts.position_tolerance) or (x and y and x.get('items')!=y.get('items')):
            diffs.append(build_diff('VECTOR_CHANGED',x,y,x.get('bbox') if x else None,y.get('bbox') if y else None,'layout'))
    with fitz.open(path_a) as da,fitz.open(path_b) as db:
        pa,pb=da[mapping['a']-1],db[mapping['b']-1]
        visual=compare_visual(pa,pb,opts,folder);scores['visual']=visual['score']
        for d in diffs:
            if d.get('ocr_evidence') and visual['score']==100:
                d['category']='OCR_UNCERTAINTY';d['severity']='informational';d['no_score']=True;ocr_uncertain=True
                d['explanation']+=' Rendered pages agree within tolerance; recognition variation is not treated as a verified text change.'
        if ocr_uncertain:
            scores['text']=None;scores['semantic']=None
            notes.append('OCR text is not fully assessed: low-confidence or visually unconfirmed recognition differences require review.')
        for logo in opts.logos:
            if logo.page_a!=mapping['a'] or logo.page_b!=mapping['b']:continue
            from .extract import render,dhash
            ia,_=render(pa,150,fitz.Rect(logo.bbox_a));ib,_=render(pb,150,fitz.Rect(logo.bbox_b))
            import numpy as np
            xa=np.asarray(ia.resize((256,256)));xb=np.asarray(ib.resize((256,256)))
            changed=float(np.mean(np.max(np.abs(xa.astype(float)-xb.astype(float)),axis=2)>opts.pixel_threshold))
            if changed>.001:
                blank=lambda z:np.std(z)<2 and np.mean(z)>250
                category='LOGO_MISSING' if blank(xb) else 'LOGO_ADDED' if blank(xa) else 'LOGO_CHANGED'
                diffs.append(build_diff(category,logo.label,logo.label,logo.bbox_a,logo.bbox_b,'logos',explanation=f'{logo.label}: {changed*100:.2f}% of normalized logo crop pixels changed.'))
            wa,ha=logo.bbox_a[2]-logo.bbox_a[0],logo.bbox_a[3]-logo.bbox_a[1];wb,hb=logo.bbox_b[2]-logo.bbox_b[0],logo.bbox_b[3]-logo.bbox_b[1]
            if max(abs(wa-wb),abs(ha-hb))>opts.position_tolerance:diffs.append(build_diff('LOGO_RESIZED',[wa,ha],[wb,hb],logo.bbox_a,logo.bbox_b,'logos'))
            elif bbox_delta(logo.bbox_a,logo.bbox_b)>opts.position_tolerance:diffs.append(build_diff('LOGO_MOVED',logo.bbox_a,logo.bbox_b,logo.bbox_a,logo.bbox_b,'logos'))
        for region in visual['regions']:
            attached=[]
            for d in diffs:
                if overlap(region['bbox_a'],d['reference_bbox'])>.15 or overlap(region['bbox_b'],d['candidate_bbox'])>.15:attached.append(d)
            if attached:
                for d in attached:
                    if 'visual' not in d['signals']:d['signals'].append('visual')
                    d.setdefault('visual_regions',[]).append(region)
            else:diffs.append(build_diff('VISUAL_CHANGE',None,None,region['bbox_a'],region['bbox_b'],'visual',explanation=f'{region["pixels"]} changed pixels not attributed to a native object.',changed_pixels=region['pixels']))
    # Font metrics can move the text box: retain that geometry as evidence of the style edit.
    for primary in [d for d in diffs if d['dimension']=='typography']:
        for d in list(diffs):
            if d['category']=='POSITION_CHANGE' and overlap(primary['reference_bbox'],d['reference_bbox'])>.85 and overlap(primary['candidate_bbox'],d['candidate_bbox'])>.85:
                primary.setdefault('observations',[]).append(d);primary['signals']=sorted(set(primary['signals']+d['signals']));diffs.remove(d)
    for primary in [d for d in diffs if d['category']=='FONT_CHANGE']:
        for d in list(diffs):
            same_span=d['category']=='FONT_STYLE_CHANGE' and overlap(primary['reference_bbox'],d['reference_bbox'])>.85
            same_font=d['category']=='FONT_EMBEDDING_CHANGED' and isinstance(d['reference_value'],dict) and isinstance(d['candidate_value'],dict) and d['reference_value'].get('name')==primary['reference_value'] and d['candidate_value'].get('name')==primary['candidate_value']
            if same_span or same_font:
                primary.setdefault('observations',[]).append(d);primary['signals']=sorted(set(primary['signals']+d['signals']));diffs.remove(d)
    # Correlate table/explicit logo findings with observations at the same physical location.
    for primary in [d for d in diffs if d['dimension'] in ('tables','logos','forms')]:
        for d in list(diffs):
            if d is primary or d['dimension'] in ('tables','logos','forms'):continue
            if (overlap(primary['reference_bbox'],d['reference_bbox'])>.7 or overlap(primary['candidate_bbox'],d['candidate_bbox'])>.7) and (d['dimension'] in ('text','typography','images','visual') or primary['dimension']=='logos' and d['category']=='VECTOR_CHANGED'):
                primary.setdefault('observations',[]).append(d)
                primary['signals']=sorted(set(primary['signals']+d['signals']));diffs.remove(d)
    if mapping.get('reordered'):diffs.append(build_diff('PAGE_REORDERED',mapping['a'],mapping['b'],dimension='structure',explanation='Page order changed relative to other aligned pages.'))
    if mapping.get('ambiguous'):notes.append('Page alignment is ambiguous: repeated/similar pages require review.')
    # A dimension with no applicable elements is N/A, never an invented 100%.
    denominators={'layout':max(1,len(lines_a)+len(a['vectors'])),'typography':max(len(lines_a),len(lines_b)),
                  'images':max(len(a['images']),len(b['images'])),'logos':sum(l.page_a==mapping['a'] and l.page_b==mapping['b'] for l in opts.logos),
                  'tables':max(sum(len(t['cells']) for t in a['tables']),sum(len(t['cells']) for t in b['tables'])),
                  'forms':max(len(a['forms']),len(b['forms'])),'structure':max(1,len(a['fonts'])+len(a['annotations'])+len(a['links']))}
    for dim,n in denominators.items():
        count=sum(dim in d['signals'] and not d.get('no_score') for d in diffs)
        if n and (dim!='typography' or native):scores[dim]=round(100*(1-min(1,count/n)),5)
    result=finish(diffs,scores,mapping,opts,notes+a['warnings']+b['warnings'],a,b)
    result['visual']={k:v for k,v in visual.items() if k!='regions'}
    return result

def finish(diffs,scores,mapping,opts,notes,a,b):
    for d in diffs:
        d['severity']=opts.severity.get(d['category'],d['severity'])
        d['page_a']=mapping['a'];d['page_b']=mapping['b']
        # Repeated header/footer changes are grouped later, while preserving each occurrence.
        page=a or b;bb=d['reference_bbox'] or d['candidate_bbox']
        d['region']='header' if bb and bb[3]<page['height']*.12 else 'footer' if bb and bb[1]>page['height']*.88 else 'body'
        payload=[mapping['a'],mapping['b'],d['category'],d['reference_value'],d['candidate_value'],d['reference_bbox'],d['candidate_bbox']]
        d['difference_id']=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()[:24]
    weights={k:v for k,v in opts.weights.items() if scores[k] is not None and v>0};den=sum(weights.values())
    overall=sum(weights[k]*scores[k] for k in weights)/den if den else None
    if overall is not None:
        for dim in weights:
            relevant=[d for d in diffs if dim in d['signals'] and not d.get('no_score')]
            for d in relevant:d['score_impact']+=weights[dim]/den*(100-scores[dim])/len(relevant)
    for d in diffs:d['score_impact']=round(d['score_impact'],6)
    return dict(mapping=mapping,scores=scores,overall=round(overall,5) if overall is not None else None,differences=diffs,warnings=sorted(set(notes)),
                dimensions={'a': [a['width'],a['height']] if a else None,'b':[b['width'],b['height']] if b else None},kinds={'a':a['kind'] if a else None,'b':b['kind'] if b else None})
