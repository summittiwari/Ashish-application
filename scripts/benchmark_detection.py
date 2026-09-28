"""Controlled, reproducible category-level finding benchmark; not a general accuracy claim."""
import sys,os,json,shutil,time
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['START_WORKER']='0'
import fitz
from PIL import Image,ImageDraw
from app.extract import extract_page,inspect_document
from app.compare import compare_page
from app.pipeline import doc_diffs
from app.align import align_pages
from app.config import Options,ENGINE_VERSION

root=Path('data/golden');root.mkdir(parents=True,exist_ok=True)
opts=Options.from_input({'dpi':72,'ocr':False}).model_dump()
def make(path,text='Controlled invoice amount 300',font='helv',size=12,color=(0,0,0),pos=(30,70),extra=None,image=None,logo=False,widget=None,title=''):
    with fitz.open() as d:
        p=d.new_page(width=400,height=300)
        if text:p.insert_text(pos,text,fontname=font,fontsize=size,color=color)
        if extra:p.insert_text((30,120),extra,fontsize=12)
        if image:p.insert_image(fitz.Rect(250,180,340,260),filename=str(image))
        if logo:p.draw_rect(fitz.Rect(250,30,340,60),color=(.1,.2,.3),fill=(.1,.2,.3))
        if widget is not None:
            w=fitz.Widget();w.field_name='account';w.field_type=fitz.PDF_WIDGET_TYPE_TEXT;w.rect=fitz.Rect(40,170,180,195);w.field_value=widget;p.add_widget(w)
        d.set_metadata({'title':title});d.save(path)

for color in ('red','blue'):
    im=Image.new('RGB',(120,100),color);ImageDraw.Draw(im).rectangle((15,15,60,60),fill='white');im.save(root/f'{color}.png')
cases=[
 ('identical',{}, {},{}),
 ('character',{'text':'The cat sat.'},{'text':'The bat sat.'},{'TEXT_MODIFIED':1}),
 ('number',{}, {'text':'Controlled invoice amount 450'},{'NUMERIC_CHANGE':1}),
 ('font_family',{}, {'font':'cour'},{'FONT_CHANGE':1}),
 ('font_size',{}, {'size':13},{'FONT_SIZE_CHANGE':1}),
 ('movement_2pt',{}, {'pos':(32,70)},{'POSITION_CHANGE':1}),
 ('text_color',{}, {'color':(0,0,1)},{'COLOR_CHANGE':1}),
 ('paragraph_added',{}, {'extra':'Additional terms apply.'},{'TEXT_ADDED':1}),
 ('paragraph_removed',{'extra':'Additional terms apply.'},{},{'TEXT_REMOVED':1}),
 ('polarity',{'text':'Refunds are permitted.'},{'text':'Refunds are not permitted.'},{'POLARITY_CHANGE':1}),
 ('obligation',{'text':'Payment must be made.'},{'text':'Payment may be made.'},{'OBLIGATION_CHANGE':1}),
 ('image_replaced',{'image':root/'red.png'},{'image':root/'blue.png'},{'IMAGE_CHANGED':1}),
 ('metadata_only',{'title':'Reference'},{'title':'Candidate'},{'METADATA_CHANGED':1}),
 ('form_value',{'widget':'300'},{'widget':'450'},{'FORM_CHANGED':1}),
]
records=[];started=time.monotonic()
def record(name,expected,findings,extra=None):
    actual=Counter(d['category'] for d in findings if not d.get('no_score'))
    expected=Counter(expected);tp=sum((actual&expected).values());fp=sum((actual-expected).values());fn=sum((expected-actual).values())
    records.append(dict(case=name,expected=dict(expected),actual=dict(actual),true_positive=tp,false_positive=fp,false_negative=fn,**(extra or {})))

for name,ka,kb,expected in cases:
    folder=root/name;folder.mkdir(exist_ok=True);pa,pb=folder/'reference.pdf',folder/'candidate.pdf';make(pa,**ka);make(pb,**kb)
    aa=extract_page(pa,0,folder/'a.json',False);bb=extract_page(pb,0,folder/'b.json',False)
    result=compare_page(aa,bb,pa,pb,{'a':1,'b':1,'reordered':False},opts,folder/'visual')
    findings=result['differences']+doc_diffs({'info':inspect_document(pa)},{'info':inspect_document(pb)},opts)
    record(name,expected,findings)

# Alignment fixtures use real extracted pages; every unmatched page becomes a primary finding.
for name,words_a,words_b,expected in [
 ('page_reordered',['Alpha account','Beta contract','Gamma schedule'],['Gamma schedule','Alpha account','Beta contract'],{'PAGE_REORDERED':1}),
 ('page_removed',['Alpha account','Beta contract','Gamma schedule'],['Alpha account','Gamma schedule'],{'PAGE_REMOVED':1}),
 ('page_added',['Alpha account','Gamma schedule'],['Alpha account','Beta contract','Gamma schedule'],{'PAGE_ADDED':1})]:
    folder=root/name;folder.mkdir(exist_ok=True);ex=[];paths=[]
    for side,words in [('a',words_a),('b',words_b)]:
        path=folder/f'{side}.pdf';paths.append(path)
        with fitz.open() as d:
            for word in words:d.new_page(width=400,height=300).insert_text((30,70),word)
            d.save(path)
        ex.append([extract_page(path,i,folder/f'{side}{i}.json',False) for i in range(len(words))])
    findings=[]
    for idx,mapping in enumerate(align_pages([p['fingerprint'] for p in ex[0]],[p['fingerprint'] for p in ex[1]],.53)):
        result=compare_page(ex[0][mapping['a']-1] if mapping['a'] else None,ex[1][mapping['b']-1] if mapping['b'] else None,*paths,mapping,opts,folder/f'visual{idx}')
        findings.extend(result['differences'])
    record(name,expected,findings)

tp=sum(r['true_positive'] for r in records);fp=sum(r['false_positive'] for r in records);fn=sum(r['false_negative'] for r in records)
precision=tp/(tp+fp) if tp+fp else 1;recall=tp/(tp+fn) if tp+fn else 1
report=dict(engine=ENGINE_VERSION,scope='Synthetic category-level primary-finding counts; category and multiplicity must match. No OCR model, external corpus, localization-IoU evaluation, or independent producer suite included.',
 cases=records,metrics=dict(true_positive=tp,false_positive=fp,false_negative=fn,precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision+recall else 0,
 false_discovery_rate=fp/(tp+fp) if tp+fp else 0,false_negative_rate=fn/(tp+fn) if tp+fn else 0,false_positive_rate=None,
 false_positive_rate_note='Undefined for open-ended finding detection: true negatives are not enumerable. Negative-document false-alarm rate is reported separately.',
 negative_document_false_alarm_rate=sum(bool(r['actual']) for r in records if not r['expected'])/max(1,sum(not r['expected'] for r in records))),seconds=time.monotonic()-started)
Path('docs/benchmark-detection.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
