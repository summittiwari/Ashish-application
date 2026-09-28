"""Paged exports. Detailed PDF volumes bound report memory; originals are never modified."""
import csv,json,zipfile,math,os
from pathlib import Path
from collections import Counter
from sqlalchemy import select
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor,white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from openpyxl import Workbook
import fitz
from .config import ROOT
from .db import one,jobs,documents,pages,engine,iterate_diffs
from .pipeline import document_path
from .util import safe_cell

FONT='Helvetica'
for candidate in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf']:
    if os.path.exists(candidate):
        pdfmetrics.registerFont(TTFont('ReportUnicode',candidate));FONT='ReportUnicode';break
COLORS=['#387cf5','#825ee4','#19a895','#e8a72c','#e76379','#64748b','#d26ee0','#74a4cc']

def text(c,s,x,y,size=10,color='#24354a'):
    c.setFillColor(HexColor(color));c.setFont(FONT,size);c.drawString(x,y,str(s))

def wrap(c,s,x,y,width=500,size=9,leading=13,max_lines=None):
    # Preserve all text; callers paginate long findings rather than truncating silently.
    lines=[]
    for para in str(s if s is not None else '—').splitlines() or ['']:
        current=''
        for char in para:
            if pdfmetrics.stringWidth(current+char,FONT,size)>width:
                lines.append(current);current=char
            else:current+=char
        lines.append(current)
    for line in lines:
        if y<55:c.showPage();header(c,'Detail continued');y=742
        text(c,line,x,y,size);y-=leading
    return y

def header(c,title):
    c.setFillColor(HexColor('#132b49'));c.rect(0,788,595,54,fill=1,stroke=0)
    text(c,'PDF SENTINEL',36,809,15,'#ffffff');text(c,title,36,766,17)
    text(c,'Deterministic document comparison • Match is not detection accuracy',36,23,8,'#65748b')

def donut(c,counts,x=118,y=430):
    total=sum(counts.values());start=90
    if not total:c.setStrokeColor(HexColor('#cbd5e1'));c.circle(x,y,60);return
    for i,(key,n) in enumerate(counts.items()):
        angle=360*n/total;c.setFillColor(HexColor(COLORS[i%len(COLORS)]));c.wedge(x-65,y-65,x+65,y+65,start,angle,stroke=0,fill=1);start+=angle
    c.setFillColor(white);c.circle(x,y,40,stroke=0,fill=1);text(c,str(total),x-10,y-4,16)
    for i,(key,n) in enumerate(counts.items()):
        yy=y+55-i*17;c.setFillColor(HexColor(COLORS[i%len(COLORS)]));c.rect(x+100,yy-2,9,9,fill=1,stroke=0);text(c,f'{key}: {n}',x+116,yy,9)

