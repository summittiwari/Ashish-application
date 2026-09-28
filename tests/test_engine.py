import os
os.environ['START_WORKER']='0'
import pytest,fitz
from pathlib import Path
from PIL import Image
from app.extract import extract_page
from app.compare import compare_page
from app.config import Options
from app.align import align_pages
from app.semantic import compare_semantics
from app.util import safe_cell

@pytest.fixture
def pdf(tmp_path):
    def make(name,text='Payment must be completed within 30 days.',size=12,color=(0,0,0),pos=(50,80),rotate=0):
        path=tmp_path/name
        with fitz.open() as d:
            p=d.new_page(width=400,height=300)
            if text:p.insert_text(pos,text,fontsize=size,color=color)
            p.set_rotation(rotate);d.save(path)
        return path
    return make

def compare(tmp_path,a,b,**options):
    aa=extract_page(a,0,tmp_path/'a.json',False);bb=extract_page(b,0,tmp_path/'b.json',False)
    return compare_page(aa,bb,a,b,{'a':1,'b':1,'reordered':False,'ambiguous':False,'confidence':1},Options.from_input({'dpi':72,**options}).model_dump(),tmp_path/'visual')

def test_identical_is_exact(tmp_path,pdf):
    a=pdf('same.pdf');r=compare(tmp_path,a,a)
    assert r['differences']==[] and r['overall']==100
    assert r['scores']['logos'] is None and r['scores']['images'] is None

def test_number_has_precise_evidence_and_is_correlated(tmp_path,pdf):
    a=pdf('a.pdf');b=pdf('b.pdf',text='Payment must be completed within 45 days.')
    r=compare(tmp_path,a,b);diff=[d for d in r['differences'] if d['category']=='NUMERIC_CHANGE']
    assert len(diff)==1
    d=diff[0];assert (d['reference_value'],d['candidate_value'])==('30','45')
    assert d['reference_bbox'][2]-d['reference_bbox'][0]<25
    assert {'text','semantic','visual'}<=set(d['signals'])
    assert not [d for d in r['differences'] if d['category']=='VISUAL_CHANGE']

def test_polarity(tmp_path,pdf):
    r=compare(tmp_path,pdf('a.pdf','Refunds are permitted.'),pdf('b.pdf','Refunds are not permitted.'))
    assert any(d['category']=='POLARITY_CHANGE' for d in r['differences'])
    assert r['scores']['semantic']==0

def test_font_change_correlates_geometry(tmp_path,pdf):
    r=compare(tmp_path,pdf('a.pdf','A heading',size=12),pdf('b.pdf','A heading',size=13))
    assert len(r['differences'])==1
    assert r['differences'][0]['category']=='FONT_SIZE_CHANGE'
    assert 'layout' in r['differences'][0]['signals']

def test_color_change(tmp_path,pdf):
    r=compare(tmp_path,pdf('a.pdf','Heading'),pdf('b.pdf','Heading',color=(0,0,1)))
    assert any(d['category']=='COLOR_CHANGE' for d in r['differences'])

def test_position_change(tmp_path,pdf):
    r=compare(tmp_path,pdf('a.pdf','Move me'),pdf('b.pdf','Move me',pos=(58,90)))
    assert any(d['category']=='POSITION_CHANGE' for d in r['differences'])

def test_unassessed_scan_never_claims_text_match(tmp_path,pdf):
    image=Image.new('RGB',(600,400),'white');from PIL import ImageDraw
    ImageDraw.Draw(image).text((50,40),'SCAN CONTENT',fill='black');image.save(tmp_path/'scan.png')
    with fitz.open() as d:
        p=d.new_page(width=400,height=300);p.insert_image(p.rect,filename=str(tmp_path/'scan.png'));d.save(tmp_path/'scan.pdf')
    r=compare(tmp_path,tmp_path/'scan.pdf',tmp_path/'scan.pdf')
    assert r['scores']['text'] is None and r['scores']['semantic'] is None
    assert any('not fully assessed' in w for w in r['warnings'])

def test_rotation_boxes_in_page_space(tmp_path,pdf):
    p=pdf('rot.pdf','Rotated',rotate=90);a=extract_page(p,0,tmp_path/'rot.json',False)
    assert a['width']==300 and a['height']==400
    for line in a['lines']:
        x0,y0,x1,y1=line['bbox'];assert 0<=x0<x1<=300 and 0<=y0<y1<=400

def inventory(words):
    import hashlib
    return [dict(text=w,text_hash=hashlib.sha256(w.encode()).hexdigest(),render_hash=w,visual_hash='0'*64,width=400,height=300,lines=1,kind='native') for w in words]

