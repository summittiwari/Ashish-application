"""One isolated, memory-limited native operation per subprocess."""
import os, sys, resource
from pathlib import Path
from .config import MEMORY_MB, ROOT
resource.setrlimit(resource.RLIMIT_AS,(MEMORY_MB*1024**2,MEMORY_MB*1024**2))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
from .util import write_json,read_json

def main():
    action=sys.argv[1];args=sys.argv[2:]
    if action=='inspect':
        from .extract import inspect_document
        write_json(args[1],inspect_document(args[0]))
    elif action=='extract':
        from .extract import extract_page
        extract_page(args[0],int(args[1]),args[2],args[3]=='1')
    elif action=='extract-batch':
        from .extract import extract_page
        for index in range(int(args[1]),int(args[2])):
            out=Path(args[3])/f'{index}.json'
            if not out.exists():extract_page(args[0],index,out,args[4]=='1')
    elif action=='compare-batch':
        from .compare import compare_page
        for pairfolder in read_json(args[0]):
            pf=Path(pairfolder)
            if (pf/'result.json').exists():continue
            spec=read_json(pf/'input.json');a=read_json(spec['cache_a']) if spec.get('cache_a') else None;b=read_json(spec['cache_b']) if spec.get('cache_b') else None
            write_json(pf/'result.json',compare_page(a,b,spec['path_a'],spec['path_b'],spec['mapping'],spec['options'],pf))
    elif action=='compare':
        from .compare import compare_page
        spec=read_json(args[0]);a=read_json(spec['cache_a']) if spec.get('cache_a') else None;b=read_json(spec['cache_b']) if spec.get('cache_b') else None
        write_json(args[1],compare_page(a,b,spec['path_a'],spec['path_b'],spec['mapping'],spec['options'],Path(spec['folder'])))
    elif action=='render':
        import fitz
        from .extract import render
        with fitz.open(args[0]) as d:
            im,_=render(d[int(args[1])],int(args[3]));im.save(args[2])
    elif action=='exports':
        from .reports import generate_exports
        generate_exports(args[0])
    elif action=='run':
        from .pipeline import run_job
        run_job(args[0])
    else:raise ValueError('Unknown operation')
if __name__=='__main__':main()
