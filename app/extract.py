import re, hashlib, json, math, io, time
from pathlib import Path
import fitz
import numpy as np
from PIL import Image
from .config import MAX_PIXELS, MAX_PAGES, ENGINE_VERSION
from .util import write_json, overlap


def box(page,b):
    return [round(v,3) for v in (fitz.Rect(b)*page.rotation_matrix)]

def fontname(name): return re.sub(r'^[A-Z]{6}\+','',str(name))

def render(page,dpi=150,clip=None):
    # Display coordinates are used consistently, including page rotation.
    target=page.rect
    scale=min(dpi/72,math.sqrt(MAX_PIXELS/max(1,target.width*target.height)))
    if target.width<=0 or target.height<=0:raise ValueError('Empty page rectangle')
    pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False,colorspace=fitz.csRGB)
    im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
    if clip is not None:
        r=fitz.Rect(clip)&target
        if r.is_empty:raise ValueError('Empty clip rectangle')
        im=im.crop(tuple(round(v*scale) for v in r))
    return im,scale

def dhash(im):
    a=np.asarray(im.convert('L').resize((9,8)))
    return ''.join('1' if x else '0' for x in (a[:,1:]>a[:,:-1]).ravel())

def inspect_document(path):
    with fitz.open(path) as d:
        if d.needs_pass:raise ValueError('This PDF requires a password. Supply a decrypted copy; password-protected content is not assessed.')
        if not d.is_pdf:raise ValueError('The uploaded file is not a PDF')
        if len(d)>MAX_PAGES:raise ValueError(f'Page limit is {MAX_PAGES}; administrator can raise MAX_PAGES')
        if not len(d):raise ValueError('Empty PDF')
        info=dict(pages=len(d),metadata=d.metadata,version=d.metadata.get('format'),encrypted=bool(d.is_encrypted or d.metadata.get('encryption')),
                  permissions=d.permissions,dimensions=[round(x,2) for x in d[0].rect[2:]],orientation='landscape' if d[0].rect.width>d[0].rect.height else 'portrait',
                  warnings=[],outlines=d.get_toc(),embedded_files=d.embfile_names())
        from .fontinspect import inspect_fonts
        info['embedded_fonts'],fw=inspect_fonts(d);info['warnings'].extend(fw)
        try:info['xml_metadata']=d.get_xml_metadata()
        except Exception as e:info['warnings'].append(f'XMP: {e}')
        try:info['layers']={str(k):v for k,v in d.get_ocgs().items()}
        except Exception:info['layers']={}
        # Remove volatile xref IDs; layer definitions are keyed by stable names.
        info['layers']=sorted([{k:v for k,v in layer.items() if k!='xref'} for layer in info['layers'].values()],key=lambda x:x.get('name',''))
    import pikepdf
    with pikepdf.open(path) as p:
        info['pdf_version']=str(p.pdf_version)
        info['custom_metadata']={str(k):str(v) for k,v in p.docinfo.items()}
        info['encryption']={'encrypted':p.is_encrypted}
        info['structure']={}
        for key in ('/Names','/PageLabels','/OCProperties','/AcroForm','/MarkInfo','/Lang','/ViewerPreferences'):
            if key in p.Root:info['structure'][key]=canonical(p.Root[key],maxdepth=5)
        info['xfa_present']=bool(p.Root.get('/AcroForm',{}).get('/XFA'))
        if info['xfa_present']:info['warnings'].append('XFA present: only AcroForm fields and rendered appearances are assessed; dynamic XFA semantics are not supported.')
        info['attachments']=[]
        for name in p.attachments:
            try:
                obj=p.attachments[name].get_file()
                size=int(obj.size)
                data=obj.read_bytes() if size<=32*1024**2 else None
                info['attachments'].append({'name':name,'size':size,'sha256':hashlib.sha256(data).hexdigest() if data is not None else None})
                if data is None:info['warnings'].append(f'Attachment content over 32 MiB not inspected: {name}')
            except Exception as e:info['warnings'].append(f'Attachment {name}: {type(e).__name__}')
    return info

def canonical(obj,depth=0,maxdepth=4,seen=None):
    """Bounded canonical object view, independent of object numbers and resource names."""
    import pikepdf
    if depth>maxdepth:return '<depth-limit>'
    if obj is None:return None
    if isinstance(obj,pikepdf.Stream):
        length=int(obj.get('/Length',0))
        data=obj.read_bytes() if length<4*1024**2 else None
        return {'stream_hash':hashlib.sha256(data).hexdigest() if data else None,
                'dictionary':{str(k):canonical(v,depth+1,maxdepth) for k,v in obj.items() if str(k) not in ('/Length','/Filter','/DecodeParms')}}
    if isinstance(obj,pikepdf.Dictionary):
        return {str(k):canonical(v,depth+1,maxdepth) for k,v in sorted(obj.items()) if str(k) not in ('/Parent','/P','/Kids','/AP')}
    if isinstance(obj,pikepdf.Array):return [canonical(x,depth+1,maxdepth) for x in obj][:10000]
    if isinstance(obj,(int,float,bool)):return obj
    return str(obj)

