"""Surya 2 is used only for extraction. It never decides whether PDFs differ."""
import importlib.util, os
from html.parser import HTMLParser
class PlainText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,s):self.parts.append(s)
    def handle_starttag(self,t,a):
        if t in ('br','p','tr','td','th','li'):self.parts.append(' ')

def plain(s):
    p=PlainText();p.feed(s or '');return ''.join(p.parts).strip()

def available():
    return bool(importlib.util.find_spec('surya')) and bool(os.getenv('SURYA_INFERENCE_URL'))

def recognize(image):
    if not available():
        raise RuntimeError('Surya OCR is not configured: install requirements-ocr.txt and set a local SURYA_INFERENCE_URL. Scanned text is not assessed.')
    # The configured endpoint must be operator-controlled. No document content is sent to a cloud service by this application.
    from surya.inference import SuryaInferenceManager
    from surya.recognition import RecognitionPredictor
    manager=SuryaInferenceManager()
    result=RecognitionPredictor(manager)([image])[0]
    out=[]
    for i,b in enumerate(result.blocks):
        if getattr(b,'error',False):raise RuntimeError('Surya failed to recognize a block')
        text=plain(b.html)
        out.append(dict(text=text,bbox=list(b.bbox),label=b.label,confidence=float(b.confidence or 0),order=i,html=b.html if b.label=='Table' else None))
    return out
