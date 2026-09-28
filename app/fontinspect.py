"""Inspect bounded embedded font programs; subset byte changes are informational."""
import hashlib,io
from fontTools.ttLib import TTFont
from .extract import fontname

def inspect_fonts(doc):
    used={};warnings=[]
    for page in doc:
        for f in page.get_fonts(full=True):used[f[0]]=f
    out=[]
    for xref,f in used.items():
        entry={'name':fontname(f[3]),'type':f[2],'encoding':f[5],'embedded':f[1] not in ('n/a',''),'subset':f[3]!=fontname(f[3])}
        if entry['embedded']:
            try:
                name,extension,kind,data=doc.extract_font(xref)
                if len(data)>32*1024**2:
                    warnings.append(f'Font program over 32 MiB: {entry["name"]}');continue
                entry['program_bytes']=len(data);entry['program_sha256']=hashlib.sha256(data).hexdigest()
                if extension in ('ttf','otf'):
                    font=TTFont(io.BytesIO(data),lazy=True)
                    if 'head' in font:entry['units_per_em']=font['head'].unitsPerEm
                    if 'OS/2' in font:entry['weight_class']=font['OS/2'].usWeightClass;entry['width_class']=font['OS/2'].usWidthClass
                    if 'name' in font:
                        entry['family']=font['name'].getDebugName(1);entry['style']=font['name'].getDebugName(2)
                    entry['tables']=sorted(font.keys());font.close()
            except Exception as e:warnings.append(f'Embedded font inspection incomplete: {entry["name"]} ({type(e).__name__})')
        out.append(entry)
    return sorted(out,key=lambda x:(x['name'],x['type'],x['encoding'])),warnings
