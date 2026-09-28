from pathlib import Path
import fitz
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

OUT=Path(__file__).resolve().parents[1]/'examples';OUT.mkdir(exist_ok=True)

def invoice(path,modified=False):
    c=canvas.Canvas(str(path),pagesize=(595,842),invariant=1)
    c.setTitle('Northstar services - '+('Revised invoice' if modified else 'Invoice baseline'))
    c.setAuthor('PDF Sentinel example data')
    for page in range(1,4):
        c.setFillColor(HexColor('#163757'));c.roundRect(40,757,155,42,6,fill=1,stroke=0)
        c.setFillColor(HexColor('#ffffff'));c.setFont('Helvetica-Bold',16);c.drawString(53,773,'NORTHSTAR')
        c.setFillColor(HexColor('#53677e'));c.setFont('Helvetica',9);c.drawRightString(555,783,'SERVICES / DOCUMENT CONTROL')
        c.setStrokeColor(HexColor('#dae1e9'));c.line(40,740,555,740)
        c.setFillColor(HexColor('#163757'))
        if page==1:
            c.setFont('Helvetica-Bold',26 if modified else 25);c.drawString(40,695,'Service invoice')
            c.setFont('Helvetica',10);c.drawString(40,669,'Invoice NS-2026-024  |  Issued 24 September 2026')
            c.setFont('Helvetica-Bold',11);c.drawString(40,622,'BILL TO');c.setFont('Helvetica',11);c.drawString(40,600,'Culina Logistics — Example account')
            c.drawString(40,582,'Operations & Technology')
            rows=[['Description','Quantity','Rate (GBP)','Amount (GBP)'],['Platform maintenance','1','2,500.00','2,500.00'],['Implementation support','20','100.00','2,400.00' if modified else '2,000.00'],['TOTAL','','','4,900.00' if modified else '4,500.00']]
            xs=[40,310,385,465,555];ys=[545,510,472,434,396]
            for ri,row in enumerate(rows):
                c.setFillColor(HexColor('#eaf0f7') if ri==0 else HexColor('#ffffff'));c.rect(xs[0],ys[ri+1],515,ys[ri]-ys[ri+1],fill=1,stroke=0)
                for ci,cell in enumerate(row):
                    c.setFillColor(HexColor('#163757'));c.setFont('Helvetica-Bold' if ri in (0,3) else 'Helvetica',9);c.drawString(xs[ci]+8,ys[ri]-22,cell)
            c.setStrokeColor(HexColor('#bfcddd'));c.setLineWidth(.5)
            for x in xs:c.line(x,ys[-1],x,ys[0])
            for y in ys:c.line(xs[0],y,xs[-1],y)
            c.setFont('Helvetica-Bold',12);c.drawString(40,355,'Payment terms')
            c.setFont('Helvetica',11);c.drawString(40,328,f'Payment must be completed within {45 if modified else 30} days.')
            c.drawString(40,306,'Refunds are not permitted.' if modified else 'Refunds are permitted.')
            c.setFillColor(HexColor('#61758c'));c.setFont('Helvetica',10);c.drawString(40,260,'Please quote the invoice reference with your payment.')
        elif page==2:
            c.setFont('Helvetica-Bold',25);c.drawString(40,695,'Service scope')
            c.setFont('Helvetica',12)
            for i,s in enumerate(['Application monitoring and platform support.','Scheduled release coordination and change records.','Documentation and operational handover.']):c.drawString(40,645-i*28,s)
        else:
            c.setFont('Helvetica-Bold',25);c.drawString(40,695,'Acceptance checklist')
            c.setFont('Helvetica',12)
            for i,s in enumerate(['Release documentation received.','Operational checks completed.','Service owner approval recorded.']):c.drawString(40,645-i*28,s)
        c.setStrokeColor(HexColor('#dae1e9'));c.line(40,67,555,67);c.setFillColor(HexColor('#61758c'));c.setFont('Helvetica',9);c.drawString(40,47,'INTERNAL — Example document for testing');c.drawRightString(555,47,f'{page} of 3');c.showPage()
    c.save()

invoice(OUT/'reference.pdf');invoice(OUT/'candidate-original.pdf',True)
with fitz.open(OUT/'candidate-original.pdf') as d:
    d.select([0,2,1]);d.save(OUT/'candidate.pdf')
(OUT/'candidate-original.pdf').unlink()
print('Generated reference.pdf and candidate.pdf')