def test_insert_not_reorder():
    a=inventory(['A one','B two','C three']);b=inventory(['A one','Unique insertion','B two','C three'])
    r=align_pages(a,b)
    assert any(x['a'] is None and x['b']==2 for x in r)
    assert not any(x['reordered'] for x in r)
    assert [(x['a'],x['b']) for x in r if x['a']]==[(1,1),(2,3),(3,4)]

def test_reorder_and_duplicate_occurrences():
    r=align_pages(inventory(['Alpha','Beta','Alpha']),inventory(['Alpha','Alpha','Beta']))
    assert len(r)==3 and len({p['b'] for p in r})==3
    assert any(p['reordered'] for p in r)
    assert any(p['duplicate_a'] for p in r)

def test_forms_value_change(tmp_path,pdf):
    a=pdf('a.pdf','Application');b=tmp_path/'b.pdf'
    with fitz.open(a) as d:
        p=d[0];w=fitz.Widget();w.field_name='customer';w.field_type=fitz.PDF_WIDGET_TYPE_TEXT;w.rect=fitz.Rect(50,120,200,150);w.field_value='Alice';p.add_widget(w);d.save(tmp_path/'form-a.pdf')
    with fitz.open(tmp_path/'form-a.pdf') as d:
        p=d[0];w=next(p.widgets());w.field_value='Bob';w.update();d.save(b)
    r=compare(tmp_path,tmp_path/'form-a.pdf',b)
    assert any(d['category']=='FORM_CHANGED' for d in r['differences'])

def test_rules_do_not_claim_unknown_paraphrase():
    assert compare_semantics('A dog ran away.','The animal departed.')['similarity'] is None
    assert compare_semantics('Payment within thirty days.','Payment within 30 days.')['similarity']==1
    assert compare_semantics('Payment must be made.','Payment may be made.')['kind']=='OBLIGATION_CHANGE'

def test_csv_injection():
    for value in ('=HYPERLINK("x")',' +CMD','@SUM(A1:A2)','-1'):
        assert safe_cell(value).startswith("'")

def test_multiple_digit_edit_is_single_finding(tmp_path,pdf):
    r=compare(tmp_path,pdf('a.pdf','Amount 300'),pdf('b.pdf','Amount 450'))
    numeric=[d for d in r['differences'] if d['category']=='NUMERIC_CHANGE']
    assert len(numeric)==1
    assert numeric[0]['reference_value']=='300' and numeric[0]['candidate_value']=='450'

def test_ocr_variation_with_identical_pixels_is_uncertainty(tmp_path,pdf):
    path=pdf('a.pdf','Amount 300')
    a=extract_page(path,0,tmp_path/'a.json',False);b=extract_page(path,0,tmp_path/'b.json',False)
    for p in (a,b):
        for line in p['lines']:line.update(source='ocr',confidence=.9,chars=[],spans=[])
    b['lines'][0]['text']='Amount 800';b['text']='Amount 800'
    r=compare_page(a,b,path,path,{'a':1,'b':1},Options(dpi=72).model_dump(),tmp_path/'vis')
    assert len(r['differences'])==1
    assert r['differences'][0]['category']=='OCR_UNCERTAINTY'
    assert r['differences'][0]['no_score']
    assert r['scores']['text'] is None and r['scores']['semantic'] is None

def test_character_spacing(tmp_path):
    from reportlab.pdfgen import canvas
    paths=[]
    for name,spacing in [('a',0),('b',1)]:
        path=tmp_path/f'{name}.pdf';c=canvas.Canvas(str(path),pagesize=(400,300));t=c.beginText(30,230);t.setFont('Helvetica',12);t.setCharSpace(spacing);t.textLine('Spacing');c.drawText(t);c.save();paths.append(path)
    r=compare(tmp_path,*paths)
    assert any(d['category']=='CHARACTER_SPACING_CHANGE' for d in r['differences'])

def test_explicit_logo_missing_correlates_vector(tmp_path):
    paths=[]
    for name,present in [('a',True),('b',False)]:
        path=tmp_path/f'{name}.pdf'
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=300)
            if present:p.draw_rect(fitz.Rect(30,30,100,60),fill=(.1,.2,.3),color=None)
            doc.save(path)
        paths.append(path)
    r=compare(tmp_path,*paths,logos=[dict(page_a=1,page_b=1,bbox_a=[25,25,105,65],bbox_b=[25,25,105,65])])
    primary=[d for d in r['differences'] if not d.get('no_score')]
    assert len(primary)==1 and primary[0]['category']=='LOGO_MISSING'
