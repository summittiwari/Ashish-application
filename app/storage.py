"""Optional S3-compatible archive; processing always uses the shared local work volume."""
import os
from .config import ROOT
from .db import log

def client():
    import boto3
    return boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT_URL') or None,
                        region_name=os.getenv('AWS_DEFAULT_REGION','us-east-1'))

def archive_files(kind,identifier,files):
    bucket=os.getenv('S3_BUCKET')
    if not bucket:return False
    prefix=os.getenv('S3_PREFIX','pdf-sentinel').strip('/')
    try:
        s3=client()
        for name,path in files:
            args={'ServerSideEncryption':os.environ['S3_SSE']} if os.getenv('S3_SSE') else {}
            s3.upload_file(str(path),bucket,f'{prefix}/{kind}/{identifier}/{name}',ExtraArgs=args)
        log('archive_completed',identifier,{'kind':kind});return True
    except Exception as e:
        # The local result remains available and this explicit failure can be retried by operators.
        log('archive_failed',identifier,{'kind':kind,'error_type':type(e).__name__});return False

def archive_document(identifier):
    return archive_files('documents',identifier,[('original.pdf',ROOT/'documents'/f'{identifier}.pdf')])

def archive_job(identifier):
    folder=ROOT/'jobs'/identifier/'exports'
    return archive_files('jobs',identifier,[(p.name,p) for p in sorted(folder.iterdir()) if p.is_file()])

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description='Retry an optional S3 archive. Uses standard AWS credentials.')
    p.add_argument('kind',choices=['document','job']);p.add_argument('id');a=p.parse_args()
    from .db import documents,jobs,one
    if not one(documents if a.kind=='document' else jobs,a.id):p.error('Unknown ID')
    ok=archive_document(a.id) if a.kind=='document' else archive_job(a.id)
    raise SystemExit(0 if ok else 1)