def generate_exports(job):
    state=one(jobs,job);summary=state['summary'];folder=ROOT/'jobs'/job/'exports';folder.mkdir(parents=True,exist_ok=True)
    a,b=one(documents,state['a']),one(documents,state['b'])
    for old_volume in folder.glob('details-*.pdf'):old_volume.unlink()
    fields=['difference_id','page_a','page_b','category','severity','confidence','reference_value','candidate_value','reference_bbox','candidate_bbox','explanation','score_impact','signals']
    with open(folder/'result.json','w') as f:
        f.write('{"schema_version":"1.0","summary":');json.dump(summary,f,ensure_ascii=False);f.write(',"pages":[')
        with engine.connect() as conn:
            for i,row in enumerate(conn.execute(select(pages.c.data).where(pages.c.job==job,pages.c.idx>=0).order_by(pages.c.idx))):
                if i:f.write(',')
                json.dump(row[0],f,ensure_ascii=False)
        f.write('],"differences":[')
        for i,d in enumerate(iterate_diffs(job)):
            if i:f.write(',')
            json.dump(d,f,ensure_ascii=False)
        f.write(']}')
    wb=Workbook(write_only=True);ws=wb.create_sheet('Differences');ws.append(fields);info=wb.create_sheet('Summary');info.append(['Metric','Value'])
    for k in ('overall','score_label','total_differences','page_pairs','failed_pages','incomplete','formula'):info.append([k,safe_cell(summary[k])])
    for k,v in summary['scores'].items():info.append([f'{k} match',v])
    ps=wb.create_sheet('Pages');ps.append(['Pair','Reference','Candidate','Status','Match'])
    with engine.connect() as conn:
        for row in conn.execute(select(pages).where(pages.c.job==job,pages.c.idx>=0).order_by(pages.c.idx)).mappings():ps.append([row['idx']+1,row['a'],row['b'],row['status'],row['score']])
    with open(folder/'differences.csv','w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(fields)
        for d in iterate_diffs(job):
            vals=[json.dumps(d.get(k),ensure_ascii=False) if isinstance(d.get(k),(list,dict)) else d.get(k) for k in fields]
            writer.writerow([safe_cell(v) for v in vals]);ws.append([safe_cell(v) if isinstance(v,str) else v for v in vals])
    wb.save(folder/'comparison.xlsx')
    c=canvas.Canvas(str(folder/'report.pdf'),pagesize=(595,842));c.setTitle('PDF Sentinel comparison report');header(c,'Comparison report')
    y=730;y=wrap(c,f'Reference: {a["name"]}',36,y);y=wrap(c,f'Candidate: {b["name"]}',36,y)
    overall=f'{summary["overall"]:.2f}%' if summary['overall'] is not None else 'Not assessed'
    text(c,overall,36,y-42,32,'#176bb8');text(c,summary['score_label'],210,y-37,11)
    y-=80
    for k in ('page_pairs','matched_pages','changed_pages','total_differences','failed_pages'):
        text(c,f'{k.replace("_"," ").title()}: {summary[k]}',36,y,10);y-=18
    donut(c,summary['distribution'],118,420)
    y=290
    for k,v in summary['scores'].items():
        text(c,k.title(),36,y);text(c,'N/A' if v is None else f'{v:.2f}%',180,y)
        c.setFillColor(HexColor('#e5eaf1'));c.rect(245,y-2,240,7,fill=1,stroke=0)
        if v is not None:c.setFillColor(HexColor('#387cf5'));c.rect(245,y-2,240*v/100,7,fill=1,stroke=0)
        y-=18
    c.showPage();header(c,'Scoring, coverage and review notes');y=730
    for severity in ('critical','major','minor','informational'):
        count=summary['severity'].get(severity,0)
        text(c,severity.title(),36,y);text(c,str(count),140,y)
        c.setFillColor(HexColor({'critical':'#e76379','major':'#e8a72c','minor':'#387cf5','informational':'#64748b'}[severity]))
        c.rect(180,y-2,300*count/max(1,summary['total_differences']),8,fill=1,stroke=0);y-=22
    y-=20
    for s in [summary['formula'],summary['confidence_note'],'Weights: '+json.dumps(summary['weights']),*summary['warnings']]:y=wrap(c,s,36,y)-13
    if not summary['warnings']:text(c,'No extraction or alignment warnings.',36,y)
    c.showPage();header(c,'Page comparison');y=729
    with engine.connect() as conn:
        for row in conn.execute(select(pages).where(pages.c.job==job,pages.c.idx>=0).order_by(pages.c.idx)).mappings():
            if y<65:c.showPage();header(c,'Page comparison continued');y=729
            score='N/A' if row['score'] is None else f'{row["score"]:.2f}%'
            text(c,f'A {row["a"] or "—"}   →   B {row["b"] or "—"}',36,y);text(c,row['status'],230,y);text(c,score,450,y);y-=19
    c.save()
    # Volumes of 100 findings include every detail and two evidence crops where coordinates exist.
    c=None;volume=0
    with fitz.open(document_path(a['id'])) as da,fitz.open(document_path(b['id'])) as db:
        for i,d in enumerate(iterate_diffs(job)):
            if i%100==0:
                if c:c.save()
                volume+=1;c=canvas.Canvas(str(folder/f'details-{volume:03}.pdf'),pagesize=(595,842));c.setTitle(f'Detailed differences volume {volume}')
            header(c,f'Finding {i+1}: {d["category"].replace("_"," ")}');y=728
            y=wrap(c,f'Page A: {d["page_a"] or "—"} | Page B: {d["page_b"] or "—"} | {d["severity"]} | Evidence confidence: {d["confidence"]:.1%}',36,y)-9
            for label,val in [('Reference',d['reference_value']),('Candidate',d['candidate_value']),('Explanation',d['explanation']),('Supporting signals',', '.join(d['signals'])),('Score impact (percentage points)',d['score_impact'])]:
                y=wrap(c,f'{label}: {json.dumps(val,ensure_ascii=False) if isinstance(val,(dict,list)) else val}',36,y)-9
            if y<260:c.showPage();header(c,'Evidence crops');y=729
            for side,doc,x in [('a',da,36),('b',db,305)]:
                page=d.get('page_'+side);bb=d.get('reference_bbox' if side=='a' else 'candidate_bbox')
                if page and bb:
                    p=doc[page-1];clip=(fitz.Rect(bb)+(-10,-10,10,10));clip&=p.rect
                    if not clip.is_empty:
                        from .extract import render
                        im,scale=render(p,108,clip)
                        from reportlab.lib.utils import ImageReader
                        from PIL import Image,ImageDraw
                        draw=ImageDraw.Draw(im)
                        br=fitz.Rect(bb);coords=[(br.x0-clip.x0)*scale,(br.y0-clip.y0)*scale,(br.x1-clip.x0)*scale,(br.y1-clip.y0)*scale]
                        draw.rectangle(coords,outline='#f43f5e',width=2)
                        text(c,'Reference' if side=='a' else 'Candidate',x,y,10)
                        factor=min(240/im.width,180/im.height);c.drawImage(ImageReader(im),x,y-16-im.height*factor,width=im.width*factor,height=im.height*factor)
            c.showPage()
        if c:c.save()
    with zipfile.ZipFile(folder/'detailed-report.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.write(folder/'report.pdf','00-summary.pdf')
        for p in sorted(folder.glob('details-*.pdf')):z.write(p,p.name)
    # Incremental annotations reuse originals on disk, never rewriting uploaded documents.
    for side,doc in [('a',a),('b',b)]:
        target=folder/f'annotated-{side}.pdf'
        import shutil
        shutil.copyfile(document_path(doc['id']),target)
        with fitz.open(target) as pdf:
            for d in iterate_diffs(job):
                pn=d.get('page_'+side);bb=d.get('reference_bbox' if side=='a' else 'candidate_bbox')
                if pn and bb:
                    p=pdf[pn-1];rect=fitz.Rect(bb)*p.derotation_matrix;rect&=p.rect*p.derotation_matrix
                    if rect.is_empty:continue
                    annotation=p.add_rect_annot(rect);annotation.set_colors(stroke=(.96,.2,.3));annotation.set_opacity(.75)
                    annotation.set_info(title='PDF Sentinel',content=f'{d["category"]}: {d["explanation"]}');annotation.update()
            if pdf.can_save_incrementally():pdf.saveIncr()
            else:
                tmp=target.with_suffix('.tmp.pdf');pdf.save(tmp);os.replace(tmp,target)
    return folder