def extract_page(path,index,out,ocr_enabled=True):
    started=time.monotonic();warnings=[]
    with fitz.open(path) as doc:
        p=doc[index];w,h=p.rect.width,p.rect.height
        result=dict(index=index+1,width=w,height=h,rotation=p.rotation,mediabox=list(p.mediabox),cropbox=list(p.cropbox),lines=[],images=[],tables=[],vectors=[],forms=[],annotations=[],links=[],fonts=[],warnings=warnings,engine=ENGINE_VERSION)
        raw=p.get_text('rawdict',flags=fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES,sort=True)
        for block in raw['blocks']:
            if block['type']!=0:continue
            for li,line in enumerate(block['lines']):
                chars=[];spans=[]
                for s in line['spans']:
                    style={k:s.get(k) for k in ('font','size','flags','color','alpha')};style['font']=fontname(style['font'])
                    style['rotation']=round(math.degrees(math.atan2(-line['dir'][1],line['dir'][0]))+p.rotation,2)
                    style['wmode']=line.get('wmode',0)
                    for ch in s['chars']:chars.append(dict(c=ch['c'],bbox=box(p,ch['bbox']),style=style))
                    spans.append(dict(text=''.join(x['c'] for x in s['chars']),bbox=box(p,s['bbox']),style=style))
                text=''.join(c['c'] for c in chars)
                if text.strip():result['lines'].append(dict(text=text,chars=chars,spans=spans,bbox=box(p,line['bbox']),block=block.get('number',0),source='native',confidence=1.))
        for item in p.get_image_info(hashes=True,xrefs=True):
            info={k:item.get(k) for k in ('width','height','bpc','colorspace','cs-name','xres','yres','transform')}
            info['bbox']=box(p,item['bbox']);info['digest']=item.get('digest',b'').hex();info['has_mask']=False
            xref=item.get('xref',0)
            if xref:
                try:
                    typ,length=doc.xref_get_key(xref,'Length')
                    if typ=='int' and int(length)<16*1024**2:
                        data=doc.xref_stream_raw(xref);info['encoded_hash']=hashlib.sha256(data).hexdigest()
                    info['filter']=doc.xref_get_key(xref,'Filter')[1]
                    info['has_mask']=doc.xref_get_key(xref,'SMask')[0]!='null'
                except Exception as e:warnings.append(f'Image encoding: {type(e).__name__}')
            result['images'].append(info)
        for d in p.get_drawings():
            items=[]
            for it in d.get('items',[]):
                items.append([it[0],*[list(v) if isinstance(v,(fitz.Point,fitz.Rect,fitz.Quad)) else v for v in it[1:]]])
            result['vectors'].append(dict(bbox=box(p,d['rect']),type=d['type'],fill=d.get('fill'),color=d.get('color'),width=d.get('width'),fill_opacity=d.get('fill_opacity'),stroke_opacity=d.get('stroke_opacity'),dashes=d.get('dashes'),items=items))
        for line in result['lines']:
            for span in line['spans']:
                bb=span['bbox'];span['style']['underline']=False;span['style']['strike_through']=False
                for v in result['vectors']:
                    r=v['bbox']
                    if abs(r[3]-r[1])<1.5 and min(r[2],bb[2])-max(r[0],bb[0])>max(2,(bb[2]-bb[0])*.7):
                        if abs(r[1]-(bb[3]-span['style']['size']*.12))<2:span['style']['underline']=True
                        if abs(r[1]-(bb[1]+bb[3])/2)<2:span['style']['strike_through']=True
                subset=[c for c in line['chars'] if overlap(c['bbox'],bb)>.8]
                advances=[round(subset[k+1]['bbox'][0]-subset[k]['bbox'][0],3) for k in range(len(subset)-1)]
                span['advances']=advances
        try:
            import pikepdf
            with pikepdf.open(path) as pdf:
                pageobj=pdf.pages[index]
                result['page_objects']={}
                resources=pageobj.obj.get('/Resources',{})
                for key in ('/ExtGState','/Properties','/ColorSpace'):
                    if key in resources:
                        values=resources[key]
                        result['page_objects'][key]=sorted([canonical(v) for _,v in values.items()],key=lambda x:json.dumps(x,sort_keys=True)) if hasattr(values,'items') else canonical(values)
                result['page_objects']['transparency_group']=canonical(pageobj.obj.get('/Group'))
                # Operator sequence is independent of raw object numbers, but producer rewrites can still differ.
                result['operator_counts']=dict(__import__('collections').Counter(str(op) for _,op in pikepdf.parse_content_stream(pageobj)))
        except Exception as e:warnings.append(f'PDF object inspection incomplete: {type(e).__name__}')
        for widget in p.widgets() or []:
            result['forms'].append(dict(name=widget.field_name,type=widget.field_type_string,value=widget.field_value,flags=widget.field_flags,options=widget.choice_values,bbox=box(p,widget.rect),label=widget.field_label))
        for a in p.annots() or []:
            result['annotations'].append(dict(type=a.type[1],info=a.info,bbox=box(p,a.rect),colors=a.colors,opacity=a.opacity,vertices=a.vertices))
        for link in p.get_links():
            result['links'].append({k:box(p,v) if k=='from' else list(v) if isinstance(v,fitz.Point) else v for k,v in link.items() if k not in ('xref','id')})
        for f in p.get_fonts(full=True):
            xref,ext,typ,name,resource,encoding,*_=f
            result['fonts'].append(dict(name=fontname(name),subset=name!=fontname(name),type=typ,encoding=encoding,embedded=ext not in ('n/a','')))
        try:
            tables=p.find_tables()
            for ti,t in enumerate(tables.tables):
                rows=t.extract();cells=[]
                for ri,row in enumerate(t.rows):
                    for ci,bb in enumerate(row.cells):
                        cells.append(dict(row=ri+1,column=ci+1,text=rows[ri][ci] if ri<len(rows) and ci<len(rows[ri]) else None,bbox=box(p,bb) if bb else None))
                result['tables'].append(dict(bbox=box(p,t.bbox),rows=t.row_count,columns=t.col_count,cells=cells,source='native',header=t.header.names))
        except Exception as e:warnings.append(f'Table extraction failed: {type(e).__name__}')
        native_chars=sum(len(l['text']) for l in result['lines'])
        scan_regions=[]
        for im in result['images']:
            bb=im['bbox'];area=max(0,bb[2]-bb[0])*max(0,bb[3]-bb[1])
            native_inside=sum(len(l['text']) for l in result['lines'] if overlap(bb,l['bbox'])>.5)
            if area/(w*h)>.08 and native_inside<15:scan_regions.append(bb)
        result['kind']='hybrid' if native_chars and scan_regions else 'scanned' if scan_regions and not native_chars else 'native' if native_chars else 'graphics'
        result['text_assessed']=True
        if scan_regions:
            if ocr_enabled:
                from .ocr import recognize
                for bb in scan_regions:
                    try:
                        clip=fitz.Rect(bb)
                        im,scale=render(p,150,clip=clip)
                        for block in recognize(im):
                            b=block['bbox'];mapped=[bb[0]+b[0]/scale,bb[1]+b[1]/scale,bb[0]+b[2]/scale,bb[1]+b[3]/scale]
                            if block['text'] and not any(overlap(mapped,l['bbox'])>.6 for l in result['lines']):
                                result['lines'].append(dict(text=block['text'],bbox=mapped,chars=[],spans=[],source='ocr',confidence=block['confidence'],block=10000+block['order'],label=block['label']))
                            if block['label']=='Table' and block.get('html'):
                                result['tables'].append(ocr_table(block['html'],mapped))
                    except Exception as e:result['text_assessed']=False;warnings.append(str(e))
            else:result['text_assessed']=False;warnings.append('OCR disabled: text in image regions was not assessed.')
        result['lines'].sort(key=lambda l:(round(l['bbox'][1]/3),l['bbox'][0]))
        result['text']='\n'.join(l['text'] for l in result['lines'])
        result['text_hash']=hashlib.sha256(result['text'].encode()).hexdigest()
        im,scale=render(p,36);result['visual_hash']=dhash(im)
        result['render_hash']=hashlib.sha256(im.tobytes()).hexdigest()
        result['fingerprint']=dict(text=result['text'][:12000],text_hash=result['text_hash'],visual_hash=result['visual_hash'],render_hash=result['render_hash'],width=w,height=h,lines=len(result['lines']),kind=result['kind'])
    result['elapsed']=round(time.monotonic()-started,4)
    write_json(out,result)
    return result

def ocr_table(html,bbox):
    from html.parser import HTMLParser
    class TableParser(HTMLParser):
        def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
        def handle_starttag(self,t,a):
            if t=='tr':self.row=[];self.rows.append(self.row)
            if t in ('td','th'):
                if self.row is None:self.row=[];self.rows.append(self.row)
                self.cell={'text':'','attributes':dict(a)};self.row.append(self.cell)
        def handle_endtag(self,t):
            if t in ('td','th'):self.cell=None
        def handle_data(self,s):
            if self.cell is not None:self.cell['text']+=s
    parser=TableParser();parser.feed(html)
    return dict(bbox=bbox,rows=len(parser.rows),columns=max([len(r) for r in parser.rows] or [0]),source='ocr',header=[],cells=[dict(row=i+1,column=j+1,text=c['text'],bbox=bbox,geometry='table-level',**c['attributes']) for i,r in enumerate(parser.rows) for j,c in enumerate(r)])
